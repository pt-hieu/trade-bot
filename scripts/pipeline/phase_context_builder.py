"""Build pre-formatted context strings for Phase 3d+ agent prompts."""

import asyncio
import logging

from .types import InjectedContext, Phase1Result, PhaseIntermediates, PipelineContext

logger = logging.getLogger(__name__)


async def build_injected_context(
    ctx: PipelineContext,
    phase1_results: Phase1Result,
    intermediates: PhaseIntermediates,
    portfolio_context: str,
) -> InjectedContext:
    """Assemble all context blocks consumed by strategy director and synthesis."""
    from agents.tools.catalyst_preview import format_catalyst_preview_prose
    from pipeline.context_blocks import (
        format_articles_block,
        format_commodity_block,
        format_regime_block,
        format_vn_economy_block,
    )

    # ── Catalyst context ──
    catalyst_context = ""
    if ctx.enrichment and ctx.enrichment.catalyst_preview:
        catalyst_context = format_catalyst_preview_prose(ctx.enrichment.catalyst_preview)

    # Catalyst boost set was pre-computed in Phase 0 (load_db_context).
    # Read from ctx — no re-fetch. None signals fetch failure; {} = no boosts.
    from shared.rules.catalyst_override import format_catalyst_boost_context

    catalyst_boost_context = format_catalyst_boost_context(ctx.catalyst_boosted or {})

    # ── Articles context ──
    articles_context = ""
    if ctx.enrichment and ctx.enrichment.articles:
        articles_context = format_articles_block(ctx.enrichment.articles)

    # ── Regime context ──
    regime_context = format_regime_block(
        phase1_results.market_level,
        phase1_results.macro_metrics,
        market_valuation=phase1_results.market_valuation or None,
    )
    macro_interpretation = ""
    if phase1_results.macro_metrics:
        macro_interpretation = phase1_results.macro_metrics.get("interpretation") or ""

    # ── Commodity context ──
    commodity_context = ""
    if phase1_results.commodity_prices:
        commodity_context = format_commodity_block(phase1_results.commodity_prices)

    # ── VN economy context ──
    vn_economy_context = format_vn_economy_block(phase1_results.vn_economy)

    # ── Macro trends (5-day) ──
    macro_trend_context = ""
    try:
        from pipeline.macro_trends import (
            compute_indicator_trends,
            compute_regime_transition,
            detect_cross_asset_narratives,
            format_trend_block,
        )
        from shared.neon.market import get_macro_history, get_regime_history

        macro_history = await get_macro_history(5)
        regime_history = await get_regime_history(5)
        trends = compute_indicator_trends(macro_history)
        regime_transition = compute_regime_transition(regime_history)
        narratives = detect_cross_asset_narratives(
            trends,
            commodity_prices=phase1_results.commodity_prices or None,
            market_valuation=phase1_results.market_valuation or None,
        )
        macro_trend_context = format_trend_block(trends, regime_transition, narratives)
    except Exception as trend_error:
        logger.warning("Trend computation failed (non-fatal): %s", trend_error)

    if macro_trend_context:
        regime_context = regime_context + "\n" + macro_trend_context

    # SWI-204: surface VN-INDEX-positive macro catalysts (Idemitsu, IMF growth
    # upgrade, etc.) into the regime block so entry_strategist / critic /
    # meta_controller see them via `format_dual_regime_labels` consumers.
    # `ctx.active_catalysts` was already fetched in Phase 0 — no extra query.
    try:
        from pipeline.context_blocks_macro import format_vnindex_catalyst_lines

        # CatalystInput is a TypedDict — runtime dict, safe to pass through.
        vnindex_positive_lines = format_vnindex_catalyst_lines(
            list(ctx.active_catalysts or [])  # type: ignore[arg-type]
        )
        if vnindex_positive_lines:
            regime_context = (
                regime_context
                + "\n## MACRO POSITIVES (VN-INDEX, IMMINENT/ACTIVE)\n"
                + "\n".join(vnindex_positive_lines)
            )
    except Exception as exc:  # pragma: no cover — observability path
        logger.warning("VN-INDEX positives splice failed: %s", exc)

    # ── Memory tools pre-fetch ──
    memory_context = ""
    try:
        from agents.tools.memory import (
            tool_get_losing_patterns,
            tool_get_similar_days,
            tool_get_trading_rules,
            tool_get_winning_patterns,
        )
        from pipeline.context_blocks_calibration import format_memory_block

        market_level = phase1_results.market_level or {}
        regime = market_level.get("regime") or "NEUTRAL"
        macro_regime = (phase1_results.macro_metrics or {}).get("global_risk_regime") or "CALM"
        vix = (phase1_results.macro_metrics or {}).get("vix_value")
        hot = ",".join((intermediates.sector_rotation or {}).get("hot_sectors") or [])
        cold = ",".join((intermediates.sector_rotation or {}).get("cold_sectors") or [])

        similar_days, rules, winning, losing = await asyncio.gather(
            tool_get_similar_days(regime, hot, cold, macro_regime, vix),
            tool_get_trading_rules(regime, hot),
            tool_get_winning_patterns(regime, hot),
            tool_get_losing_patterns(regime, cold),
        )
        memory_context = format_memory_block(similar_days, rules, winning, losing)
    except Exception as memory_error:
        logger.warning("Memory tools pre-fetch failed (non-fatal): %s", memory_error)

    # ── Inject-instead-of-tool context from enrichment ──
    recent_trades_block = ""
    learnings_formatted: dict[str, str] = {}
    if ctx.enrichment:
        if ctx.enrichment.recent_trades_prose:
            from pipeline.context_blocks_calibration import format_trades_block

            recent_trades_block = format_trades_block(ctx.enrichment.recent_trades_prose)
        if ctx.enrichment.learnings_cache:
            from pipeline.context_blocks_calibration import format_learnings_block

            entry_learnings = format_learnings_block(
                ctx.enrichment.learnings_cache,
                ["summary", "calibration", "sector_bias", "ticker_accuracy"],
            )
            if entry_learnings:
                learnings_formatted["entry_strategist"] = entry_learnings

    return InjectedContext(
        portfolio_context=portfolio_context,
        catalyst_context=catalyst_context,
        catalyst_boost_context=catalyst_boost_context,
        articles_context=articles_context,
        geopolitical_context=intermediates.geopolitical_context,
        trailing_stops_context=intermediates.trailing_stops_context,
        regime_context=regime_context,
        macro_interpretation=macro_interpretation,
        commodity_context=commodity_context,
        vn_economy_context=vn_economy_context,
        recent_trades=recent_trades_block,
        learnings_formatted=learnings_formatted,
        memory_context=memory_context,
    )
