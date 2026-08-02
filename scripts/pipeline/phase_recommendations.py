"""Phase 6: Write structured recommendations to DB (no LLM parsing)."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from eval.score_recorder import ScoreRecorder

from agents.retro.parser import SECTION_WHAT_TO_DO
from shared.env import is_production
from shared.observability import log_warn
from shared.rules.audit_tags import (
    DERIVED_FROM_BELIEFS,
    DETERMINISTIC_ONLY,
    NO_BELIEF_NO_REC,
    PARTIAL_COVERAGE,
    RECONCILED_FROM_BELIEFS,
)
from shared.rules.belief_to_signal import Signal, derive_signal_from_belief
from shared.rules.recommendation_gate import RecommendationGateDecision

from .published_action_audit import audit_action_downgrades
from .recommendation_builder import BUY_ACTIONS, build_structured_recommendations
from .recommendation_validator import validate_structured_recommendations
from .types import DeterministicBeliefs

logger = logging.getLogger(__name__)


# Default confidence floor used when deterministic beliefs lack calibration stats.
NO_BELIEF_CONFIDENCE = 0.2

# Backwards-named aliases kept for local readability — tag vocabulary lives in
# `shared.rules.audit_tags` and is the single source of truth for the strip path.
RECONCILED_MARKER = RECONCILED_FROM_BELIEFS
NO_BELIEF_MARKER = NO_BELIEF_NO_REC

# Coverage-gap reconciliation never auto-promotes a missing ticker to BUY.
# Missing tickers have not passed the pipeline's entry gates; surface as WATCH
# so operators review before acting. BUY is absent from this map because
# derive_signal_from_belief never returns it (see belief_to_signal.py).
_SIGNAL_TO_ACTION: dict[Signal, Literal["WATCH", "WAIT", "AVOID"]] = {
    "WATCH": "WATCH",
    "WAIT": "WAIT",
    "AVOID": "AVOID",
}

CoverageLevel = Literal["FULL", "PARTIAL", "DETERMINISTIC_ONLY", "NONE"]


def coverage_level_from_rec(rec: dict) -> CoverageLevel:
    """Resolve a rec's coverage tier from explicit field or marker inspection.

    Prefers the explicit `coverage_level` field (set at build time) and falls
    back to marker presence in `rationale` / `verdict` for rows originating
    from older code paths or DB reads that do not carry the field yet.
    """
    explicit = rec.get("coverage_level")
    if explicit in ("FULL", "PARTIAL", "DETERMINISTIC_ONLY", "NONE"):
        return explicit  # type: ignore[return-value]
    text = f"{rec.get('rationale') or ''} {rec.get('verdict') or ''}"
    if NO_BELIEF_NO_REC in text:
        return "NONE"
    if PARTIAL_COVERAGE in text:
        return "PARTIAL"
    if (
        DETERMINISTIC_ONLY in text
        or RECONCILED_FROM_BELIEFS in text
        or DERIVED_FROM_BELIEFS in text
    ):
        return "DETERMINISTIC_ONLY"
    return "FULL"


def _tickers_in_recs(recommendations: list[dict]) -> set[str]:
    """Extract unique uppercase tickers from a recommendation list."""
    return {(rec.get("ticker") or "").upper() for rec in recommendations}


def _build_valid_tickers(
    swing_watchlist_tickers: set[str] | None,
    longterm_watchlist: dict[str, dict] | None,
    holdings: list[dict] | None,
) -> frozenset[str]:
    """Build authoritative universe from the 3 upstream sources.

    Raises `RuntimeError("UNIVERSE_FETCH_FAILED")` when ALL three inputs are
    empty — that state is almost always an upstream fetch failure (portfolio
    API down, watchlist table empty due to migration, etc.) and the
    alternative is silently dropping every recommendation.
    """
    swing = {t.upper() for t in (swing_watchlist_tickers or set()) if t}
    longterm = {t.upper() for t in (longterm_watchlist or {}) if t}
    held = {
        (slice_row.get("ticker") or "").upper()
        for slice_row in (holdings or [])
        if slice_row.get("ticker")
    }
    universe = swing | longterm | held
    if not universe:
        raise RuntimeError(
            "UNIVERSE_FETCH_FAILED: swing + longterm watchlists AND portfolio "
            "holdings all empty — refusing to silently drop every rec. "
            "Check upstream watchlist/portfolio fetches."
        )
    return frozenset(universe)


def _flatten_beliefs(beliefs: DeterministicBeliefs) -> dict[str, dict]:
    """Flatten sector + positions beliefs into a ticker→belief lookup.

    Positions override sector when both exist (positions reflect held state).
    """
    flat: dict[str, dict] = {}
    for belief in beliefs.get("sector") or []:
        flat[belief["ticker"]] = belief
    for belief in beliefs.get("positions") or []:
        flat[belief["ticker"]] = belief
    return flat


def _reconciled_rec_from_belief(ticker: str, belief: dict, calibration_stats: dict) -> dict:
    """Build a recommendation row from an aggregated belief."""
    signal = derive_signal_from_belief(belief)
    action = _SIGNAL_TO_ACTION.get(signal, "WAIT")
    direction = belief.get("direction", "NEUTRAL")
    narrative = (belief.get("belief_narrative") or "").strip()
    rationale = (
        f"{RECONCILED_MARKER} {narrative}"
        if narrative
        else f"{RECONCILED_MARKER} direction={direction}"
    )

    conviction = float(belief.get("conviction") or 0.5)
    agent_key = belief.get("agent_key") or ""
    agent_stats = (calibration_stats or {}).get(agent_key, {})
    effective_brier = agent_stats.get("brier_30d")
    if effective_brier is None:
        effective_brier = agent_stats.get("avg_brier")
    calibration_penalty = 1.0 if effective_brier is None else max(0.0, 1.0 - float(effective_brier))
    strategy_confidence = max(0.05, min(0.95, conviction * calibration_penalty))

    return {
        "ticker": ticker,
        "action": action,
        "section": SECTION_WHAT_TO_DO,
        "source": "reconciliation",
        "rationale": rationale,
        "strategy_confidence": strategy_confidence,
        "verdict": f"{action} — {RECONCILED_MARKER} {direction} view",
        "coverage_level": "DETERMINISTIC_ONLY",
    }


def _no_belief_rec(ticker: str) -> dict:
    """Fail-loudly row for a watchlist ticker with no deterministic belief."""
    return {
        "ticker": ticker,
        "action": "WAIT",
        "section": SECTION_WHAT_TO_DO,
        "source": "reconciliation",
        "rationale": (
            f"{NO_BELIEF_MARKER} {ticker} on swing watchlist but missing from "
            "pipeline output AND no deterministic belief."
        ),
        "strategy_confidence": NO_BELIEF_CONFIDENCE,
        "verdict": f"WAIT — {NO_BELIEF_MARKER} No pipeline coverage for {ticker}.",
        "coverage_level": "NONE",
    }


def _inject_coverage_gaps(
    recommendations: list[dict],
    swing_watchlist_tickers: set[str],
    beliefs_by_ticker: dict[str, dict],
    calibration_stats: dict,
) -> list[dict]:
    """Reconcile watchlist tickers absent from pipeline output using deterministic beliefs.

    Preference order per ticker:
      1. Aggregated belief → direction-aware WATCH / WAIT / AVOID row with the
         belief's narrative and a calibration-penalized strategy_confidence.
      2. No belief available → fail-loudly `[NO_BELIEF_NO_REC]` row + `logger.error`.
         Rare once T04 derives signals from sub-agent views for timed-out
         sector aggregators; a hit here implies total sector failure upstream.
    """
    covered_tickers = _tickers_in_recs(recommendations)

    reconciled_rows: list[dict] = []
    reconciled_count = 0
    for ticker in swing_watchlist_tickers:
        ticker = ticker.upper()
        if ticker in covered_tickers:
            continue
        belief = beliefs_by_ticker.get(ticker)
        if belief is not None:
            row = _reconciled_rec_from_belief(ticker, belief, calibration_stats)
            reconciled_rows.append(row)
            reconciled_count += 1
            logger.info(
                "Coverage gap reconciled from belief: %s → %s (direction=%s)",
                ticker,
                row["action"],
                belief.get("direction"),
            )
        else:
            logger.error(
                "NO_BELIEF_NO_REC: %s on swing watchlist, missing from recs, "
                "AND no deterministic belief — possible upstream failure",
                ticker,
            )
            reconciled_rows.append(_no_belief_rec(ticker))

    if reconciled_count:
        logger.info("Reconciled %d ticker(s) from beliefs", reconciled_count)

    return recommendations + reconciled_rows


async def run_phase6_recommendations(
    pre_computed_picks: list[dict],
    position_alerts: dict,
    sector_signals: list[dict],
    holdings: list[dict],
    trading_mode: dict,
    longterm_watchlist: dict,
    deployable_cash: float,
    market_regime: str,
    global_risk_regime: str,
    scan_date: date,
    reflection_status: str,
    gate_decision: RecommendationGateDecision | None,
    deterministic_beliefs: DeterministicBeliefs | None = None,
    swing_watchlist_tickers: set[str] | None = None,
    buy_signal_count: int = 0,
    technicals: dict | None = None,
    gated_tickers: list[dict] | None = None,
    # SWI-171 Phase A audit (optional)
    score_recorder: ScoreRecorder | None = None,
    score_phase: Literal["morning", "midday", "retro"] = "morning",
) -> None:
    """Build, validate, and persist structured recommendations to DB."""
    print("\n" + "=" * 60, flush=True)
    print("PHASE 6: Write Recommendations to DB", flush=True)
    print("=" * 60, flush=True)

    try:
        from shared.neon import insert_morning_recommendations

        # Build trade_setup lookup for WATCH/SKIP R:R population. Derived
        # directly from the technicals map (keyed by ticker) so the lookup is
        # independent of sector-signal ordering — eliminates a latent
        # local-rebind fragility in phase_picks.
        # WATCH/WAIT rows pull trigger from conditional setups; do not filter on `valid`.
        trade_setups_by_ticker: dict[str, dict] = {
            ticker.upper(): setup
            for ticker, tech in (technicals or {}).items()
            if (setup := (tech.get("trade_setup") or {}))
        }

        beliefs_contract: DeterministicBeliefs = deterministic_beliefs or {}  # type: ignore[assignment]
        beliefs_by_ticker = _flatten_beliefs(beliefs_contract)
        calibration_stats = beliefs_contract.get("calibration_stats") or {}

        # Build authoritative universe: swing watchlist ∪ longterm watchlist
        # ∪ portfolio tickers. Empty inputs across ALL three must fail closed
        # — an empty universe here means the upstream watchlist/portfolio
        # fetches failed and we'd otherwise silently drop every rec.
        valid_tickers = _build_valid_tickers(
            swing_watchlist_tickers=swing_watchlist_tickers,
            longterm_watchlist=longterm_watchlist,
            holdings=holdings,
        )

        structured_recommendations = build_structured_recommendations(
            pre_computed_picks=pre_computed_picks or [],
            position_alerts=position_alerts,
            sector_signals=sector_signals,
            holdings=holdings or [],
            trading_mode=trading_mode,
            longterm_watchlist=longterm_watchlist,
            beliefs_by_ticker=beliefs_by_ticker or None,
            calibration_stats=calibration_stats or None,
            trade_setups_by_ticker=trade_setups_by_ticker or None,
            valid_tickers=valid_tickers,
            gated_tickers=gated_tickers,
            technicals_by_ticker={
                ticker.upper(): tech for ticker, tech in (technicals or {}).items()
            }
            or None,
            gate_floor_at_build=(
                float(gate_decision.effective_rr_floor) if gate_decision else None
            ),
            gate_passes_at_build=(bool(gate_decision.entries_allowed) if gate_decision else None),
        )

        if swing_watchlist_tickers:
            structured_recommendations = _inject_coverage_gaps(
                structured_recommendations,
                swing_watchlist_tickers,
                beliefs_by_ticker,
                calibration_stats,
            )

        # Don't inject — auto-HOLD in recommendation_builder.py owns this invariant
        holdings_in_recs = _tickers_in_recs(structured_recommendations)
        seen_in_check: set[str] = set()
        for slice_row in holdings or []:
            holding_ticker_upper = (slice_row.get("ticker") or "").upper()
            if not holding_ticker_upper or holding_ticker_upper in seen_in_check:
                continue
            seen_in_check.add(holding_ticker_upper)
            if holding_ticker_upper not in holdings_in_recs:
                logger.warning(
                    "HOLDINGS_GAP: %s is held but has no recommendation — "
                    "auto-HOLD in recommendation_builder should have caught this. "
                    "Check holdings list and seen_tickers at build time.",
                    holding_ticker_upper,
                )

        if gate_decision is None:
            raise RuntimeError(
                "GATE_DECISION_MISSING: phase6 received gate_decision=None. "
                "compose_gate_from_state must run before phase6. Check "
                "phase_orchestration wiring."
            )
        validated_recommendations, recommendation_warnings = validate_structured_recommendations(
            recs=structured_recommendations,
            trading_mode=trading_mode,
            deployable_cash=deployable_cash,
            gate_decision=gate_decision,
        )
        if recommendation_warnings:
            for warning in recommendation_warnings:
                print(f"  Rec validation: {warning}", flush=True)

        # SWI-171 Phase A: re-stamp `pre_gate_candidates.gated_by` for each
        # BUY rec the validator saw — picks.py wrote 'passed' for layers
        # 1-4 survivors; the validator's verdict overrides it. Audit-only,
        # no behavioral effect on `validated_recommendations`.
        if score_recorder is not None:
            from .recommendation_audit import audit_validator_outcome

            await audit_validator_outcome(
                recorder=score_recorder,
                phase=score_phase,  # type: ignore[arg-type]
                input_recs=structured_recommendations,
                output_recs=validated_recommendations,
                warnings=recommendation_warnings,
            )

        # Audit invariant: every aggregator EXIT/TRIM that ends up
        # published as a different action must cite a deterministic
        # resolving rule. Under ADVOCATE_GATE_MODE=enforce a missing rule
        # raises instead of shipping a silent downgrade.
        audit_action_downgrades(
            scan_date=scan_date,
            validated_recommendations=validated_recommendations,
            position_alerts=position_alerts,
        )

        buy_rec_count = sum(1 for r in validated_recommendations if r.get("action") in BUY_ACTIONS)

        mode_str = trading_mode.get("mode") if trading_mode else None
        await insert_morning_recommendations(
            scan_date=scan_date,
            market_regime=market_regime,
            trading_mode=mode_str,
            recommendations=validated_recommendations,
            reflection_status=reflection_status,
            buy_signal_count=buy_signal_count,
            buy_rec_count=buy_rec_count,
            gate_decision_json=gate_decision.to_jsonb() if gate_decision else None,
            global_risk_regime=global_risk_regime,
        )

        # Register conditional alerts for WATCH/WAIT rows. Failure must not
        # crash the pipeline — rec insert already committed. `recs_without_alerts`
        # shortfall log makes divergence visible.
        try:
            from shared.neon.alerts import register_alerts_batch

            from .conditional_alerts import build_conditional_alert_payloads

            alert_payloads = build_conditional_alert_payloads(validated_recommendations, scan_date)
            registered = await register_alerts_batch([dict(p) for p in alert_payloads])
            if registered:
                logger.info("Registered %d conditional_watch alert(s)", registered)
            shortfall = len(alert_payloads) - registered
            if shortfall:
                logger.warning(
                    "recs_without_alerts: %d of %d conditional payloads failed for %s",
                    shortfall,
                    len(alert_payloads),
                    scan_date,
                )
        except Exception as alert_exc:
            logger.warning("Conditional alert registration failed for %s: %s", scan_date, alert_exc)

        print(
            f"  BUY funnel: {buy_signal_count} signals → {buy_rec_count} recommendations",
            flush=True,
        )

        await _check_buy_survival_rate(scan_date)
    except RuntimeError:
        # UNIVERSE_FETCH_FAILED + sibling fail-closed conditions must
        # propagate — they signal upstream data loss, not a DB glitch.
        # Carve-out preserved verbatim from 87d05d55.
        raise
    except Exception as e:
        # Env-gated raise: production logs + continues so the pipeline
        # completes degraded (MORNING_EMPTY_RECS guard is the secondary
        # failsafe); non-prod re-raises so regressions surface in CI.
        logger.exception("Recommendation DB write error for %s: %s", scan_date, e)
        print(f"  Recommendation DB write error: {e}", flush=True)
        log_warn(
            "pipeline_db_write_unexpected",
            scope="phase_recommendations",
            scan_date=str(scan_date),
            error=str(e),
            error_type=type(e).__name__,
        )
        if not is_production():
            raise


_SURVIVAL_ALERT_DAYS = 3
_SURVIVAL_RATE_THRESHOLD = 0.05


async def _check_buy_survival_rate(scan_date: date) -> None:
    """Alert if BUY survival rate is near-zero for consecutive days.

    Queries the last N days where BUY signals existed and checks if
    recommendations consistently failed to materialize — a sign of
    compounding gate regression (conservatism death spiral).
    """
    try:
        from shared.database import get_db
        from shared.telegram import send_telegram_error

        db = await get_db()
        rows = await db.fetch_all(
            """
            SELECT buy_signal_count, buy_rec_count
            FROM daily_records
            WHERE buy_signal_count > 0
              AND record_date <= $1
            ORDER BY record_date DESC
            LIMIT $2
            """,
            scan_date,
            _SURVIVAL_ALERT_DAYS,
        )

        if len(rows) < _SURVIVAL_ALERT_DAYS:
            return  # not enough data yet

        all_starved = all(
            (r.get("buy_rec_count") or 0) / (r.get("buy_signal_count") or 1)
            < _SURVIVAL_RATE_THRESHOLD
            for r in rows
        )

        if all_starved:
            total_signals = sum(r.get("buy_signal_count") or 0 for r in rows)
            total_recs = sum(r.get("buy_rec_count") or 0 for r in rows)
            send_telegram_error(
                f"[PIPELINE HEALTH] BUY survival rate < 5% for "
                f"{_SURVIVAL_ALERT_DAYS} consecutive days. "
                f"{total_signals} BUY signals produced, {total_recs} reached "
                f"recommendations. Possible compounding gate regression."
            )
            logger.warning(
                "BUY survival alert: %d signals → %d recs over %d days",
                total_signals,
                total_recs,
                _SURVIVAL_ALERT_DAYS,
            )
    except Exception as exc:
        logger.warning("BUY survival rate check failed: %s", exc)
