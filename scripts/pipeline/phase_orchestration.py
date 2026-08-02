"""Phase 3-6 orchestration: typed phase results, parallel where safe."""

import asyncio
import logging
from datetime import date
from pathlib import Path

from shared.observability import span
from shared.rules.entry_gates import TradingMode

from .helpers import compose_gate_from_state, resolve_trading_mode
from .phase_advocate import apply_advocate_gate, run_advocate_reviews
from .phase_alerts import run_phase5_alert_pipeline
from .phase_context_builder import build_injected_context
from .phase_picks import compute_top_picks
from .phase_recommendations import run_phase6_recommendations
from .phase_strategy_synthesis import run_strategy_and_synthesis
from .types import (
    AdvocateResult,
    DeterministicBeliefs,
    InjectedContext,
    Phase1Result,
    Phase2Result,
    Phase3aResult,
    Phase3bResult,
    Phase3Result,
    PhaseIntermediates,
    PipelineContext,
    SynthesisResult,
)

logger = logging.getLogger(__name__)


async def _spanned(name: str, coro):
    """Run `coro` inside a Logfire `span(name)` context.

    Shared wrapper for per-phase instrumentation so each phase gets its own
    duration + error boundary visible in Logfire without sprinkling a
    one-shot `with span(...)` block around every call site.
    """
    with span(name):
        return await coro


# ---------------------------------------------------------------------------
# Private phase helpers — each returns a typed result dataclass
# ---------------------------------------------------------------------------


async def _run_phase3(
    ctx: PipelineContext,
    intermediates: PhaseIntermediates,
    phase2_results: Phase2Result,
    scan_date: date,
    portfolio_context: str,
) -> Phase3Result:
    """Phase 3: Trading Mode determination."""
    print("\n" + "=" * 60, flush=True)
    print("PHASE 3: Trading Mode Determination", flush=True)
    print("=" * 60, flush=True)

    trading_mode = await resolve_trading_mode(
        intermediates.early_mode,
        ctx.deployable_cash,
        phase2_results.position_alerts,
        intermediates.sector_rotation,
        ctx.longterm_watchlist,
        scan_date,
        portfolio_context=portfolio_context,
    )
    return Phase3Result(trading_mode=trading_mode)


async def _run_phase3a(
    scan_date: date,
    intermediates: PhaseIntermediates,
) -> Phase3aResult:
    """Phase 3a: Compute Pipeline Constraints."""
    from agents.strategy_constraints import compute_pipeline_constraints

    pipeline_constraints, goals, cash_dict = await compute_pipeline_constraints(
        scan_date=scan_date,
        entries_allowed=intermediates.entries_allowed,
        entries_blocked_reason=intermediates.entries_blocked_reason,
    )
    return Phase3aResult(
        pipeline_constraints=pipeline_constraints,
        goals=goals,
        cash_dict=cash_dict,
        composed_min_rr=pipeline_constraints.get("min_rr") or 2.5,
        composed_max_picks=pipeline_constraints.get("max_new_entries") or 3,
        expectancy_floor=pipeline_constraints.get("expectancy_floor"),
        rolling_win_rate=pipeline_constraints.get("rolling_win_rate"),
    )


async def _run_phase3b(
    phase2_results: Phase2Result,
    intermediates: PhaseIntermediates,
    ctx: PipelineContext,
    deterministic_beliefs: DeterministicBeliefs,
    phase3a: Phase3aResult,
    scan_date: date,
    phase1_results: Phase1Result,
) -> Phase3bResult:
    """Phase 3b: Pre-Compute Top Picks.

    When Phase 2 health flags ``degraded_mode == "aggregator_only"``, the
    surviving sector signals are dropped: they represent a tiny minority
    of the universe and recommending from them silently publishes
    partial-coverage recs. Picks then fall back to
    ``belief_boosted_tickers`` (derived from the aggregator's BULLISH
    beliefs) — the same deterministic path used when sector agents
    starve naturally.
    """
    from pipeline.phase_parallel_health import DEGRADED_MODE_AGGREGATOR_ONLY
    from shared.rules.belief_fallback import derive_belief_boosted_tickers

    picks: list[dict] = []
    health = phase2_results.health
    aggregator_only_mode = (
        health is not None
        and getattr(health, "degraded_mode", None) == DEGRADED_MODE_AGGREGATOR_ONLY
    )
    sector_signals_for_picks: list[dict]
    if aggregator_only_mode:
        logger.warning(
            "Phase 3b: aggregator_only mode active — dropping %d surviving sector_signals "
            "to avoid publishing recs from <15%% sector coverage. Falling back to "
            "belief_boosted_tickers.",
            len(phase2_results.sector_signals),
        )
        sector_signals_for_picks = []
    else:
        sector_signals_for_picks = phase2_results.sector_signals

    belief_boosted = derive_belief_boosted_tickers(
        deterministic_beliefs.get("sector"),
        sector_signals_for_picks,
        ctx.holdings_tickers,
        phase3a.composed_max_picks,
    )
    if belief_boosted:
        logger.info(
            "belief_fallback: %d BULLISH aggregator tickers promoted as pick candidates: %s",
            len(belief_boosted),
            sorted(belief_boosted),
        )
        print(
            f"  [belief_fallback] Promoting {len(belief_boosted)} BULLISH aggregator "
            f"tickers as pick candidates: {sorted(belief_boosted)}",
            flush=True,
        )

    if sector_signals_for_picks or belief_boosted:
        try:
            # SWI-171 Phase A: build the per-pipeline audit context once
            # so every per-candidate score row records consistent suppressor
            # inputs. Mirrors the Rule 5a predicate in recommendation_gate.py.
            audit_context = _build_score_audit_context(
                intermediates=intermediates,
                phase1_results=phase1_results,
                phase3a=phase3a,
                ctx=ctx,
                deterministic_beliefs=deterministic_beliefs,
            )
            picks = await compute_top_picks(
                sector_signals=sector_signals_for_picks,
                scan_date=scan_date,
                technicals=intermediates.technicals,
                sector_rotation=intermediates.sector_rotation,
                holdings_tickers=ctx.holdings_tickers,
                deterministic_beliefs=deterministic_beliefs.get("sector"),
                min_rr=phase3a.composed_min_rr,
                max_picks=phase3a.composed_max_picks,
                risk_regime=intermediates.global_risk_regime,
                catalyst_boosted_tickers=set((ctx.catalyst_boosted or {}).keys()),
                belief_boosted_tickers=belief_boosted,
                # L2 (2026-04-27): per-ticker stacked-shock relief inputs.
                # active_catalysts is the typed list from Phase 0; macro's
                # geopolitical_shock dict is loaded in Phase 1.
                active_catalysts=ctx.active_catalysts,
                geopolitical_shock=(phase1_results.macro_metrics or {}).get("geopolitical_shock"),
                score_recorder=ctx.score_recorder,
                score_phase="morning",
                audit_context=audit_context,
            )
        except Exception as e:
            logger.warning("Picks extraction error (non-fatal): %s", e)
            print(f"  Picks extraction error (non-fatal): {e}", flush=True)
    return Phase3bResult(pre_computed_picks=picks)


def _build_score_audit_context(
    *,
    intermediates: PhaseIntermediates,
    phase1_results: Phase1Result,
    phase3a: Phase3aResult,
    ctx: PipelineContext,
    deterministic_beliefs: DeterministicBeliefs,
) -> dict:
    """Pack composer Rule 5a inputs + sector counts for the score audit.

    Audit-only — caller threads this into ``compute_top_picks`` so the
    per-candidate ``ReliefContext`` can be reconstructed inside the picks
    loop without reaching back across phase boundaries.
    """
    from shared.rules.catalyst_override import has_high_positive_macro_blanket_catalyst
    from shared.rules.geopolitical import ACTIVE_SHOCK_PHASES
    from shared.rules.macro_stress import classify_underlying_stress

    macro = phase1_results.macro_metrics or {}
    shock_phase = (macro.get("geopolitical_shock") or {}).get("phase_name") or ""
    sector_beliefs = deterministic_beliefs.get("sector") or []
    bullish_count = sum(
        1 for belief in sector_beliefs if (belief.get("direction") or "").upper() == "BULLISH"
    )
    sector_keys = (ctx.sectors or {}).keys()
    return {
        "underlying_stress": classify_underlying_stress(macro),
        "shock_active": shock_phase in ACTIVE_SHOCK_PHASES,
        "has_high_positive_macro_catalyst": has_high_positive_macro_blanket_catalyst(
            ctx.active_catalysts
        ),
        "bullish_sector_belief_count": bullish_count,
        "total_sector_count": len(list(sector_keys)) or len(sector_beliefs),
        "urgency_tier": phase3a.pipeline_constraints.get("urgency_tier"),
    }


async def _run_advocates(
    phase3b: Phase3bResult,
    deterministic_beliefs: DeterministicBeliefs,
    regime_context: str,
    phase2_results: Phase2Result,
    phase3: Phase3Result,
    scan_date: date,
) -> AdvocateResult:
    """Phase 3.5+3.6: Advocate reviews + gate filtering."""
    picks = phase3b.pre_computed_picks
    advocate_reviews: dict[str, list[dict]] = {"bull": [], "bear": []}

    if picks and not phase2_results.all_sectors_failed:
        print("\n" + "=" * 60, flush=True)
        print("PHASE 3.5: Advocate Reviews", flush=True)
        print("=" * 60, flush=True)

        advocate_reviews = await run_advocate_reviews(
            pre_computed_picks=picks,
            deterministic_beliefs=deterministic_beliefs,
            phase1_context=regime_context,
            scan_date=scan_date,
        )

    filtered_picks = list(picks)
    gated_tickers: list[dict] = []
    if advocate_reviews.get("bull") or advocate_reviews.get("bear"):
        filtered_picks, gated_tickers = apply_advocate_gate(
            pre_computed_picks=list(picks),
            advocate_reviews=advocate_reviews,
            position_alerts=phase2_results.position_alerts,
            trading_mode=phase3.mode_str,
        )

    return AdvocateResult(
        advocate_reviews=advocate_reviews,
        filtered_picks=filtered_picks,
        gated_tickers=gated_tickers,
    )


async def _run_synthesis(
    ctx: PipelineContext,
    phase1_results: Phase1Result,
    phase2_results: Phase2Result,
    intermediates: PhaseIntermediates,
    phase3: Phase3Result,
    phase3a: Phase3aResult,
    advocate: AdvocateResult,
    injected: InjectedContext,
    scan_date: date,
    is_degraded: bool,
) -> SynthesisResult:
    """Phase 3d+4: Strategy Director + Synthesis."""
    final_brief, reflection_status = await run_strategy_and_synthesis(
        ctx=ctx,
        phase1_results=phase1_results,
        phase2_results=phase2_results,
        sector_results=phase2_results.sector_results,
        position_alerts=phase2_results.position_alerts,
        trading_mode=phase3.trading_mode,
        pre_computed_picks=advocate.filtered_picks,
        advocate_reviews=advocate.advocate_reviews,
        gated_tickers=advocate.gated_tickers,
        holdings_tickers=ctx.holdings_tickers,
        all_sectors_failed=phase2_results.all_sectors_failed,
        scan_date=scan_date,
        entries_allowed=intermediates.entries_allowed,
        entries_blocked_reason=intermediates.entries_blocked_reason,
        market_regime=intermediates.market_regime,
        global_risk_regime=intermediates.global_risk_regime,
        sector_rotation=intermediates.sector_rotation,
        sector_signals=phase2_results.sector_signals,
        injected=injected,
        is_degraded=is_degraded,
        pre_computed_constraints=phase3a.pipeline_constraints,
        goals=phase3a.goals,
        cash_dict=phase3a.cash_dict,
        rolling_win_rate=phase3a.rolling_win_rate,
        expectancy_floor=phase3a.expectancy_floor,
        min_rr_floor=phase3a.composed_min_rr,
        gate_decision=intermediates.gate_decision,
    )
    return SynthesisResult(final_brief=final_brief, reflection_status=reflection_status)


# ---------------------------------------------------------------------------
# Public orchestrator — signature unchanged from previous version
# ---------------------------------------------------------------------------


async def run_phases_3_to_6(
    ctx: PipelineContext,
    phase1_results: Phase1Result,
    phase2_results: Phase2Result,
    *,
    intermediates: PhaseIntermediates,
    deterministic_beliefs: DeterministicBeliefs,
    scan_date: date,
    research_dir: Path,
    today_str: str,
    skip_alerts: bool,
    is_degraded: bool = False,
) -> None:
    """Run Phases 3-6: trading mode, picks, advocates, synthesis, alerts, recommendations."""
    from analysis.synthesis import save_morning_brief
    from pipeline.context_blocks import format_portfolio_block

    portfolio_context = format_portfolio_block(
        ctx.holdings,
        ctx.cash_balance,
        ctx.deployable_cash,
        snapshot_at=ctx.holdings_snapshot_at,
    )

    # ── PHASE 3 || 3a (parallel — no cross-dependencies) ──
    phase3, phase3a = await asyncio.gather(
        _spanned(
            "phase3_trading_mode",
            _run_phase3(ctx, intermediates, phase2_results, scan_date, portfolio_context),
        ),
        _spanned("phase3a_constraints", _run_phase3a(scan_date, intermediates)),
    )

    # ── Compose the single `RecommendationGateDecision` that every downstream
    # consumer (validator, renderer, picks writer, synthesis, phase_strategy
    # fallback) must read from. Ties trading mode, regime, urgency, retro,
    # streak alert, and underlying-macro stress into ONE audit-logged object. ──
    # Candidate universe = today's swing watchlist union holdings. Feeds
    # Rule 5a's per-ticker catalyst check so VN-INDEX-only macro catalysts
    # don't also register as per-ticker relief signal. `holdings_tickers`
    # is the typed property on `PipelineContext` (list[str]).
    candidate_universe = {
        ticker for tickers in (ctx.sectors or {}).values() for ticker in tickers
    } | set(ctx.holdings_tickers)

    await compose_gate_from_state(
        intermediates=intermediates,
        macro_metrics=phase1_results.macro_metrics,
        pipeline_constraints=dict(phase3a.pipeline_constraints),
        trading_mode=phase3.mode_str,
        scan_date=scan_date,
        active_catalysts=ctx.active_catalysts,
        sector_beliefs=phase2_results.sector_beliefs,
        candidate_universe=candidate_universe,
    )
    if intermediates.gate_decision is not None:
        # Ripple the composer-derived floor + max_entries into phase3a so
        # every caller that reads `composed_min_rr` / `composed_max_picks`
        # picks up the post-composition values (streak relaxation, shock-only
        # flooring, etc.) without having to know the composer exists.
        phase3a.composed_min_rr = intermediates.gate_decision.effective_rr_floor
        phase3a.composed_max_picks = intermediates.gate_decision.max_new_entries

        # Same ripple at the pipeline_constraints layer. Reader-facing
        # surfaces (brief ENTRY CRITERIA, synthesis narrative) read the
        # EFFECTIVE keys; pre-composition urgency values stay intact as the
        # producer contract.
        from shared.rules.constraints import inject_gate_composition

        inject_gate_composition(phase3a.pipeline_constraints, intermediates.gate_decision)

    # ── PHASE 3b: Top Picks (needs phase3a.composed_min_rr) ──
    phase3b = await _spanned(
        "phase3b_picks",
        _run_phase3b(
            phase2_results,
            intermediates,
            ctx,
            deterministic_beliefs,
            phase3a,
            scan_date,
            phase1_results,
        ),
    )

    # ── CONTEXT BUILD ──
    injected = await build_injected_context(
        ctx,
        phase1_results,
        intermediates,
        portfolio_context,
    )

    # ── PHASE 3.5+3.6: Advocates → AdvocateResult ──
    advocate = await _spanned(
        "phase3_advocates",
        _run_advocates(
            phase3b,
            deterministic_beliefs,
            injected.regime_context,
            phase2_results,
            phase3,
            scan_date,
        ),
    )

    # ── PHASE 3d+4: Strategy + Synthesis → SynthesisResult ──
    synthesis = await _spanned(
        "phase_strategy_synthesis",
        _run_synthesis(
            ctx,
            phase1_results,
            phase2_results,
            intermediates,
            phase3,
            phase3a,
            advocate,
            injected,
            scan_date,
            is_degraded,
        ),
    )
    # Banners: critic-missing + 0-BUY streak alert. Streak blob is already
    # cached on intermediates by compose_gate_from_state — reuse rather
    # than re-fetching yesterday's row from Neon.
    from pipeline.rendering.banners import (
        Banner,
        critic_missing_banner,
        streak_alert_banner,
    )

    brief_banners: list[Banner] = []
    if synthesis.reflection_status in {"skipped_timeout", "skipped_error"}:
        brief_banners.append(critic_missing_banner())
    prior_blob = intermediates.streak_alert
    if prior_blob and (prior_blob.get("length") or 0) >= 3:
        brief_banners.append(streak_alert_banner(prior_blob))
    # DELIBERATE: publish-with-stub policy (commits 4eb608da 2026-04-16,
    # 43dbdbef 2026-04-19). The brief publishes even when critic/validation
    # emits non-empty issues — banners + appended warnings make crashes
    # visually distinguishable from clean runs. Do NOT add a publish gate
    # here; user reviewed 2026-05-14 and re-affirmed.
    save_morning_brief(synthesis.final_brief, research_dir, today_str, banners=brief_banners)

    # ── PHASE 5: Alert Registration (sequential — shared Neon pool) ──
    alert_trading_mode: TradingMode = phase3.mode_str  # type: ignore[assignment]
    await _spanned(
        "phase5_alerts",
        run_phase5_alert_pipeline(
            position_alerts=phase2_results.position_alerts,
            pre_computed_picks=advocate.filtered_picks,
            scan_date=scan_date,
            global_risk_regime=intermediates.global_risk_regime,  # type: ignore[arg-type]
            trading_mode=alert_trading_mode,
            holdings=ctx.holdings,
            skip_alerts=skip_alerts,
        ),
    )

    # ── PHASE 6: Write Recommendations to DB ──
    swing_watchlist_tickers: set[str] = {
        ticker for tickers in (ctx.sectors or {}).values() for ticker in tickers
    }
    buy_signal_count = sum(1 for s in phase2_results.sector_signals if s.get("signal") == "BUY")
    await _spanned(
        "phase6_recommendations",
        run_phase6_recommendations(
            pre_computed_picks=advocate.filtered_picks,
            position_alerts=phase2_results.position_alerts,
            sector_signals=phase2_results.sector_signals,
            holdings=ctx.holdings,
            trading_mode=phase3.trading_mode,
            longterm_watchlist=ctx.longterm_watchlist,
            deployable_cash=ctx.deployable_cash,
            market_regime=intermediates.market_regime,
            global_risk_regime=intermediates.global_risk_regime,
            scan_date=scan_date,
            reflection_status=synthesis.reflection_status,
            gate_decision=intermediates.gate_decision,
            deterministic_beliefs=deterministic_beliefs,
            swing_watchlist_tickers=swing_watchlist_tickers,
            buy_signal_count=buy_signal_count,
            technicals=intermediates.technicals,
            gated_tickers=advocate.gated_tickers,
            score_recorder=ctx.score_recorder,
            score_phase="morning",
        ),
    )
