"""Revision-time pick generation — morning BUYs + catalyst-added BUYs.

Extracted from ``phase_catalyst_revision`` to keep that module under the
300-line cap. The helpers here own the DEF-005 fix: catalyst revision may
now emit fresh BUY picks for held/watched tickers named by HIGH/MEDIUM
POSITIVE catalysts, subject to the per-ticker R:R gate. Universe bound
(``holdings ∪ watchlist``) and impact/confidence eligibility are enforced
in ``select_catalyst_candidates``; this module wires them together.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from agents.tools.technicals import (
    compute_setup_from_levels,
    get_batch_ticker_data_async,
    is_structural_uptrend,
)
from pipeline.types import GeopoliticalShockDict
from shared.neon.portfolio import get_portfolio_holdings
from shared.neon.watchlist import load_all_watchlist_tickers
from shared.observability import log_info, log_warn
from shared.rules.catalyst_candidates import select_catalyst_candidates
from shared.rules.catalyst_override import (
    CatalystBoost,
    CatalystInput,
    count_high_positive_per_ticker,
)
from shared.rules.entry_gates import check_candidate_gate, is_stacked_shock_relief
from shared.rules.exit_strategy import read_rr
from shared.rules.geopolitical import derive_shock_affected_tickers
from shared.rules.recommendation_gate import RecommendationGateDecision

logger = logging.getLogger(__name__)

# Minimum position VND for a revision-generated BUY. Small enough that
# normal setups always pass; primarily filters out pathological micro-sized
# positions that would slip through compute_setup_from_levels when a stock
# trades at extreme prices.
_MIN_POSITION_VND: int = 500_000

# Hard ceiling on how many candidate tickers revision fans out to. Bounds
# the technicals fetch during revision so we stay well inside the revision
# budget. The set is always ⊆ (held ∪ watched).
_MAX_CANDIDATES: int = 15

# Fetch timeout for the per-candidate technicals call. On timeout we fall
# back to an empty candidate set (fail-closed — no new BUY emitted).
_TECHNICALS_FETCH_TIMEOUT_SECONDS: float = 30.0


def recs_to_picks(recommendations: list[dict]) -> list[dict]:
    """Convert morning DB recommendations to AlertPick dicts for re-registration."""
    picks: list[dict] = []
    for rec in recommendations:
        entry = rec.get("entry_price")
        stop = rec.get("stop_price")
        target = rec.get("target_price")
        risk_reward = rec.get("risk_reward")
        action = rec.get("action") or "BUY"

        if action not in ("BUY", "DIP_BUY"):
            continue
        if entry is None or stop is None or target is None or risk_reward is None:
            continue

        picks.append(
            {
                "ticker": rec["ticker"],
                "entry": float(entry),
                "stop": float(stop),
                "target": float(target),
                "risk_reward": float(risk_reward),
                "strategy": rec.get("strategy") or "",
                "sector": rec.get("section") or "",
                "action": action,
                "source": rec.get("source") or "morning_brief",
            }
        )
    return picks


async def _load_universe(
    scan_date: date,
) -> tuple[set[str], set[str]] | None:
    """Load (holdings, watchlist) sets; return None on failure (fail-closed)."""
    try:
        holdings_rows, watchlist_tickers = await asyncio.gather(
            get_portfolio_holdings(),
            load_all_watchlist_tickers(),
        )
    except Exception as exc:
        logger.warning(
            "Revision universe fetch failed — falling back to morning-only picks: %s",
            exc,
            exc_info=True,
        )
        log_warn(
            "catalyst_revision_universe_fetch_failed",
            scan_date=str(scan_date),
            error=str(exc),
        )
        # Fail-closed in prod (return None → morning-only picks); fail-loud
        # in dev so unexpected fetch errors surface immediately.
        if os.environ.get("SWINGY_ENV") != "production":
            raise
        return None

    holdings_tickers = {
        (row.get("ticker") or "").upper() for row in (holdings_rows or []) if row.get("ticker")
    }
    return holdings_tickers, watchlist_tickers


def _build_pick_from_setup(
    *,
    ticker: str,
    setup: dict,
    tech: dict,
    catalyst_key: str,
) -> dict:
    """Shape a revision-generated pick dict for register_picks_as_alerts."""
    return {
        "ticker": ticker,
        "entry": float(setup["entry"]),
        "stop": float(setup["stop"]),
        "target": float(setup["target"]),
        "risk_reward": float(setup["risk_reward"]),
        "strategy": "CATALYST_REVISION",
        "sector": tech.get("sector") or "",
        "action": "BUY",
        "source": "catalyst_revision",
        "catalyst_key": catalyst_key,
    }


def _emit_picks_generated(
    *,
    scan_date: date,
    morning_count: int,
    catalyst_count: int,
    gate_rejected: int,
    skipped_no_technicals: int,
    candidate_pool_size: int,
    **extra: object,
) -> None:
    """Emit the structured Logfire event `catalyst_revision_picks_generated`.

    Single source of truth for the event's field shape. Field names are
    load-bearing for /pipeline-review regression cross-check — funnel every
    return path through here.
    """
    log_info(
        "catalyst_revision_picks_generated",
        scan_date=str(scan_date),
        morning_count=morning_count,
        catalyst_count=catalyst_count,
        gate_rejected_count=gate_rejected,
        skipped_no_technicals=skipped_no_technicals,
        candidate_pool_size=candidate_pool_size,
        **extra,
    )


async def generate_revision_picks(
    scan_date: date,
    morning_recs: list[dict],
    changed_catalysts: list[dict],
    rec_gate: RecommendationGateDecision,
    catalyst_boost: dict[str, CatalystBoost],
    risk_regime: str | None = None,
    *,
    active_catalysts: list[CatalystInput] | None = None,
    geopolitical_shock: GeopoliticalShockDict | None = None,
    holdings_tickers: set[str] | None = None,
    watchlist_tickers: set[str] | None = None,
) -> list[dict]:
    """Generate the revision-time pick list — morning BUYs + catalyst BUYs.

    The core DEF-005 fix. Revision previously seeded picks from
    ``recs_to_picks(morning_recs)`` only; when morning produced 0 BUYs the
    revision inherited 0 by construction regardless of how bullish an
    intraday catalyst was. This helper:

    1. Keeps every morning BUY (dedup key = ticker).
    2. Selects HIGH/MEDIUM POSITIVE catalyst × ticker pairs bounded to
       ``holdings ∪ watchlist`` — the tradable universe never widens.
    3. Batch-fetches technicals for the candidate set and runs
       ``check_candidate_gate`` with a per-ticker catalyst R:R discount.
    4. Emits structured Logfire events so /pipeline-review cross-check
       can auto-bump the matching Linear issue once clean runs accrue.
    """
    morning_picks = recs_to_picks(morning_recs)
    morning_tickers = {pick["ticker"].upper() for pick in morning_picks}

    # Universe injection (2026-04-27 simplify): the revision-phase caller
    # already loaded holdings + watchlist for the L1 composer call. Reuse
    # those sets to avoid a duplicate Neon round-trip. Fall back to a
    # local fetch when the caller didn't inject them (direct test callers).
    if holdings_tickers is None or watchlist_tickers is None:
        universe = await _load_universe(scan_date)
        if universe is None:
            return morning_picks
        holdings_tickers, watchlist_tickers = universe

    # Macro-blanket fan-out onto the tradable universe — a separate dict so
    # per-ticker explicit boosts always win the max() below
    # (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-002).
    from shared.rules.catalyst_override import get_macro_blanket_boosts

    trade_universe = sorted(holdings_tickers | watchlist_tickers)
    macro_blanket_boosts: dict[str, CatalystBoost] = (
        get_macro_blanket_boosts(active_catalysts, trade_universe) if active_catalysts else {}
    )

    # SWI-19 (2026-04-27): seed the candidate selector with the union of
    # changed catalysts ∪ active catalysts. Pre-fix, only `changed_catalysts`
    # fed the selector — a HIGH/POSITIVE fuel-tax catalyst discovered
    # yesterday and unchanged today produced 0 candidates because revision
    # only looked at *today's* changes. Caller-side dedup keeps the
    # selector signature stable and lets the param name follow up in a
    # rename ticket. Active rows whose `catalyst_key` is already in
    # `changed_catalysts` are skipped to avoid double-counting.
    changed_catalyst_keys: set[str] = {
        str(c.get("catalyst_key") or c.get("id") or "") for c in (changed_catalysts or [])
    }
    active_only_seeds: list[dict] = []
    for catalyst in active_catalysts or []:
        key = str(catalyst.get("catalyst_key") or "")
        if key and key not in changed_catalyst_keys:
            # CatalystInput is a TypedDict; cast to dict so the selector
            # accepts the row alongside the changed-catalyst dicts.
            active_only_seeds.append(dict(catalyst))
    seeds = list(changed_catalysts or []) + active_only_seeds

    candidates = select_catalyst_candidates(
        changed_catalysts=seeds,
        holdings_tickers=holdings_tickers,
        watchlist_tickers=watchlist_tickers,
    )
    candidates = [c for c in candidates if c["ticker"] not in morning_tickers]
    if len(candidates) > _MAX_CANDIDATES:
        candidates = candidates[:_MAX_CANDIDATES]

    # L2 (2026-04-27): per-ticker stacked-shock relief inputs. Computed
    # once before the loop so each candidate iteration is O(1).
    shock_affected = derive_shock_affected_tickers(geopolitical_shock)
    candidate_ticker_set = {c["ticker"] for c in candidates}
    high_positive_count = (
        count_high_positive_per_ticker(active_catalysts, candidate_ticker_set)
        if active_catalysts and shock_affected
        else {}
    )

    if not candidates:
        _emit_picks_generated(
            scan_date=scan_date,
            morning_count=len(morning_picks),
            catalyst_count=0,
            gate_rejected=0,
            skipped_no_technicals=0,
            candidate_pool_size=0,
        )
        return morning_picks

    candidate_tickers = [c["ticker"] for c in candidates]
    try:
        technicals = await asyncio.wait_for(
            get_batch_ticker_data_async(
                candidate_tickers,
                scan_date,
                risk_regime=risk_regime,
            ),
            timeout=_TECHNICALS_FETCH_TIMEOUT_SECONDS,
        )
    except (TimeoutError, Exception) as exc:
        logger.warning(
            "Revision technicals fetch failed for %s — fail-closed to 0 catalyst picks: %s",
            candidate_tickers,
            exc,
            exc_info=True,
        )
        log_warn(
            "catalyst_revision_technicals_fetch_failed",
            scan_date=str(scan_date),
            candidate_tickers=candidate_tickers,
            error=str(exc),
        )
        _emit_picks_generated(
            scan_date=scan_date,
            morning_count=len(morning_picks),
            catalyst_count=0,
            gate_rejected=0,
            skipped_no_technicals=len(candidate_tickers),
            candidate_pool_size=len(candidates),
        )
        return morning_picks

    new_picks: list[dict] = []
    gate_rejected = 0
    skipped_no_technicals = 0
    for candidate in candidates:
        ticker = candidate["ticker"]
        tech = technicals.get(ticker) or {}
        if not tech or "error" in tech:
            skipped_no_technicals += 1
            log_info(
                "catalyst_revision_pick_rejected",
                scan_date=str(scan_date),
                ticker=ticker,
                reason="no_technicals",
                catalyst_key=candidate["catalyst_key"],
            )
            continue

        levels = tech.get("levels") or {}
        close = tech.get("close") or 0
        if not levels or not close:
            skipped_no_technicals += 1
            log_info(
                "catalyst_revision_pick_rejected",
                scan_date=str(scan_date),
                ticker=ticker,
                reason="missing_levels_or_close",
                catalyst_key=candidate["catalyst_key"],
            )
            continue

        setup = compute_setup_from_levels(
            levels=levels,
            close=close,
            ticker=ticker,
            structural_uptrend=is_structural_uptrend(tech),
            atr=tech.get("atr"),
            risk_regime=risk_regime,
        )

        # Per-ticker boost wins over macro-blanket (plan: explicit > blanket).
        # Macro-blanket magnitude (0.25/0.125 by confidence) is inherently
        # smaller than the per-ticker 0.5/0.25, so the max() is usually the
        # explicit boost — but keeping both in the max() preserves the
        # correct ordering even if per-ticker data is missing.
        per_ticker_delta = float(
            (catalyst_boost.get(ticker) or {}).get("rr_floor_adjustment") or 0.0
        )
        macro_delta = float(
            ((macro_blanket_boosts or {}).get(ticker) or {}).get("rr_floor_adjustment") or 0.0
        )
        rr_delta = max(per_ticker_delta, macro_delta)
        # L2 (2026-04-27): per-ticker stacked-shock relief — fires only
        # when ticker is shock-affected AND has ≥2 HIGH/MEDIUM POSITIVE
        # catalysts stacked. Other candidates same iteration pass False —
        # no fleet-wide leak.
        gate = check_candidate_gate(
            trade_setup=setup,
            rr_floor=rec_gate.effective_rr_floor,
            sizing_floor_vnd=_MIN_POSITION_VND,
            catalyst_rr_adjustment=rr_delta,
            stacked_shock_relief=is_stacked_shock_relief(
                ticker, shock_affected, high_positive_count
            ),
        )
        if not gate["passed"]:
            gate_rejected += 1
            log_info(
                "catalyst_revision_pick_rejected",
                scan_date=str(scan_date),
                ticker=ticker,
                reason=gate["reason"],
                effective_rr_floor=gate["effective_rr_floor"],
                # setup_rr is a diagnostic log field; trailing setups (read_rr → None)
                # are coerced to 0.0 here only for the log line — the gate decision
                # itself runs above on the original setup with full None awareness.
                setup_rr=float(read_rr(setup) or 0.0),
                catalyst_key=candidate["catalyst_key"],
            )
            continue

        new_picks.append(
            _build_pick_from_setup(
                ticker=ticker,
                setup=setup,
                tech=tech,
                catalyst_key=candidate["catalyst_key"],
            )
        )

    max_new_entries = rec_gate.max_new_entries if rec_gate.entries_allowed else 0
    combined = morning_picks + new_picks
    if max_new_entries > 0 and len(combined) > max_new_entries:
        trimmed = combined[:max_new_entries]
        new_picks_trimmed = len(combined) - len(trimmed)
        combined = trimmed
    else:
        new_picks_trimmed = 0

    _emit_picks_generated(
        scan_date=scan_date,
        morning_count=len(morning_picks),
        catalyst_count=len(new_picks),
        gate_rejected=gate_rejected,
        skipped_no_technicals=skipped_no_technicals,
        candidate_pool_size=len(candidates),
        trimmed_by_max_entries=new_picks_trimmed,
        effective_rr_floor=rec_gate.effective_rr_floor,
    )

    return combined


__all__ = ["recs_to_picks", "generate_revision_picks"]
