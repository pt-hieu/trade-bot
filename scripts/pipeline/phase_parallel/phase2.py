"""Phase 2 — sector analysts + long-term + positions ensemble in parallel."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agents import (
    analyze_longterm_with_agent,
    analyze_sector_with_agent,
    monitor_positions_ensemble,
)
from shared.errors import report_caught

from ..sector_utils import merge_split_sector_results, split_sectors
from ..types import Phase2Result, Phase2SectorsCompleteCheckpoint, PhaseHealth
from .utils import _collect_sector_outputs, _run_with_semaphore

if TYPE_CHECKING:
    from pipeline.enrichment_loader import EnrichmentData
    from shared.rules.catalyst_override import CatalystBoost, CatalystInput


async def run_phase2_parallel(
    scan_date,
    sectors: dict,
    trailing_stops_context: str = "",
    sector_rotation: dict | None = None,
    entries_allowed: bool = True,
    workflow_config: dict | None = None,
    market_regime: str = "CAUTIOUS",
    global_risk_regime: str = "CAUTIOUS",
    geopolitical_context: str = "",
    holdings: list | None = None,
    cash_balance: float = 0.0,
    deployable_cash: float = 0.0,
    market_level_dict: dict | None = None,
    macro_metrics_dict: dict | None = None,
    technicals: dict | None = None,
    enrichment_data: EnrichmentData | None = None,
    commodity_prices: dict | None = None,
    market_valuation: dict | None = None,
    vn_economy: dict | None = None,
    catalyst_boosted: dict[str, CatalystBoost] | None = None,
    active_catalysts: list[CatalystInput] | None = None,
) -> Phase2Result:
    """Phase 2: Run sector analysis + position monitor + long-term in parallel."""
    print("\n" + "=" * 60, flush=True)
    print("PHASE 2: Sector Analysis + Holdings (Parallel)", flush=True)
    if not entries_allowed:
        print(
            "  [CASH GATE] entries_allowed=False — sector agents will not produce BUY signals",
            flush=True,
        )
    print("=" * 60, flush=True)

    wf = workflow_config or {}

    from pipeline.context_blocks import format_articles_block

    sector_articles_context = ""
    if enrichment_data and enrichment_data.articles:
        sector_articles_context = format_articles_block(enrichment_data.articles)

    split = split_sectors(sectors)

    phase2a_tasks = []

    for name, tickers in split.items():

        async def analyze_sector(n=name, t=tickers):
            return await analyze_sector_with_agent(
                n,
                t,
                scan_date,
                entries_allowed=entries_allowed,
                market_regime=market_regime,
                global_risk_regime=global_risk_regime,
                geopolitical_context=geopolitical_context,
                market_level_dict=market_level_dict,
                macro_metrics_dict=macro_metrics_dict,
                technicals=technicals,
                enrichment_data=enrichment_data,
                articles_context=sector_articles_context,
                commodity_prices=commodity_prices,
                market_valuation=market_valuation,
                catalyst_boosted=catalyst_boosted,
                active_catalysts=active_catalysts,
            )

        phase2a_tasks.append(_run_with_semaphore(analyze_sector(), f"sector_{name}"))

    if wf.get("run_longterm", True):
        from pipeline.context_blocks import format_regime_block

        longterm_regime_context = format_regime_block(
            market_level_dict, macro_metrics_dict, market_valuation=market_valuation
        )
        from pipeline.context_blocks import format_vn_economy_block

        longterm_vn_economy = format_vn_economy_block(vn_economy)
        phase2a_tasks.append(
            _run_with_semaphore(
                analyze_longterm_with_agent(
                    scan_date,
                    geopolitical_context=geopolitical_context,
                    regime_context=longterm_regime_context,
                    vn_economy_context=longterm_vn_economy,
                ),
                "longterm",
            )
        )
    else:
        print("  [Meta-Controller] Skipping longterm analysis", flush=True)

    print(
        f"  Phase 2a: running {len(phase2a_tasks)} sector+longterm agent(s) in parallel...",
        flush=True,
    )

    phase2a_results = await asyncio.gather(*[t for t in phase2a_tasks])
    results_dict: dict[str, Any] = dict(phase2a_results)

    if wf.get("run_positions", True):
        merged_for_ckpt = merge_split_sector_results(results_dict, sectors, split)
        (
            ckpt_sector_results,
            ckpt_sector_signals,
            ckpt_sector_beliefs,
            ckpt_failed_sector_count,
        ) = _collect_sector_outputs(sectors, merged_for_ckpt, verbose=False)
        longterm_raw = results_dict.get("longterm")
        ckpt_longterm = longterm_raw if not isinstance(longterm_raw, Exception) else None
        ckpt_failed_names = [
            f"sector_{n}"
            for n in sectors
            if isinstance(merged_for_ckpt.get(n), (Exception, type(None)))
        ]
        if isinstance(results_dict.get("longterm"), Exception):
            ckpt_failed_names.append("longterm")
        ckpt_total = len(sectors) + (1 if wf.get("run_longterm", True) else 0)
        ckpt_health = PhaseHealth(
            total_agents=ckpt_total,
            failed_agents=len(ckpt_failed_names),
            failed_names=ckpt_failed_names,
        )
        ckpt = Phase2SectorsCompleteCheckpoint(
            sector_results=ckpt_sector_results,
            sector_signals=ckpt_sector_signals,
            sector_beliefs=ckpt_sector_beliefs,
            failed_sector_count=ckpt_failed_sector_count,
            longterm=ckpt_longterm if isinstance(ckpt_longterm, str) else None,
            health=ckpt_health,
        )
        try:
            from shared.neon.checkpoints import save_checkpoint

            saved = await save_checkpoint(
                scan_date=scan_date,
                phase="phase2_sectors_complete",
                data=ckpt.to_dict(),
                failed_sector_count=ckpt_failed_sector_count,
                total_sector_count=len(sectors),
            )
            if saved:
                print(
                    "  Phase 2a checkpoint saved (sectors+longterm complete, positions pending)",
                    flush=True,
                )
        except Exception as checkpoint_error:
            report_caught("phase2.sectors_complete_checkpoint", checkpoint_error)

        print("  Phase 2b: running positions ensemble...", flush=True)
        positions_pair = await _run_with_semaphore(
            monitor_positions_ensemble(
                scan_date,
                trailing_stops_context,
                sector_rotation,
                geopolitical_context,
                holdings=holdings,
                cash_balance=cash_balance,
                deployable_cash=deployable_cash,
                market_level_dict=market_level_dict,
                macro_metrics_dict=macro_metrics_dict,
                technicals=technicals,
                enrichment_data=enrichment_data,
                market_valuation=market_valuation,
                commodity_prices=commodity_prices,
            ),
            "positions",
        )
        results_dict[positions_pair[0]] = positions_pair[1]
    else:
        print("  [Meta-Controller] Skipping position monitor", flush=True)

    merged = merge_split_sector_results(results_dict, sectors, split)

    sector_results, sector_signals, sector_beliefs, failed_sector_count = _collect_sector_outputs(
        sectors, merged, verbose=True
    )

    longterm = results_dict.get("longterm")
    if isinstance(longterm, Exception):
        longterm = f"Long-term analysis failed: {longterm}"
        print("  [longterm] FAILED", flush=True)
    else:
        print("  [longterm] OK", flush=True)

    positions = results_dict.get("positions")
    if isinstance(positions, Exception):
        import logging as _logging

        _logging.getLogger(__name__).error(
            "Positions ensemble raised %s — dict-coerced; per-ticker coverage gate decides loud-fail.",
            positions,
        )
        positions = {"alerts": [], "summary": str(positions)}
        print("  [positions] FAILED", flush=True)
    else:
        print("  [positions] OK", flush=True)

    position_beliefs = []
    if isinstance(positions, dict):
        position_beliefs = positions.get("beliefs", [])

    phase2_failed_names = [
        f"sector_{n}" for n in sectors if isinstance(merged.get(n), (Exception, type(None)))
    ]
    if isinstance(results_dict.get("longterm"), Exception):
        phase2_failed_names.append("longterm")
    if isinstance(results_dict.get("positions"), Exception):
        phase2_failed_names.append("positions")
    phase2_total = (
        len(sectors)
        + (1 if "longterm" in results_dict else 0)
        + (1 if "positions" in results_dict else 0)
    )
    phase2_health = PhaseHealth(
        total_agents=phase2_total,
        failed_agents=len(phase2_failed_names),
        failed_names=phase2_failed_names,
    )

    if len(sectors) > 0 and failed_sector_count >= len(sectors):
        raise RuntimeError(
            f"Phase 2 collapsed: {failed_sector_count}/{len(sectors)} sectors "
            f"produced no signals ({', '.join(phase2_failed_names[:8])}). "
            f"Aborting — empty sector_signals cannot feed synthesis."
        )

    from pipeline.phase_parallel_health import (
        apply_aggregator_only_gate,
        emit_partial_failure_span,
    )

    failed_sector_only_names = [n for n in phase2_failed_names if n.startswith("sector_")]
    emit_partial_failure_span(
        scan_date=str(scan_date),
        failed_sector_count=failed_sector_count,
        total_sectors=len(sectors),
        failed_sector_names=failed_sector_only_names,
    )
    apply_aggregator_only_gate(
        phase2_health=phase2_health,
        scan_date=str(scan_date),
        failed_sector_count=failed_sector_count,
        total_sectors=len(sectors),
        failed_sector_names=failed_sector_only_names,
    )

    return Phase2Result(
        sector_results=sector_results,
        sector_signals=sector_signals,
        position_alerts=positions if isinstance(positions, dict) else {"alerts": []},
        sector_beliefs=sector_beliefs,
        position_beliefs=position_beliefs,
        failed_sector_count=failed_sector_count,
        health=phase2_health,
    )
