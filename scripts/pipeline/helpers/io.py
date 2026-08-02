"""Async DB I/O: catalyst bundle fetch, Phase 0 load, Phase 1 persist + post-process."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import TYPE_CHECKING, cast

from shared.neon import (
    get_cash_balance,
    get_longterm_watchlist,
    get_portfolio_holdings_snapshot,
    get_swing_watchlist,
    insert_foreign_flow,
    insert_macro_metrics,
    insert_market_regime,
)

from ..types import PipelineContext
from .rules import extract_risk_regime, patch_oil_from_commodities, reconcile_regimes

if TYPE_CHECKING:
    from shared.rules.catalyst_override import CatalystBoost, CatalystInput

    from ..types import FlatTechnicalsRow, Phase1Result

logger = logging.getLogger(__name__)


async def _safe_catalyst_bundle() -> tuple[
    dict[str, CatalystBoost] | None, list[CatalystInput] | None
]:
    """Fetch active catalysts once, return (boost_set, typed_active_catalysts).

    Single DB round-trip for both payloads. Either result is `None` on
    fetch failure (fail-closed).
    """
    from shared.neon.catalyst_summaries import build_catalyst_inputs, get_active_catalysts
    from shared.rules.catalyst_override import get_catalyst_boosted_tickers

    try:
        raw_rows = await get_active_catalysts()
        typed = build_catalyst_inputs(raw_rows)
        boosts = get_catalyst_boosted_tickers(typed)
        return boosts, typed
    except Exception as exc:
        logger.warning("Catalyst bundle fetch failed in Phase 0: %s", exc, exc_info=True)
        return None, None


async def load_db_context(scan_date: date | None = None) -> PipelineContext:
    """Load all database context inside shared async pool.

    Phase 0 batch: watchlist, holdings, cash, catalyst-boosted ticker set,
    and the typed active-catalyst list.
    """
    # CRITICAL (SWI-304): rally_readmit mutates swing_watchlist.is_active and MUST
    # resolve BEFORE the gather block reads it. Do NOT move into asyncio.gather —
    # that would race writes against the get_swing_watchlist() read.
    if scan_date is not None:
        try:
            from ..phase_zero import run_rally_readmit

            await run_rally_readmit(scan_date)
        except Exception as exc:
            logger.warning("Phase 0 rally_readmit failed (non-fatal): %s", exc, exc_info=True)

    sectors, longterm, holdings_snapshot, cash, catalyst_bundle = await asyncio.gather(
        get_swing_watchlist(),
        get_longterm_watchlist(),
        get_portfolio_holdings_snapshot(),
        get_cash_balance(),
        _safe_catalyst_bundle(),
    )
    holdings = holdings_snapshot.holdings
    catalyst_boosted, active_catalysts = catalyst_bundle

    from shared.trading_config import get_trading_config

    deployable = max(0, cash - get_trading_config().min_cash_reserve)

    boost_count = len(catalyst_boosted) if catalyst_boosted else 0
    boost_tag = "unavailable" if catalyst_boosted is None else f"{boost_count} tickers"
    active_count = len(active_catalysts) if active_catalysts else 0
    print(
        f"Loaded from database: {sum(len(v) for v in sectors.values())} sectors, "
        f"{len(longterm)} long-term, {len(holdings)} holdings, "
        f"catalyst boost: {boost_tag}, active catalysts: {active_count}"
    )
    print(f"Cash: {cash:,.0f} VND (deployable: {deployable:,.0f} VND)")

    score_recorder = None
    if scan_date is not None:
        from eval.score_recorder import ScoreRecorder

        score_recorder = ScoreRecorder.for_run(scan_date)

    return PipelineContext(
        sectors=sectors,
        longterm_watchlist=longterm,
        holdings=holdings,
        holdings_snapshot_at=holdings_snapshot.snapshot_at,
        cash_balance=cash,
        deployable_cash=deployable,
        catalyst_boosted=catalyst_boosted,
        active_catalysts=active_catalysts,
        score_recorder=score_recorder,
    )


async def persist_phase1(
    scan_date,
    market_level,
    market_regime,
    macro_metrics,
    global_risk_regime,
    institutional_flow,
    vnindex_technicals: FlatTechnicalsRow | dict | None = None,
):
    """Persist Phase 1 results to database."""
    from shared.database import get_db

    db = await get_db()
    await db.execute(
        "INSERT INTO daily_scans (scan_date, status) VALUES ($1, 'in_progress') "
        "ON CONFLICT (scan_date) DO NOTHING",
        scan_date,
    )
    if market_level:
        print(f"\nMarket Regime: {market_regime} ({market_level.get('regime_confidence', 0):.0%})")
        await insert_market_regime(
            scan_date, market_level, vnindex_technicals=cast("dict | None", vnindex_technicals)
        )
    if macro_metrics and not macro_metrics.get("error"):
        print(f"Global Risk: {global_risk_regime}")
        await insert_macro_metrics(scan_date, macro_metrics)
    if institutional_flow and not institutional_flow.get("error"):
        net_value = institutional_flow.get("net_value_billion", 0)
        trend = "NET BUY" if net_value > 0 else "NET SELL" if net_value < 0 else "NEUTRAL"
        print(f"Foreign Flow: {trend} {abs(net_value):.1f}B VND")
        await insert_foreign_flow(scan_date, institutional_flow)


async def post_process_phase1(
    scan_date: date,
    phase1: Phase1Result,
    vnindex_technicals: FlatTechnicalsRow | dict | None = None,
) -> tuple[str, str, str]:
    """Post-process Phase 1: oil patch, regime extraction, geo context, persist.

    Single reconciliation point — producers run in parallel without the
    global_risk floor in their prompts; reconcile here so all downstream
    consumers (DB, entry_strategist, positions, narrative) read one value.
    """
    from agents.tools.geopolitical import build_geopolitical_context

    patch_oil_from_commodities(phase1.macro_metrics, phase1.commodity_prices)

    market_level = phase1.market_level or {}
    raw_regime = market_level.get("regime") or "CAUTIOUS"
    global_risk_regime = extract_risk_regime(phase1.macro_metrics)

    market_regime = reconcile_regimes(raw_regime, global_risk_regime)
    if phase1.market_level is not None:
        phase1.market_level["regime_raw"] = raw_regime
        phase1.market_level["regime"] = market_regime

    geopolitical_shock = (phase1.macro_metrics or {}).get("geopolitical_shock")
    geopolitical_context = build_geopolitical_context(geopolitical_shock)
    if geopolitical_context:
        geo_name = (geopolitical_shock or {}).get("phase_name", "unknown")
        print(f"  Geopolitical shock active: {geo_name}")

    await persist_phase1(
        scan_date,
        market_level=phase1.market_level,
        market_regime=market_regime,
        macro_metrics=phase1.macro_metrics,
        global_risk_regime=global_risk_regime,
        institutional_flow=phase1.foreign_flow,
        vnindex_technicals=vnindex_technicals,
    )

    return market_regime, global_risk_regime, geopolitical_context
