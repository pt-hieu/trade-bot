#!/usr/bin/env python3
"""
LLM Analysis Script — Morning Brief Generation

Multi-step sector analysis with parallel execution:
1. Phase 1: Market Level + Macro + Foreign Flow (parallel)
2. Phase 2: Sector Analysis x6 + Long-term + Position Monitor (parallel)
3. Phase 3: Trading Mode + Top Picks + Strategy Director
4. Phase 4: Synthesis + Reflection
5. Phase 5: Alert Registration
6. Phase 6: Write Recommendations
"""

import argparse
import asyncio
import logging
import os
import time
from datetime import date, datetime

from shared.observability import (
    configure_observability,
    emit_pipeline_health_summary,
    reset_health_counters,
    shutdown_observability,
    span,
)
from shared.session import init_session

# Initialize observability early (no-op if LOGFIRE_TOKEN not set)
configure_observability()
init_session("morning")

logger = logging.getLogger(__name__)

from analysis.synthesis import save_morning_brief
from pipeline import (
    compute_and_persist_trailing_stops,
    derive_intermediates,
    determine_adaptive_workflow,
    get_market_level,
    load_db_context,
    load_sector_rotation,
    post_process_phase1,
    run_phase1_parallel,
    run_phase2_parallel,
    validate_pipeline_data,
)
from pipeline.phase_orchestration import run_phases_3_to_6
from pipeline.phase_postprocess import persist_phase2_results
from pipeline.phase_resume import (
    load_phase2_sectors_complete_checkpoint,
    load_resume_data,
)
from pipeline.types import PhaseIntermediates
from shared.api.technicals import get_technicals
from shared.config import get_research_dir, get_scan_date
from shared.rules.belief_coverage import sector_coverage_universe
from shared.telegram import send_telegram_error
from shared.trading_config import init_trading_config

TODAY = get_scan_date()
RESEARCH_DIR = get_research_dir()


def main():
    """Sync entry point."""
    parser = argparse.ArgumentParser(description="Morning brief generation")
    parser.add_argument(
        "--skip-alerts", action="store_true", help="Skip alert registration (Phase 5)"
    )
    parser.add_argument(
        "--resume-from",
        choices=["phase3", "phase2_sectors_complete"],
        help=(
            "Resume entry point. phase3 = load full Phase 2 checkpoint "
            "(skip both sector + positions ensembles). "
            "phase2_sectors_complete = load Phase 2a checkpoint (sector+longterm "
            "done) and re-run only positions ensemble + Phase 3+."
        ),
    )
    args = parser.parse_args()
    asyncio.run(_main_async(skip_alerts=args.skip_alerts, resume_from=args.resume_from))


async def _main_async(skip_alerts: bool = False, resume_from: str | None = None):
    """Async main — single event loop, shared database pool."""
    from shared.database import Database, close_db

    reset_health_counters()

    # SWI-122: nick-fields/retry@v3 silently re-runs failed jobs; without this
    # span + Telegram ping a 17min sector-timeout cascade ships zero signal.
    run_attempt = int(os.getenv("GITHUB_RUN_ATTEMPT") or 1)
    if run_attempt > 1:
        with span(
            "pipeline_retry",
            run_attempt=run_attempt,
            prior_attempt_number=run_attempt - 1,
            github_run_id=os.getenv("GITHUB_RUN_ID") or "",
            scan_date=TODAY,
        ):
            logger.warning("pipeline_retry: attempt %d for %s", run_attempt, TODAY)
        send_telegram_error(
            f"Pipeline retry #{run_attempt} for {TODAY} — investigate prior failure"
        )

    try:
        async with Database():
            await init_trading_config()
            ctx = await load_db_context(scan_date=date.fromisoformat(TODAY))
            with span("morning_brief_generation", date=TODAY) as root_span:
                try:
                    await asyncio.wait_for(
                        _run_analysis(ctx, skip_alerts=skip_alerts, resume_from=resume_from),
                        timeout=7200,
                    )
                except BaseException as exc:
                    # Capture exception inside the span so audit subagents
                    # reading the failed root trace can JOIN against the
                    # subsequent pipeline_retry span via github_run_id.
                    root_span.set_attribute("exception_type", type(exc).__name__)
                    root_span.set_attribute("exception_message", str(exc)[:500])
                    raise
    except TimeoutError:
        error_msg = "Pipeline timed out after 2 hours"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    except Exception as e:
        error_msg = f"LLM analysis failed: {e}"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    finally:
        from shared.vnstock_client import close_client

        emit_pipeline_health_summary(scan_date=TODAY, phase="morning", logger=logger)
        await close_client()
        await close_db()
        shutdown_observability()


def _enforce_health_gate(health, phase_label: str) -> None:
    """Abort pipeline if all agents in a phase failed."""
    if health and health.is_total_failure:
        error_msg = (
            f"{phase_label} TOTAL FAILURE: {health.failed_agents}/{health.total_agents} "
            f"agents crashed ({', '.join(health.failed_names[:5])}). Aborting pipeline."
        )
        logger.critical(error_msg)
        send_telegram_error(error_msg)
        raise RuntimeError(error_msg)


def _check_degraded(health) -> bool:
    """Return True and alert if phase is degraded (>50% failed)."""
    if health and health.is_degraded:
        degraded_msg = (
            f"PIPELINE DEGRADED: {health.failed_agents}/{health.total_agents} "
            f"agents failed ({', '.join(health.failed_names[:5])}). Continuing with partial data."
        )
        logger.warning(degraded_msg)
        send_telegram_error(degraded_msg)
        return True
    return False


async def _run_analysis(ctx, skip_alerts: bool = False, resume_from: str | None = None):
    """Run the full analysis pipeline (async) with parallel execution."""
    start_time = time.time()

    SECTORS = ctx.sectors
    LONGTERM_WATCHLIST = ctx.longterm_watchlist
    HOLDINGS = ctx.holdings
    DEPLOYABLE_CASH = ctx.deployable_cash
    scan_date = datetime.strptime(TODAY, "%Y-%m-%d").date()

    # Early cash gate: compute mode deterministically before any agents run
    from agents.trading_mode import determine_mode
    from shared.rules.entry_gates import determine_entry_gate

    early_mode = determine_mode(DEPLOYABLE_CASH)
    gate = determine_entry_gate(early_mode)  # pre-Phase1: no regime yet
    entries_allowed = gate.entries_allowed
    print(f"Early mode: {early_mode} | entries_allowed: {entries_allowed}")

    print(f"\n{'=' * 60}")
    print(f"LLM Analysis - {TODAY} (Parallel Execution)")
    print(f"{'=' * 60}\n")

    phase1_results = None
    phase2_results = None

    # Fetch technicals from API — merge held tickers so positions_technical gets data
    from shared.watchlist import merge_holdings_into_watchlist

    merged_sectors = merge_holdings_into_watchlist(SECTORS, HOLDINGS or [])
    all_tickers = [ticker for tickers in merged_sectors.values() for ticker in tickers]
    all_tickers_with_vnindex = ["VNINDEX"] + all_tickers
    from shared.api.prices import compute_daily_return

    technicals, vnindex_change_pct = await asyncio.gather(
        get_technicals(all_tickers_with_vnindex),
        compute_daily_return("VNINDEX"),
    )
    if not technicals:
        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        save_morning_brief(
            f"## Data Not Available\n\nNo market data for {TODAY}. "
            "Check vnstock API or wait for market hours.",
            RESEARCH_DIR,
            TODAY,
        )
        print("ERROR: No technicals from API. Saved error message to morning-brief.md")
        return
    # Attach change_pct to VNINDEX technicals for downstream persistence
    if "VNINDEX" in technicals and vnindex_change_pct is not None:
        technicals["VNINDEX"]["change_pct"] = vnindex_change_pct
    print(f"Loaded {len(technicals)} tickers from API\n", flush=True)

    # Batch-fetch enrichment data for context injection
    from pipeline.enrichment_loader import batch_fetch_enrichment

    longterm_tickers = list(LONGTERM_WATCHLIST.keys())
    with span("batch_enrichment_fetch"):
        ctx.enrichment = await batch_fetch_enrichment(
            all_tickers=all_tickers,
            scan_date=scan_date,
            holdings=HOLDINGS,
            longterm_tickers=longterm_tickers,
            longterm_watchlist=LONGTERM_WATCHLIST,
        )
    print("Enrichment batch fetch complete\n", flush=True)

    intermediates: PhaseIntermediates | None = None
    if resume_from == "phase3":
        phase1_results, phase2_results, intermediates = await load_resume_data(
            scan_date, HOLDINGS, ctx, SECTORS, DEPLOYABLE_CASH
        )
        if phase1_results and phase2_results and intermediates:
            print("\n  [RESUME] Loaded Phase 1+2 from cache/checkpoint", flush=True)
        else:
            print("  [RESUME] No checkpoint found — running full pipeline", flush=True)
            resume_from = None

    if resume_from != "phase3":
        from agents.model import check_primary_model_health

        await check_primary_model_health()

        # PHASE 1
        vnindex_technicals = technicals.get("VNINDEX")
        with span("phase1_parallel"):
            import json as _json
            from functools import partial

            from pipeline.context_blocks_calibration import (
                format_learnings_block,
                format_rotation_block,
            )
            from shared.neon import get_sector_rotation as _neon_rotation

            _ml_rotation_ctx = ""
            _ml_learnings_ctx = ""
            _prefetched_rotation = await _neon_rotation(scan_date)
            if _prefetched_rotation and "error" not in _prefetched_rotation:
                _ml_rotation_ctx = format_rotation_block(
                    _json.dumps(_prefetched_rotation, default=str)
                )
            else:
                _prefetched_rotation = None
                logger.warning(
                    "Rotation pre-fetch returned error or empty — agent gets no rotation data"
                )
            if ctx.enrichment and ctx.enrichment.learnings_cache:
                learnings_keys = []
                if ctx.enrichment.learnings_cache.get("macro_patterns"):
                    learnings_keys.append("macro_patterns")
                if ctx.enrichment.learnings_cache.get("rotation_patterns"):
                    learnings_keys.append("rotation_patterns")
                if learnings_keys:
                    _ml_learnings_ctx = format_learnings_block(
                        ctx.enrichment.learnings_cache, learnings_keys
                    )

            phase1_results = await run_phase1_parallel(
                scan_date,
                partial(
                    get_market_level,
                    vnindex_technicals=vnindex_technicals,
                    rotation_context=_ml_rotation_ctx,
                    learnings_context=_ml_learnings_ctx,
                ),
            )

        _enforce_health_gate(phase1_results.health, "PHASE 1")

        raw_regime, _, geopolitical_context = await post_process_phase1(
            scan_date, phase1_results, vnindex_technicals=vnindex_technicals
        )

        # Load sector rotation + trailing stops in parallel
        async def _safe_trailing_stops():
            try:
                return await compute_and_persist_trailing_stops(HOLDINGS, scan_date)
            except Exception as e:
                print(f"Trailing stops computation failed (non-fatal): {e}")
                return ""

        async def _resolve_sector_rotation():
            if _prefetched_rotation:
                return _prefetched_rotation
            return await load_sector_rotation(scan_date, market_regime=raw_regime)

        sector_rotation, trailing_stops_context = await asyncio.gather(
            _resolve_sector_rotation(),
            _safe_trailing_stops(),
        )

        intermediates = await derive_intermediates(
            raw_regime=raw_regime,
            macro_metrics=phase1_results.macro_metrics,
            early_mode=early_mode,
            sector_rotation=sector_rotation,
            trailing_stops_context=trailing_stops_context,
            technicals=technicals,
            geopolitical_context=geopolitical_context,
            market_level=phase1_results.market_level,
        )

        # Backfill reconciled regime into rotation for downstream agents
        if intermediates.sector_rotation and not intermediates.sector_rotation.get("market_regime"):
            intermediates.sector_rotation["market_regime"] = intermediates.market_regime
        if intermediates.sector_rotation:
            print(
                f"Sector Rotation: Hot={intermediates.sector_rotation.get('hot_sectors', [])}, "
                f"Cold={intermediates.sector_rotation.get('cold_sectors', [])}"
            )

        workflow_config, sectors_for_phase2 = determine_adaptive_workflow(
            intermediates.early_mode,
            intermediates.market_regime,
            intermediates.global_risk_regime,
            scan_date,
            DEPLOYABLE_CASH,
            SECTORS,
        )

        # Observability-only for now: log catalyst-boosted tickers that
        # have no sector assignment — future work can promote them into
        # a canonical sector bucket.
        from pipeline.sector_utils import log_catalyst_boosted_outside_watchlist

        sectors_for_phase2 = log_catalyst_boosted_outside_watchlist(
            sectors_for_phase2, ctx.catalyst_boosted
        )

        validate_pipeline_data(technicals, ctx.cash_balance, HOLDINGS, phase1_results.macro_metrics)

        # PHASE 2 — optionally skip sector fan-out via Phase 2a checkpoint
        phase2a_ckpt = None
        if resume_from == "phase2_sectors_complete":
            phase2a_ckpt = await load_phase2_sectors_complete_checkpoint(scan_date)
            if phase2a_ckpt is None:
                print(
                    "  [RESUME] No phase2_sectors_complete checkpoint — running full Phase 2",
                    flush=True,
                )
            else:
                print(
                    f"  [RESUME] Phase 2a checkpoint: "
                    f"{len(phase2a_ckpt.sector_results)} sectors, "
                    f"{len(phase2a_ckpt.sector_signals)} signals — "
                    "running positions ensemble only",
                    flush=True,
                )

        if phase2a_ckpt is not None:
            # Resume path: use cached sectors+longterm, re-run positions only.
            from agents import monitor_positions_ensemble
            from pipeline.types import Phase2Result, PhaseHealth

            with span("phase2_positions_only", resumed=True):
                try:
                    positions = await monitor_positions_ensemble(
                        scan_date,
                        intermediates.trailing_stops_context,
                        intermediates.sector_rotation,
                        intermediates.geopolitical_context,
                        holdings=HOLDINGS,
                        cash_balance=ctx.cash_balance,
                        deployable_cash=DEPLOYABLE_CASH,
                        market_level_dict=phase1_results.market_level,
                        macro_metrics_dict=phase1_results.macro_metrics,
                        technicals=technicals,
                        enrichment_data=ctx.enrichment,
                        market_valuation=phase1_results.market_valuation or None,
                        commodity_prices=phase1_results.commodity_prices or None,
                    )
                except Exception as e:
                    logger.warning("Resumed positions ensemble failed: %s", e)
                    positions = {"alerts": [], "summary": str(e)}

            position_beliefs = positions.get("beliefs", []) if isinstance(positions, dict) else []
            ckpt_failed_names = list(
                phase2a_ckpt.health.failed_names if phase2a_ckpt.health else []
            )
            ckpt_failed_count = phase2a_ckpt.health.failed_agents if phase2a_ckpt.health else 0
            ckpt_total = phase2a_ckpt.health.total_agents if phase2a_ckpt.health else 0
            if not isinstance(positions, dict) or positions.get("alerts") is None:
                ckpt_failed_names.append("positions")
                ckpt_failed_count += 1
            phase2_results = Phase2Result(
                sector_results=phase2a_ckpt.sector_results,
                sector_signals=phase2a_ckpt.sector_signals,
                position_alerts=positions if isinstance(positions, dict) else {"alerts": []},
                sector_beliefs=phase2a_ckpt.sector_beliefs,
                position_beliefs=position_beliefs,
                failed_sector_count=phase2a_ckpt.failed_sector_count,
                health=PhaseHealth(
                    total_agents=ckpt_total + 1,
                    failed_agents=ckpt_failed_count,
                    failed_names=ckpt_failed_names,
                ),
            )
        else:
            with span("phase2_parallel", sector_count=len(sectors_for_phase2)):
                phase2_results = await run_phase2_parallel(
                    scan_date,
                    sectors_for_phase2,
                    intermediates.trailing_stops_context,
                    intermediates.sector_rotation,
                    entries_allowed=intermediates.entries_allowed,
                    workflow_config=workflow_config,
                    market_regime=intermediates.market_regime,
                    global_risk_regime=intermediates.global_risk_regime,
                    geopolitical_context=intermediates.geopolitical_context,
                    holdings=HOLDINGS,
                    cash_balance=ctx.cash_balance,
                    deployable_cash=DEPLOYABLE_CASH,
                    market_level_dict=phase1_results.market_level,
                    macro_metrics_dict=phase1_results.macro_metrics,
                    technicals=technicals,
                    enrichment_data=ctx.enrichment,
                    commodity_prices=phase1_results.commodity_prices or None,
                    market_valuation=phase1_results.market_valuation or None,
                    vn_economy=phase1_results.vn_economy or None,
                    catalyst_boosted=ctx.catalyst_boosted,
                    active_catalysts=ctx.active_catalysts,
                )

    # Phase 2 health gate
    if phase1_results is None or phase2_results is None or intermediates is None:
        raise RuntimeError(
            "Pipeline failed: phase results or intermediates is None after execution"
        )
    _enforce_health_gate(phase2_results.health, "PHASE 2")
    is_degraded = _check_degraded(phase2_results.health)

    # Use sectors_for_phase2 (not merged_sectors) so the gate's "expected" set
    # excludes the holdings pseudo-sector — those tickers are fetched but never
    # analyzed, so counting them produces false coverage failures.
    expected_sector_tickers = sector_coverage_universe(sectors_for_phase2)
    expected_position_tickers = frozenset(
        h.get("ticker") for h in (HOLDINGS or []) if h.get("ticker")
    )
    deterministic_beliefs = await persist_phase2_results(
        phase2_results,
        scan_date,
        len(SECTORS),
        workflow_config=workflow_config,
        global_macro_regime=intermediates.global_risk_regime,
        expected_sector_tickers=expected_sector_tickers,
        expected_position_tickers=expected_position_tickers,
    )

    # PHASES 3-6: Trading mode, picks, advocates, synthesis, alerts, recommendations
    await run_phases_3_to_6(
        ctx,
        phase1_results,
        phase2_results,
        intermediates=intermediates,
        deterministic_beliefs=deterministic_beliefs,
        scan_date=scan_date,
        research_dir=RESEARCH_DIR,
        today_str=TODAY,
        skip_alerts=skip_alerts,
        is_degraded=is_degraded,
    )

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Analysis Complete! ({elapsed:.1f}s)")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
