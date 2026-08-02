"""Phase resume: load cached Phase 1+2 data and re-derive intermediates."""

import asyncio
import logging
from datetime import date

from agents.tools.geopolitical import build_geopolitical_context
from shared.api.technicals import get_technicals
from shared.neon import get_foreign_flow, get_macro_metrics, get_market_regime

from .helpers import derive_intermediates, load_sector_rotation
from .trailing_stops import compute_and_persist_trailing_stops
from .types import (
    Phase1Result,
    Phase2Result,
    Phase2SectorsCompleteCheckpoint,
    PhaseIntermediates,
    PipelineContext,
)

logger = logging.getLogger(__name__)


async def load_resume_data(
    scan_date: date,
    holdings: list,
    ctx: PipelineContext,
    sectors: dict,
    deployable_cash: float,
) -> tuple[Phase1Result | None, Phase2Result | None, PhaseIntermediates | None]:
    """Load Phase 1 from DB + Phase 2 from checkpoint, re-derive intermediates.

    Returns (phase1_results, phase2_results, intermediates).
    Returns (None, None, None) if resume data unavailable.
    """
    from shared.neon.checkpoints import load_checkpoint

    checkpoint_data = await load_checkpoint(scan_date, "phase2")
    if not checkpoint_data:
        return None, None, None

    from shared.api.commodities import get_commodity_prices
    from shared.vnstock_client import fetch_market_valuation, fetch_vn_economic_snapshot

    (
        existing_macro,
        existing_flow,
        existing_regime,
        commodity_prices,
        market_valuation,
        vn_economy,
    ) = await asyncio.gather(
        get_macro_metrics(scan_date),
        get_foreign_flow(scan_date),
        get_market_regime(scan_date),
        get_commodity_prices(),
        fetch_market_valuation(),
        fetch_vn_economic_snapshot(),
    )

    phase2_results = Phase2Result.from_dict(checkpoint_data)
    print(
        f"  [RESUME] Phase 2 checkpoint: {len(phase2_results.sector_results)} sectors, "
        f"{len(phase2_results.sector_signals)} signals",
        flush=True,
    )

    macro_metrics = existing_macro if "error" not in existing_macro else None
    foreign_flow = existing_flow if "error" not in existing_flow else None

    if macro_metrics is None:
        logger.warning("Resume: no cached macro metrics for %s — cannot resume", scan_date)
        return None, None, None

    phase1_results = Phase1Result(
        market_level=None,
        macro_metrics=macro_metrics,
        foreign_flow=foreign_flow,
        commodity_prices=commodity_prices if isinstance(commodity_prices, dict) else {},
        market_valuation=market_valuation if isinstance(market_valuation, dict) else {},
        vn_economy=vn_economy if isinstance(vn_economy, dict) else {},
    )

    # Regime from authoritative market_regimes table (not macro_metrics)
    raw_regime = (
        existing_regime.get("regime") or "CAUTIOUS"
        if isinstance(existing_regime, dict) and "error" not in existing_regime
        else "CAUTIOUS"
    )

    # Load raw data in parallel — merge held tickers for positions_technical
    from shared.watchlist import merge_holdings_into_watchlist

    merged_sectors = merge_holdings_into_watchlist(sectors, holdings or [])
    all_tickers = [ticker for tickers in merged_sectors.values() for ticker in tickers]

    async def _safe_trailing_stops():
        try:
            return await compute_and_persist_trailing_stops(holdings, scan_date)
        except Exception as trailing_error:
            logger.warning("Resume: trailing stops failed (non-fatal): %s", trailing_error)
            return ""

    sector_rotation, trailing_stops_context, technicals = await asyncio.gather(
        load_sector_rotation(scan_date, market_regime=raw_regime),
        _safe_trailing_stops(),
        get_technicals(all_tickers),
    )

    geopolitical_shock = (macro_metrics or {}).get("geopolitical_shock")
    geopolitical_context = build_geopolitical_context(geopolitical_shock)

    from agents.trading_mode import determine_mode

    intermediates = await derive_intermediates(
        raw_regime=raw_regime,
        macro_metrics=macro_metrics,
        early_mode=determine_mode(deployable_cash),
        sector_rotation=sector_rotation,
        trailing_stops_context=trailing_stops_context,
        technicals=technicals,
        geopolitical_context=geopolitical_context,
    )

    return phase1_results, phase2_results, intermediates


async def load_phase2_sectors_complete_checkpoint(
    scan_date: date,
) -> Phase2SectorsCompleteCheckpoint | None:
    """Load the Phase 2a checkpoint (sectors+longterm done, positions pending).

    Used by `--resume-from=phase2_sectors_complete`. The caller still runs
    the positions ensemble + Phase 3+ — this only avoids re-running the
    ~15-minute sector fan-out.
    """
    from shared.neon.checkpoints import load_checkpoint

    checkpoint_data = await load_checkpoint(scan_date, "phase2_sectors_complete")
    if not checkpoint_data:
        return None
    return Phase2SectorsCompleteCheckpoint.from_dict(checkpoint_data)
