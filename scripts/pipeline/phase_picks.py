"""Phase 3b: Pre-compute top picks from sector BUY signals (deterministic R:R)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from agents.picks import extract_top_picks
from agents.screening import screen_buy_signals
from agents.tools.portfolio import get_position_scale_factor
from agents.tools.validation import validate_sector_signals
from pipeline.types import GeopoliticalShockDict
from shared.errors import report_caught
from shared.neon import get_latest_aggregated_beliefs
from shared.observability import log_warn
from shared.rules.catalyst_override import CatalystInput
from shared.rules.scoring import ScoringPhase
from shared.trading_config import get_trading_config

if TYPE_CHECKING:
    from eval.score_recorder import ScoreRecorder

logger = logging.getLogger(__name__)


def _build_belief_fallback_signal(ticker: str, belief: dict | None) -> dict:
    """Synthesize a BUY signal dict for a belief-promoted ticker."""
    belief = belief or {}
    return {
        "ticker": ticker,
        "signal": "BUY",
        "sector": belief.get("ensemble_type") or "BELIEF_FALLBACK",
        "note": (
            belief.get("belief_narrative")
            or "BULLISH aggregator belief — promoted via belief fallback"
        ),
        "confidence": belief.get("conviction") or "MEDIUM",
        "source": "belief_fallback",
    }


def _log_catalyst_boost_dropped(
    catalyst_boosted_tickers: set[str] | None,
    screened_signals: list[dict],
    picks: list[dict],
    scan_date,
) -> None:
    """Log when catalyst-boosted tickers produced no pick.

    Surfaces the "boost-dropped" case: sector agents didn't emit BUY for
    boosted tickers, or picks validator filtered them. Helps diagnose
    "catalyst active but never reached picks" regressions.
    """
    if not catalyst_boosted_tickers:
        return
    boost_set_upper = {t.upper() for t in catalyst_boosted_tickers}
    pick_tickers = {(p.get("ticker") or "").upper() for p in picks}
    boosted_without_pick = boost_set_upper - pick_tickers
    if not boosted_without_pick:
        return
    boosted_buy_signals = {
        signal_ticker_upper
        for s in screened_signals
        for signal_ticker_upper in [(s.get("ticker") or "").upper()]
        if (s.get("signal") or "").upper() == "BUY" and signal_ticker_upper in boost_set_upper
    }
    no_buy = boosted_without_pick - boosted_buy_signals
    had_buy_but_filtered = boosted_without_pick - no_buy
    log_warn(
        "catalyst_boost_dropped",
        boosted_no_pick=sorted(no_buy),
        boosted_filtered=sorted(had_buy_but_filtered),
        scan_date=str(scan_date),
    )


async def compute_top_picks(
    sector_signals: list[dict],
    scan_date,
    technicals: list | dict,
    sector_rotation: dict | None,
    holdings_tickers: list[str],
    deterministic_beliefs: list[dict] | None = None,
    min_rr: float = 2.5,
    max_picks: int = 3,
    risk_regime: str | None = None,
    catalyst_boosted_tickers: set[str] | None = None,
    belief_boosted_tickers: set[str] | None = None,
    *,
    active_catalysts: Sequence[CatalystInput] | None = None,
    geopolitical_shock: GeopoliticalShockDict | None = None,
    # SWI-171 Phase A audit context. Optional so tests / ad-hoc CLI
    # callers don't have to wire it.
    score_recorder: ScoreRecorder | None = None,
    score_phase: ScoringPhase = "morning",
    audit_context: dict | None = None,
) -> list[dict]:
    """Validate sector signals and extract top picks with deterministic R:R.

    Args:
        deterministic_beliefs: Pre-computed aggregated beliefs (from phase_beliefs.py),
            passed in-memory to avoid DB round-trip.
        risk_regime: Global risk regime — threaded to trade-setup computation
            for regime-scaled target multiples.
        catalyst_boosted_tickers: Set of tickers with active positive catalysts
            (from Phase 0 `ctx.catalyst_boosted`). Threaded into strategy
            classifier so MEAN_REVERSION promotions to MOMENTUM fire for
            catalyst-active names.
        belief_boosted_tickers: Set of tickers with BULLISH aggregator beliefs
            but no sector BUY signal (e.g. sector agent hung). Promoted into
            the candidate pool so a sector-starvation morning can still emit
            picks; screen + trade-setup gates still apply.

    Returns list of pre-computed pick dicts.
    """
    if not sector_signals and not belief_boosted_tickers:
        return []

    # Normalize technicals to dict (used by validation + logging below)
    tech_dict = (
        {row["ticker"]: row for row in technicals} if isinstance(technicals, list) else technicals
    )

    # Merge belief-boosted tickers into sector_signals as synthetic BUY entries
    # so they flow through ONE screen_buy_signals + extract_top_picks path.
    # The set itself is also passed through so final picks can be tagged
    # with source="belief_fallback".
    sector_signals = list(sector_signals or [])
    if belief_boosted_tickers:
        existing_buy_tickers = {
            (s.get("ticker") or "").upper()
            for s in sector_signals
            if (s.get("signal") or "").upper() == "BUY"
        }
        belief_lookup: dict[str, dict] = {
            (b.get("ticker") or "").upper(): b for b in (deterministic_beliefs or [])
        }
        for ticker in sorted(belief_boosted_tickers - existing_buy_tickers):
            sector_signals.append(_build_belief_fallback_signal(ticker, belief_lookup.get(ticker)))

    # Validate sector signals against data quality (non-fatal)
    try:
        flagged = validate_sector_signals(
            signals=sector_signals,
            technicals=tech_dict,
            rotation=sector_rotation,
        )
        if flagged:
            print(f"  [Validation] {len(flagged)} BUY signals flagged:", flush=True)
            for f in flagged:
                print(f"    {f['ticker']}: {', '.join(f['issues'])}", flush=True)
    except Exception as e:
        report_caught("phase_picks.validate_sector_signals", e)

    print("\n  Pre-computing top picks from sector BUY signals...", flush=True)

    # Fundamental quality pre-filter (deterministic, before any trade setup computation)
    screened_signals, rejected_signals = await screen_buy_signals(
        sector_signals, get_trading_config()
    )
    if rejected_signals:
        print(f"  [Screen] Filtered out {len(rejected_signals)} BUY signal(s):", flush=True)
        for r in rejected_signals:
            print(f"    {r['ticker']}: {r['rejection_reason']}", flush=True)

    scale_data = await get_position_scale_factor()
    scale_factor = scale_data.get("scale_factor", 1.0)

    # Use in-memory deterministic beliefs if available, else fetch from DB
    beliefs_by_ticker: dict[str, dict] = {}
    try:
        if deterministic_beliefs:
            beliefs_by_ticker = {b["ticker"]: b for b in deterministic_beliefs}
        else:
            aggregated_beliefs = await get_latest_aggregated_beliefs(
                scan_date, "deterministic_sector"
            )
            if not aggregated_beliefs:
                aggregated_beliefs = await get_latest_aggregated_beliefs(scan_date, "sector")
            beliefs_by_ticker = {b["ticker"]: b for b in aggregated_beliefs}
        if beliefs_by_ticker:
            print(f"  [Beliefs] {len(beliefs_by_ticker)} ticker beliefs for sizing", flush=True)
    except Exception as e:
        logger.warning("Failed to fetch beliefs for picks (non-fatal): %s", e)

    picks = await extract_top_picks(
        sector_signals=screened_signals,
        scan_date=scan_date,
        min_rr=min_rr,
        max_picks=max_picks,
        scale_factor=scale_factor,
        exclude_tickers=holdings_tickers,
        beliefs_by_ticker=beliefs_by_ticker or None,
        risk_regime=risk_regime,
        catalyst_boosted_tickers=catalyst_boosted_tickers,
        belief_boosted_tickers=belief_boosted_tickers,
        active_catalysts=active_catalysts,
        geopolitical_shock=geopolitical_shock,
        score_recorder=score_recorder,
        score_phase=score_phase,
        audit_context=audit_context,
    )
    buy_count = sum(1 for s in screened_signals if s.get("signal") == "BUY")
    print(
        f"  Sector BUY signals: {buy_count}, validated picks: {len(picks)}",
        flush=True,
    )

    _log_catalyst_boost_dropped(catalyst_boosted_tickers, screened_signals, picks, scan_date)

    # Log non-BUY signals that had valid R:R — potential missed entries
    for signal in sector_signals:
        if (signal.get("signal") or "").upper() == "BUY":
            continue
        signal_ticker = signal.get("ticker", "").upper()
        tech = (tech_dict or {}).get(signal_ticker, {})
        setup = tech.get("trade_setup") or {}
        if setup.get("valid") and setup.get("risk_reward"):
            logger.info(
                "sector_filter: %s got %s signal despite valid R:R %.1f — potential missed entry",
                signal_ticker,
                signal.get("signal"),
                setup.get("risk_reward"),
            )
    for p in picks:
        rr_display = f"{p['risk_reward']:.1f}" if p["risk_reward"] is not None else "ATR_TRAIL"
        print(
            f"    {p['ticker']}: R:R {rr_display}, {p['shares']} shares",
            flush=True,
        )

    return picks
