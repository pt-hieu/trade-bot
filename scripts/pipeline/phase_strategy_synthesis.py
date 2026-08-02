"""Phase 3d + Phase 4: strategy director and synthesis orchestration."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from shared.neon.directives import save_strategy_directive
from shared.observability import span
from shared.telegram import send_telegram_error

from .phase_strategy import run_strategy_director
from .phase_synthesis import run_synthesis_and_reflection
from .types import InjectedContext, Phase1Result, Phase2Result, PipelineContext

if TYPE_CHECKING:
    from shared.rules.constraints import PipelineConstraints
    from shared.rules.recommendation_gate import RecommendationGateDecision

logger = logging.getLogger(__name__)


async def run_strategy_and_synthesis(
    ctx: PipelineContext,
    phase1_results: Phase1Result,
    phase2_results: Phase2Result,
    sector_results: list[str],
    position_alerts: dict,
    trading_mode: dict,
    pre_computed_picks: list[dict],
    advocate_reviews: dict,
    gated_tickers: list[dict],
    holdings_tickers: list[str],
    all_sectors_failed: bool,
    scan_date: date,
    entries_allowed: bool,
    entries_blocked_reason: str | None,
    market_regime: str,
    global_risk_regime: str,
    sector_rotation: dict | None,
    injected: InjectedContext,
    sector_signals: list[dict] | None = None,
    is_degraded: bool = False,
    pre_computed_constraints: PipelineConstraints | None = None,
    goals: list[dict] | None = None,
    cash_dict: dict | None = None,
    rolling_win_rate: float | None = None,
    expectancy_floor: float | None = None,
    min_rr_floor: float | None = None,
    gate_decision: RecommendationGateDecision | None = None,
) -> tuple[str, str]:
    """Run Phase 3d (strategy) + Phase 4 (synthesis). Returns (brief, reflection_status)."""
    position_guidance = None
    entry_strategy = None
    reflection_status = "reviewed"

    if not all_sectors_failed:
        # PHASE 3d: Strategy Director
        print("\n" + "=" * 60, flush=True)
        print("PHASE 3d: Strategy Director", flush=True)
        print("=" * 60, flush=True)

        with span("strategy_directive"):
            try:
                (
                    position_guidance,
                    entry_strategy,
                    directive_constraints,
                ) = await run_strategy_director(
                    phase1_results=phase1_results,
                    phase2_results=phase2_results,
                    trading_mode=trading_mode,
                    scan_date=scan_date,
                    pre_computed_picks=pre_computed_picks or None,
                    sector_rotation=sector_rotation,
                    injected=injected,
                    pre_computed_constraints=pre_computed_constraints,
                    goals=goals,
                    cash=cash_dict,
                    gate_decision=gate_decision,
                )
                # Persist constraints for midday enforcement
                # Entry gate already injected by compute_pipeline_constraints
                if directive_constraints is not None:
                    await save_strategy_directive(
                        scan_date,
                        f"{entry_strategy or ''}\n\n{position_guidance or ''}",
                        directive_constraints,
                    )
            except Exception as e:
                logger.warning("Strategy directive error (non-fatal): %s", e)
                print(f"  Strategy directive error (non-fatal): {e}", flush=True)

        # PHASE 4: Synthesis + Reflection
        print("\n" + "=" * 60, flush=True)
        print("PHASE 4: Synthesis + Reflection", flush=True)
        print("=" * 60, flush=True)

        with span("synthesis"):
            try:
                final_brief, reflection_status = await run_synthesis_and_reflection(
                    sector_results=sector_results,
                    position_alerts=position_alerts,
                    trading_mode=trading_mode,
                    scan_date=scan_date,
                    holdings=ctx.holdings,
                    holdings_snapshot_at=ctx.holdings_snapshot_at,
                    holdings_tickers=holdings_tickers,
                    pre_computed_picks=pre_computed_picks or None,
                    entry_strategy=entry_strategy,
                    entries_blocked_reason=entries_blocked_reason,
                    deployable_cash=ctx.deployable_cash,
                    market_regime=market_regime,
                    global_risk_regime=global_risk_regime,
                    geopolitical_context=injected.geopolitical_context,
                    position_beliefs=phase2_results.position_beliefs,
                    advocate_reviews=advocate_reviews,
                    gated_tickers=gated_tickers,
                    portfolio_context=injected.portfolio_context,
                    catalyst_context=injected.catalyst_context,
                    regime_context=injected.regime_context,
                    recent_trades_context=injected.recent_trades,
                    sector_signals=sector_signals,
                    longterm_watchlist=ctx.longterm_watchlist or None,
                    rolling_win_rate=rolling_win_rate,
                    expectancy_floor=expectancy_floor,
                    min_rr_floor=min_rr_floor,
                    geo_shock=(phase1_results.macro_metrics or {}).get("geopolitical_shock"),
                )
            except Exception as e:
                from .fallback import assemble_fallback_brief

                print(f"  Synthesis error: {e} — assembling fallback brief", flush=True)
                send_telegram_error(f"Synthesis failed: {e} — using fallback brief")
                reflection_status = "skipped_error"
                final_brief = assemble_fallback_brief(
                    sector_results=sector_results,
                    position_alerts=position_alerts,
                    trading_mode=trading_mode,
                    pre_computed_picks=pre_computed_picks,
                    market_regime=market_regime,
                    global_risk_regime=global_risk_regime,
                    deployable_cash=ctx.deployable_cash,
                )
    else:
        reflection_status = "skipped_no_data"
        final_brief = (
            f"## Morning Brief — {scan_date}\n\n"
            "**All sector analyses failed.** No actionable signals produced.\n\n"
            "Check Logfire traces for root cause. "
            "Possible causes: API down, DB connectivity, model timeout.\n"
        )
        send_telegram_error(
            f"Morning brief total failure: all {len(sector_results)} sectors crashed. "
            "No recommendations produced."
        )

    # Override to "degraded" only when synthesis succeeded but phase data was partial
    if is_degraded and reflection_status == "reviewed":
        reflection_status = "degraded"

    return final_brief, reflection_status
