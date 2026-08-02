"""Deterministic validation for structured recommendations."""

import logging

from pipeline.recommendation_builder import (
    BUY_ACTIONS,
    SECTION_MY_HOLDINGS,
    SECTION_WHAT_TO_DO,
)
from shared.calibration_overlay import get_calibrated_entry_gap
from shared.rules.exit_strategy import format_rr_display, is_trailing_exit, read_rr
from shared.rules.recommendation_gate import RecommendationGateDecision
from shared.rules.rr_floors import BORDERLINE_RR_EPSILON
from shared.rules.rr_math import compute_net_rr_only
from shared.trading_config import get_trading_config

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ENTRY_GAP_PCT = 3.0
_DEFAULT_TRANSACTION_COST_PCT = 0.003


def _is_atr_trail_rec(rec: dict) -> bool:
    """Call SSOT ``is_trailing_exit`` with rec-shape keys (rec uses ``target_price``)."""
    return is_trailing_exit(
        {
            "exit_family": rec.get("exit_family"),
            "target": rec.get("target_price"),
        }
    )


def _validate_exit_contract(rec: dict) -> str | None:
    """Return drop-reason string or None for the BUY exit contract.

    SWI-340: trailing picks MUST have target=None AND risk_reward=None;
    fixed-target picks MUST have non-null target AND positive risk_reward.
    Mirrors the producer contract in picks.py.
    """
    is_trailing = _is_atr_trail_rec(rec)
    target = rec.get("target_price")
    rr = rec.get("risk_reward")
    if is_trailing:
        if target is not None:
            return f"ATR_TRAIL with numeric target_price={target} (provenance lost)"
        if rr is not None:
            return (
                f"ATR_TRAIL with non-null risk_reward={rr} "
                "(provenance lost — picks.py sets None for trailing)"
            )
        return None
    if target is None:
        return "FIXED_TARGET with target_price=None"
    if rr is None or rr <= 0:
        return f"FIXED_TARGET with non-positive risk_reward={rr}"
    return None


def _maybe_downgrade_holding(
    rec: dict,
    reason: str,
    validated: list[dict],
    warnings: list[str],
) -> bool:
    """If a dropped BUY rec is from MY_HOLDINGS, downgrade to HOLD instead of dropping.

    Returns True if downgraded (caller should skip normal drop), False otherwise.
    """
    if rec.get("section") != SECTION_MY_HOLDINGS:
        return False
    ticker = rec.get("ticker") or "?"
    action = rec.get("action") or ""
    warnings.append(f"HOLDINGS_DOWNGRADE: {ticker} {action} → HOLD ({reason})")
    validated.append({**rec, "action": "HOLD", "source": "auto_hold"})
    return True


def validate_structured_recommendations(
    recs: list[dict],
    trading_mode: dict | None,
    deployable_cash: float,
    gate_decision: RecommendationGateDecision,
) -> tuple[list[dict], list[str]]:
    """Deterministic validation. Returns (validated_recs, warnings).

    All R:R floor + max_picks logic comes from the single
    `RecommendationGateDecision` so the brief, the picks writer, and this
    validator read from ONE audit-logged source of truth.
    """
    warnings: list[str] = []
    mode = (trading_mode.get("mode") if trading_mode else None) or "NORMAL"
    rr_floor = gate_decision.effective_rr_floor
    max_picks = gate_decision.max_new_entries

    # Pass 1: Trading mode enforcement
    if mode in ("LOW_CASH", "REALLOCATION") and deployable_cash <= 0:
        buy_count = sum(1 for r in recs if r.get("action") in BUY_ACTIONS)
        if buy_count > 0:
            warnings.append(
                f"MODE ENFORCEMENT: {mode} with {deployable_cash:.0f} deployable — "
                f"dropping {buy_count} BUY rec(s)"
            )
            recs = [r for r in recs if r.get("action") not in BUY_ACTIONS]

    # Pass 2: REALLOCATION requires EXIT for BUY
    if mode == "REALLOCATION":
        has_exit = any(
            r.get("action") == "EXIT" and r.get("section") == SECTION_MY_HOLDINGS for r in recs
        )
        if not has_exit:
            buy_recs = [r for r in recs if r.get("action") in BUY_ACTIONS]
            if buy_recs:
                tickers = [r["ticker"] for r in buy_recs]
                warnings.append(
                    f"REALLOCATION: no EXIT found — dropping BUY for {', '.join(tickers)}"
                )
                recs = [r for r in recs if r.get("action") not in BUY_ACTIONS]

    # Loop invariants — hoisted out of the per-rec loop
    try:
        max_gap_pct = get_calibrated_entry_gap() or _DEFAULT_MAX_ENTRY_GAP_PCT
    except Exception as error:
        logger.warning("calibrated entry gap lookup failed, using default: %s", error)
        max_gap_pct = _DEFAULT_MAX_ENTRY_GAP_PCT
    try:
        cost_pct = get_trading_config().transaction_cost_pct or _DEFAULT_TRANSACTION_COST_PCT
    except Exception as error:
        logger.warning("trading_config lookup failed, using default: %s", error)
        cost_pct = _DEFAULT_TRANSACTION_COST_PCT

    # Pass 3: Price geometry + R:R validation for BUY recs
    validated = []
    buy_count = 0
    for rec in recs:
        action = rec.get("action") or ""
        ticker = rec.get("ticker") or "?"

        if action not in BUY_ACTIONS:
            entry = rec.get("entry_price")
            target = rec.get("target_price")
            if entry and target and entry >= target:
                warnings.append(f"GEOMETRY: {ticker} {action} entry ({entry}) >= target ({target})")
            validated.append(rec)
            continue

        entry = rec.get("entry_price")
        stop = rec.get("stop_price")
        target = rec.get("target_price")

        is_atr_trail = _is_atr_trail_rec(rec)

        if action in BUY_ACTIONS and entry is None:
            if not _maybe_downgrade_holding(rec, "no entry price", validated, warnings):
                warnings.append(f"NO ENTRY PRICE: {ticker} {action} — dropping")
            continue
        if stop is None:
            if not _maybe_downgrade_holding(rec, "no stop price", validated, warnings):
                warnings.append(f"NO STOP PRICE: {ticker} {action} — dropping")
            continue

        # SWI-340: log ATR_TRAIL_PRODUCER_LEAK so the next recurrence pinpoints the producer.
        exit_contract_violation = _validate_exit_contract(rec)
        if exit_contract_violation is not None:
            logger.warning(
                "ATR_TRAIL_PRODUCER_LEAK ticker=%s section=%s strategy=%s exit_family=%s "
                "target_was=%s rr_was=%s — %s",
                ticker,
                rec.get("section"),
                rec.get("strategy"),
                rec.get("exit_family"),
                rec.get("target_price"),
                rec.get("risk_reward"),
                exit_contract_violation,
            )
            if not _maybe_downgrade_holding(rec, exit_contract_violation, validated, warnings):
                warnings.append(
                    f"EXIT CONTRACT: {ticker} {action} — {exit_contract_violation} — dropping"
                )
            continue

        if entry and stop and stop >= entry:
            if not _maybe_downgrade_holding(
                rec, f"stop ({stop}) >= entry ({entry})", validated, warnings
            ):
                warnings.append(f"GEOMETRY: {ticker} stop ({stop}) >= entry ({entry}) — dropping")
            continue
        if entry and target and entry >= target:
            if not _maybe_downgrade_holding(
                rec, f"entry ({entry}) >= target ({target})", validated, warnings
            ):
                warnings.append(
                    f"GEOMETRY: {ticker} entry ({entry}) >= target ({target}) — dropping"
                )
            continue

        # Pass 3.5: Entry reachability backstop — defense-in-depth cap on
        # entry to within max_entry_gap_pct of scan-time close. Primary
        # enforcement lives in compute_setup_from_levels().
        rec_close = rec.get("close")
        if entry and rec_close and rec_close > 0:
            entry_gap_ratio = (rec_close - entry) / rec_close
            if entry_gap_ratio > max_gap_pct / 100:
                capped_entry = round(rec_close * (1 - max_gap_pct / 100))
                stop = rec.get("stop_price")
                target = rec.get("target_price")
                if stop and target and capped_entry > stop:
                    capped_rr = compute_net_rr_only(capped_entry, stop, target, cost_pct) or 0.0
                    # ENTRY GAP recompute path runs only on fixed-target recs (target is
                    # known above). Trailing recs have target=None and skip this branch
                    # via the outer `not (entry and target and stop)` guard at line 206.
                    prior_rr_disp = format_rr_display(read_rr(rec), precision=2)
                    warnings.append(
                        f"ENTRY GAP: {ticker} entry {entry} → {capped_entry} "
                        f"(capped to {max_gap_pct:.1f}% below close {rec_close}), "
                        f"R:R {prior_rr_disp} → {capped_rr:.2f}"
                    )
                    rec = {**rec, "entry_price": capped_entry, "risk_reward": capped_rr}

        # ATR_TRAIL gated by ATRTrailExit.rr_gate in picks.py; non-null rr vetted above.
        if not is_atr_trail:
            risk_reward = rec["risk_reward"]
            if risk_reward < rr_floor:
                borderline = abs(risk_reward - rr_floor) < BORDERLINE_RR_EPSILON
                precision = 2 if borderline else 1
                reason = f"R:R {risk_reward:.{precision}f} < floor {rr_floor:.{precision}f}"
                if not _maybe_downgrade_holding(rec, reason, validated, warnings):
                    warnings.append(f"R:R FLOOR: {ticker} {reason} — dropping")
                continue

        buy_count += 1
        if buy_count > max_picks:
            if not _maybe_downgrade_holding(
                rec, f"exceeds max picks ({max_picks})", validated, warnings
            ):
                warnings.append(f"MAX PICKS: {ticker} exceeds limit ({max_picks}) — dropping")
            continue

        validated.append(rec)

    # Pass 4: Cross-section dedup (SKIP wins over BUY)
    skip_tickers = {r["ticker"] for r in validated if r.get("action") in ("SKIP", "AVOID")}
    if skip_tickers:
        deduped = []
        for rec in validated:
            ticker = rec.get("ticker") or ""
            if ticker in skip_tickers and rec.get("action") in BUY_ACTIONS:
                warnings.append(f"CROSS-SECTION: {ticker} BUY conflicts with SKIP — dropping BUY")
                continue
            deduped.append(rec)
        validated = deduped

    # Pass 5: Non-held ticker downgrade
    holdings_in_recs = {r["ticker"] for r in validated if r.get("section") == SECTION_MY_HOLDINGS}
    final = []
    for rec in validated:
        action = rec.get("action") or ""
        ticker = rec.get("ticker") or ""
        if (
            action in ("HOLD", "EXIT", "TRIM", "ADD")
            and ticker not in holdings_in_recs
            and rec.get("source") != "position_alerts"
        ):
            warnings.append(f"NOT HELD: {ticker} {action} — downgrading to WATCH")
            rec = {**rec, "action": "WATCH", "section": SECTION_WHAT_TO_DO}
        final.append(rec)

    return final, warnings
