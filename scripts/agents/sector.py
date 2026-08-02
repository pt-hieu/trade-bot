#!/usr/bin/env python3
"""
Sector analyst — ensemble of 3 sub-agents + aggregator.

Architecture: Parallel Ensemble (fan-out → fan-in).
  - Technical analyst: price action, momentum, relative strength
  - News analyst: articles, catalysts, sentiment
  - Enrichment analyst: flow, insider, valuation history
  - Aggregator (sector_aggregator): synthesizes sub-reports → SectorAnalysisResult

Returns structured signals (BUY/WATCH/WAIT/AVOID) per ticker via same public API.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.enrichment_loader import EnrichmentData
    from shared.rules.catalyst_override import CatalystBoost, CatalystInput

from shared.agent_config import build_usage_limits, load_agent_config
from shared.errors import ProviderUnavailable
from shared.observability import emit_silent_provider_hang_span, emit_ticker_drop_span
from shared.rules.audit_tags import DERIVED_FROM_BELIEFS

from .agent_factory import AgentDeps, create_agent
from .belief_aggregation import weighted_aggregate_beliefs
from .belief_collection import collect_beliefs_from_views
from .belief_models import (
    BASE_RATE_BEAR,
    BASE_RATE_BULL,
    BASE_RATE_NEUTRAL,
    AggregatedBelief,
    DirectionLiteral,
)
from .ensemble_concurrency import gated_fanout
from .model.wrappers import (
    OUTER_DISABLE_FALLBACK_WALL_S,
    await_with_hop_unwrap,
    downstream_provider_from_timeout,
    provider_slug_from_timeout,
)
from .run_with_total_timeout import run_agent_with_total_timeout
from .sector_analysts import (
    SectorAnalystReport,
    _fmt_sector_report,
    _run_sector_analyst,
)
from .sector_filters import (
    _apply_cash_gate,
    _apply_coverage_gaps,
    _apply_regime_downgrade,
    _build_regime_context,
    _format_sector_text,
)
from .sector_models import SectorAnalysisResult, TickerSignal
from .tools.native_tools import BrokerLoopBreaker

logger = logging.getLogger(__name__)

# Re-export models so existing callers via `from .sector import` continue to work
__all__ = [
    "TickerSignal",
    "SectorAnalysisResult",
    "analyze_sector_with_agent",
]


# Shared invariants for beliefs synthesized on a degraded aggregator path:
# low conviction so downstream weighting treats them as placeholders, and
# the standard 5-day belief horizon.
_DEGRADED_BELIEF_CONVICTION = 0.2
_DEGRADED_BELIEF_TIMEFRAME_DAYS = 5


def _synthesize_aggregator_belief(
    *,
    ticker: str,
    narrative: str,
    direction: DirectionLiteral,
    bull_probability: float,
    base_probability: float,
    bear_probability: float,
    price_target_vnd: int,
) -> AggregatedBelief:
    """Build a low-conviction AggregatedBelief for a degraded aggregator path.

    Both degradation paths — ``_wait_fallback`` (all sub-agents down) and
    ``_derive_signals_from_subreports`` (aggregator hung, sub-agents alive) —
    share the conviction/timeframe invariants; keep them in one place.
    """
    return AggregatedBelief(
        ticker=ticker,
        belief_narrative=narrative,
        direction=direction,
        bull_probability=bull_probability,
        base_probability=base_probability,
        bear_probability=bear_probability,
        price_target_vnd=price_target_vnd,
        timeframe_days=_DEGRADED_BELIEF_TIMEFRAME_DAYS,
        conviction=_DEGRADED_BELIEF_CONVICTION,
    )


def _wait_fallback(
    tickers: list[str],
    note: str,
    summary: str,
    last_known_prices: dict[str, int] | None = None,
) -> SectorAnalysisResult:
    """Degraded result when all 3 sub-agents fail — WAIT for all tickers.

    Synthesizes a minimal NEUTRAL ``sector_aggregator`` belief per ticker so
    the all-analysts-down path still writes belief rows (Bug 10, run2
    2026-05-14), keeping it convergent with ``_derive_signals_from_subreports``.
    A ticker with no last-known price is skipped + logged rather than
    constructed as an invalid model (``price_target_vnd`` is REQUIRED).
    """
    prices = last_known_prices or {}
    beliefs: list[AggregatedBelief] = []
    for ticker in tickers:
        price = prices.get(ticker)
        if not price:
            logger.warning(
                "_wait_fallback: no last-known price for %s — skipping aggregator belief",
                ticker,
            )
            continue
        beliefs.append(
            _synthesize_aggregator_belief(
                ticker=ticker,
                narrative=(
                    f"{DERIVED_FROM_BELIEFS} all sub-agents failed; NEUTRAL "
                    f"placeholder belief, no directional signal."
                ),
                direction="NEUTRAL",
                bull_probability=BASE_RATE_BULL,
                base_probability=BASE_RATE_NEUTRAL,
                bear_probability=BASE_RATE_BEAR,
                price_target_vnd=int(price),
            )
        )
    return SectorAnalysisResult(
        signals=[
            TickerSignal(ticker=t, signal="WAIT", note=note, confidence="LOW") for t in tickers
        ],
        summary=summary,
        beliefs=beliefs,
    )


def _derive_signals_from_subreports(
    *,
    technical: SectorAnalystReport,
    news: SectorAnalystReport,
    enrichment: SectorAnalystReport,
    tickers: list[str],
    sector_name: str,
    degradation_type: str,
) -> SectorAnalysisResult:
    """Fall-back signal derivation when the LLM aggregator degrades.

    Replaces the old `[AGGREGATOR_TIMEOUT]` placeholder (pipeline review
    2026-04-14). Per-ticker majority vote across the three sub-agent
    views, with the bullish-leaning tiebreak rule and a conviction-driven
    narrative excerpt. Notes carry the `[DERIVED_FROM_BELIEFS]` prefix so
    pipeline reviewers can audit any divergence from what the LLM would
    have produced.
    """
    from shared.rules.belief_to_signal import derive_signal_from_views

    reports_by_key = (
        ("sector_technical", technical),
        ("sector_news", news),
        ("sector_enrichment", enrichment),
    )

    views_by_ticker: dict[str, list] = {ticker: [] for ticker in tickers}
    # Per-ticker sub-agent belief dicts (model_dump + agent_key) for the
    # deterministic aggregation, plus the price targets they carried.
    belief_dicts_by_ticker: dict[str, list[dict]] = {ticker: [] for ticker in tickers}
    price_targets_by_ticker: dict[str, list[int]] = {ticker: [] for ticker in tickers}
    for agent_key, report in reports_by_key:
        for view in report.views:
            if view.ticker not in views_by_ticker:
                continue
            views_by_ticker[view.ticker].append(view)
            belief = view.belief
            belief_dict = belief.model_dump()
            # agent_key is the SUB-AGENT's key (not "sector_aggregator") —
            # weighted_aggregate_beliefs reads it for per-agent calibration
            # weighting; a constant key would flatten it to uniform.
            belief_dict["agent_key"] = agent_key
            belief_dicts_by_ticker[view.ticker].append(belief_dict)
            price_targets_by_ticker[view.ticker].append(belief.price_target_vnd)

    signals: list[TickerSignal] = []
    # Synthesize sector_aggregator beliefs so the degraded path still writes
    # belief rows (Bug 10, run2 2026-05-14). agent_key="sector_aggregator" is
    # stamped at the read loop in analyze_sector_with_agent; phase_beliefs
    # filters that key out of the deterministic average via
    # is_aggregator_double_counter, so reusing it does NOT double-count.
    beliefs: list[AggregatedBelief] = []
    for ticker in tickers:
        ticker_views = views_by_ticker.get(ticker) or []
        signal, note = derive_signal_from_views(ticker_views)
        signals.append(
            TickerSignal(
                ticker=ticker,
                signal=signal,
                note=note,
                confidence="LOW",
            )
        )

        ticker_beliefs = belief_dicts_by_ticker.get(ticker) or []
        targets = price_targets_by_ticker.get(ticker) or []
        if not ticker_beliefs or not targets:
            # No landed sub-agent view → no belief + no price source. Skip
            # this ticker's belief (logged, not silent) rather than build
            # an invalid model.
            logger.warning(
                "sector %s: no landed sub-agent belief for %s — skipping aggregator belief",
                sector_name,
                ticker,
            )
            continue
        aggregated = weighted_aggregate_beliefs(ticker_beliefs)
        beliefs.append(
            _synthesize_aggregator_belief(
                ticker=ticker,
                narrative=(
                    f"{DERIVED_FROM_BELIEFS} {sector_name} aggregator degraded "
                    f"({degradation_type}); belief synthesized from "
                    f"{len(ticker_beliefs)} sub-agent view(s)."
                ),
                direction=aggregated["direction"],
                bull_probability=aggregated["bull_probability"],
                base_probability=aggregated["base_probability"],
                bear_probability=aggregated["bear_probability"],
                price_target_vnd=int(median(targets)),
            )
        )

    return SectorAnalysisResult(
        signals=signals,
        summary=(
            f"{DERIVED_FROM_BELIEFS} {sector_name} aggregator degraded "
            f"({degradation_type}); signals derived from {len(tickers)} "
            f"tickers via sub-agent majority vote."
        ),
        beliefs=beliefs,
    )


async def _aggregate_sector(
    sector_name: str,
    tickers: list[str],
    technical: SectorAnalystReport,
    news: SectorAnalystReport,
    enrichment: SectorAnalystReport,
    regime_context: str = "",
    entries_allowed: bool = True,
) -> SectorAnalysisResult:
    """Run aggregator agent to synthesize 3 sub-reports into SectorAnalysisResult."""
    config = await load_agent_config("sector_aggregator")
    # Sector aggregator may also call broker tools (rare); seed
    # ``tickers_in_scope`` so any missing-``tickers`` validation hint
    # carries the exact sector member list.
    agent = create_agent(config, output_type=SectorAnalysisResult)

    context_parts = [
        _fmt_sector_report("technical", technical),
        _fmt_sector_report("news", news),
        _fmt_sector_report("enrichment", enrichment),
    ]

    cash_constraint = (
        "\nCONSTRAINT: Cash is depleted. Do NOT produce BUY signals. "
        "Only classify as WATCH/WAIT/AVOID.\n"
        if not entries_allowed
        else ""
    )

    prompt = (
        f"Synthesize the following analyst reports for the {sector_name} sector "
        f"(tickers: {', '.join(tickers)}) into final per-ticker signals.\n"
        f"{cash_constraint}\n" + "\n\n".join(context_parts)
    )
    if regime_context:
        prompt = f"{regime_context}\n\n{prompt}"

    try:
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="sector_aggregator",
            deps=AgentDeps(
                scan_date=None, agent_key="sector_aggregator", tickers_in_scope=list(tickers)
            ),
            total_timeout_s=float(OUTER_DISABLE_FALLBACK_WALL_S),
            usage_limits=build_usage_limits(config),
            sector=sector_name,
        )
        emit_ticker_drop_span(
            agent="sector_aggregator",
            expected={t.upper() for t in tickers},
            produced={signal.ticker.upper() for signal in result.output.signals},
            logger=logger,
            sector=sector_name,
        )
        return result.output
    except (ProviderUnavailable, TimeoutError, BrokerLoopBreaker):
        # All three are structural degradations — bubble up so the caller
        # can derive signals from the sub-agent views via
        # _derive_signals_from_subreports instead of silently returning an
        # empty SectorAnalysisResult.
        raise
    except Exception as e:
        logger.warning("Sector %s aggregator failed: %s", sector_name, e)
        return SectorAnalysisResult(
            signals=[],
            summary=f"Aggregator failed: {e}",
        )


async def analyze_sector_with_agent(
    sector_name: str,
    tickers: list[str],
    scan_date: date | None = None,
    entries_allowed: bool = True,
    market_regime: str = "NEUTRAL",
    global_risk_regime: str = "CALM",
    geopolitical_context: str = "",
    market_level_dict: dict | None = None,
    macro_metrics_dict: dict | None = None,
    technicals: dict | None = None,
    enrichment_data: EnrichmentData | None = None,
    articles_context: str = "",
    commodity_prices: dict | None = None,
    market_valuation: dict | None = None,
    catalyst_boosted: dict[str, CatalystBoost] | None = None,
    active_catalysts: list[CatalystInput] | None = None,
) -> dict:
    """Analyze a sector using ensemble of 3 sub-agents + aggregator.

    Returns dict with 'text' (str for synthesis) and 'signals' (list[dict]).

    ``active_catalysts`` powers the GEO_MIXED tie-break inside the briefing
    renderer (Fix 1, 2026-04-21). Passed through from Phase 0
    (`PipelineContext.active_catalysts`) by phase_parallel.
    """
    if scan_date is None:
        scan_date = date.today()

    regime_context = _build_regime_context(
        market_level_dict,
        macro_metrics_dict,
        geopolitical_context,
        market_valuation=market_valuation,
    )

    # Build per-agent ticker briefings so each sees its OWN prior belief
    from pipeline.context_blocks import format_ticker_briefings
    from pipeline.context_blocks_calibration import build_calibration_blocks

    geopolitical_shock = (macro_metrics_dict or {}).get("geopolitical_shock")
    briefings_technical = format_ticker_briefings(
        tickers=tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices=commodity_prices,
        macro_metrics=macro_metrics_dict,
        geopolitical_shock=geopolitical_shock,
        agent_key="sector_technical",
        catalyst_boosted=catalyst_boosted,
        active_catalysts=active_catalysts,
    )
    briefings_news = format_ticker_briefings(
        tickers=tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices=commodity_prices,
        macro_metrics=macro_metrics_dict,
        geopolitical_shock=geopolitical_shock,
        agent_key="sector_news",
        catalyst_boosted=catalyst_boosted,
        active_catalysts=active_catalysts,
    )
    briefings_enrichment = format_ticker_briefings(
        tickers=tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices=commodity_prices,
        macro_metrics=macro_metrics_dict,
        geopolitical_shock=geopolitical_shock,
        agent_key="sector_enrichment",
        catalyst_boosted=catalyst_boosted,
        active_catalysts=active_catalysts,
    )

    # Build per-agent calibration context from pre-fetched belief accuracy
    calibration = build_calibration_blocks(
        enrichment_data, ["sector_technical", "sector_news", "sector_enrichment"]
    )

    # Per-sector shared tool cache — reuses tool results across the 3 sibling
    # analysts (same ticker set, same scan_date). Does NOT leak across sectors
    # or across pipeline runs. Only the `_tool_cache` reference is shared, so
    # each agent's `agent_key` and other per-agent context stays private.
    sector_tool_cache: dict = {}

    # Serialize the 3 sibling analysts. Phase 2 runs up to 4 sectors
    # concurrently under _API_SEMAPHORE; an unbounded 3-analyst fan-out per
    # sector would peak at 12 inflight LLM requests on one OpenRouter key
    # (the 2026-05-15 incident). gated_fanout() caps each sector at 1
    # inflight, restoring _API_SEMAPHORE's intended ~4-concurrent cap.
    #
    # Tradeoff: per-sector wall is now sum-of-3 not max-of-3 analyst
    # budgets (worst case ~3 × 2 attempts × OUTER_FALLBACK_STACK_WALL_S).
    # There is no hard per-sector wall — phase2 gathers sectors with no
    # wait_for — so this is bounded only by the 7200s morning pipeline
    # timeout, which absorbs it with 4-way sector parallelism.
    _gated = gated_fanout()

    # ``return_exceptions=True`` is belt-and-suspenders for BrokerLoopBreaker:
    # _run_sector_analyst (Change 2) absorbs the breaker into an empty-views
    # report on its own, so this normalization is the safety net for any
    # future hand-rolled analyst that doesn't catch. Any non-BrokerLoopBreaker
    # exception is re-raised — preserves loud-fail for SectorAnalystFailure,
    # ValidationError, schema-unsatisfiable UnexpectedModelBehavior so
    # phase_parallel's failed_sector_count still increments correctly.
    raw_results = await asyncio.gather(
        _gated(
            _run_sector_analyst(
                "technical",
                sector_name,
                tickers,
                scan_date,
                regime_context,
                ticker_briefings=briefings_technical,
                calibration_context=calibration.get("sector_technical", ""),
                shared_cache=sector_tool_cache,
            )
        ),
        _gated(
            _run_sector_analyst(
                "news",
                sector_name,
                tickers,
                scan_date,
                regime_context,
                ticker_briefings=briefings_news,
                articles_context=articles_context,
                calibration_context=calibration.get("sector_news", ""),
                shared_cache=sector_tool_cache,
            )
        ),
        _gated(
            _run_sector_analyst(
                "enrichment",
                sector_name,
                tickers,
                scan_date,
                regime_context,
                ticker_briefings=briefings_enrichment,
                calibration_context=calibration.get("sector_enrichment", ""),
                shared_cache=sector_tool_cache,
            )
        ),
        return_exceptions=True,
    )
    normalized_reports: list[SectorAnalystReport] = []
    for slot, analyst_name in zip(raw_results, ("technical", "news", "enrichment"), strict=True):
        if isinstance(slot, BrokerLoopBreaker):
            logger.warning(
                "Sector %s %s analyst escaped with BrokerLoopBreaker (%s) — "
                "normalizing to empty-views",
                sector_name,
                analyst_name,
                slot.breaker_kind,
            )
            normalized_reports.append(
                SectorAnalystReport(
                    views=[],
                    summary=f"[BROKER_LOOP_PROPAGATED:{slot.breaker_kind}]",
                )
            )
        elif isinstance(slot, BaseException):
            raise slot
        else:
            normalized_reports.append(slot)
    technical, news, enrichment = normalized_reports

    # Graceful degradation: detect failed sub-agents
    sub_reports = {"technical": technical, "news": news, "enrichment": enrichment}
    failed_analysts = [name for name, report in sub_reports.items() if not report.views]
    if len(failed_analysts) == 3:
        logger.warning(
            "Sector %s: all 3 sub-agents failed — returning WAIT for all tickers", sector_name
        )
        # technicals[ticker]["close"] is full VND (fetch_async stores
        # latest_close * 1000) — the price source for the NEUTRAL
        # placeholder beliefs _wait_fallback synthesizes.
        last_known_prices = {
            ticker: int(close)
            for ticker in tickers
            if (close := ((technicals or {}).get(ticker) or {}).get("close"))
        }
        output = _wait_fallback(
            tickers,
            "[ALL_ANALYSTS_FAILED]",
            f"All 3 analysts failed for {sector_name}.",
            last_known_prices=last_known_prices,
        )
    else:
        # Inject coverage instruction when 1-2 analysts failed
        failure_note = ""
        if failed_analysts:
            logger.warning(
                "Sector %s: %s analyst(s) failed — proceeding with remaining",
                sector_name,
                ", ".join(failed_analysts),
            )
            failure_note = (
                f"\nNOTE: {', '.join(failed_analysts)} analyst(s) returned no views (failed). "
                f"You MUST still produce signals for ALL tickers: {', '.join(tickers)}. "
                f"Use the remaining analyst reports to cover all tickers.\n"
            )

        aggregator_wall_s = int(OUTER_DISABLE_FALLBACK_WALL_S)
        try:
            output = await await_with_hop_unwrap(
                _aggregate_sector(
                    sector_name,
                    tickers,
                    technical,
                    news,
                    enrichment,
                    regime_context=regime_context + failure_note,
                    entries_allowed=entries_allowed,
                ),
                timeout=aggregator_wall_s,
            )
        except (TimeoutError, ProviderUnavailable, BrokerLoopBreaker) as degradation:
            logger.warning(
                "sector_aggregator degraded for %s (%s): %s — deriving signals "
                "from sub-agent views",
                sector_name,
                type(degradation).__name__,
                degradation,
            )
            if isinstance(degradation, TimeoutError):
                # Distinct alertable span so pipeline-review can query
                # hang_type="silent_provider" directly instead of the
                # tokens=None/None heuristic (MON-2026-04-13-002).
                emit_silent_provider_hang_span(
                    agent="sector_aggregator",
                    wall_s=aggregator_wall_s,
                    exception_type=type(degradation).__name__,
                    logger=logger,
                    provider=provider_slug_from_timeout(degradation),
                    downstream_provider=downstream_provider_from_timeout(degradation),
                    sector=sector_name,
                )
            output = _derive_signals_from_subreports(
                technical=technical,
                news=news,
                enrichment=enrichment,
                tickers=tickers,
                sector_name=sector_name,
                degradation_type=type(degradation).__name__,
            )

    # Post-processing (deterministic, no LLM)
    signals = output.signals
    signals = _apply_coverage_gaps(signals, tickers, sub_reports=[technical, news, enrichment])
    signals = _apply_regime_downgrade(signals, global_risk_regime)
    signals = _apply_cash_gate(signals, entries_allowed)
    output = output.model_copy(update={"signals": signals})

    text = _format_sector_text(sector_name, output)
    signals_out = []
    for signal in output.signals:
        if signal.signal == "BUY" and not signal.key_risk:
            logger.warning("Missing key_risk for BUY signal: %s in %s", signal.ticker, sector_name)
        signals_out.append(
            {
                "ticker": signal.ticker,
                "signal": signal.signal,
                "note": signal.note,
                "sector": sector_name,
                "key_risk": signal.key_risk,
                "confidence": signal.confidence,
            }
        )

    # Collect sub-agent beliefs via shared helper — fail loud on None beliefs.
    beliefs_out = collect_beliefs_from_views(
        [("technical", technical), ("news", news), ("enrichment", enrichment)],
        agent_key_prefix="sector",
        scope_name=f"sector:{sector_name}",
        logger=logger,
    )
    for aggregated_belief in output.beliefs:
        beliefs_out.append({"agent_key": "sector_aggregator", **aggregated_belief.model_dump()})

    return {"text": text, "signals": signals_out, "beliefs": beliefs_out}
