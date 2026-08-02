#!/usr/bin/env python3
"""
Ensemble Position Monitor — 3 analyst committee + aggregator.

Replaces single position monitor with diverse perspectives:
  - Technical Analyst: price action, stops, momentum
  - Value Analyst: fundamentals, fair value, entry zones
  - Thesis Analyst: investment thesis, catalysts, sector outlook
  - Aggregator: resolves conflicts, produces final alerts

Architecture: Parallel Ensemble (fan-out → fan-in).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.enrichment_loader import EnrichmentData
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.errors import report_caught
from shared.neon import insert_ensemble_votes
from shared.neon.position_alerts import (
    get_morning_position_alerts,
    upsert_with_passthrough,
)
from shared.observability import emit_silent_provider_hang_span

from .agent_factory import AgentDeps, create_agent
from .ensemble_concurrency import gated_fanout
from .model.wrappers import (
    OUTER_FALLBACK_STACK_WALL_S,
    await_with_hop_unwrap,
    downstream_provider_from_timeout,
    provider_slug_from_timeout,
)
from .positions_ensemble_aggregator import aggregate_analyst_reports
from .positions_ensemble_models import AnalystReport, AnalystView
from .positions_ensemble_rules import (
    compute_portfolio_drawdown_context,
    enforce_concentration_limits,
)
from .tools.portfolio import get_holdings_async

# Re-export models so existing callers importing from this module keep working
__all__ = [
    "AnalystView",
    "AnalystReport",
    "compute_portfolio_drawdown_context",
    "enforce_concentration_limits",
    "monitor_positions_ensemble",
]

logger = logging.getLogger(__name__)


# ── Analyst Factory ───────────────────────────────────────────────────────


async def _create_technical_agent() -> tuple[Agent[AgentDeps, AnalystReport], AgentConfig]:
    """Technical analyst: price action, stops, momentum."""
    config = await load_agent_config("positions_technical")
    return create_agent(config, output_type=AnalystReport), config


async def _create_value_agent() -> tuple[Agent[AgentDeps, AnalystReport], AgentConfig]:
    """Value analyst: fundamentals, fair value, entry zones."""
    config = await load_agent_config("positions_value")
    return create_agent(config, output_type=AnalystReport), config


async def _create_thesis_agent() -> tuple[Agent[AgentDeps, AnalystReport], AgentConfig]:
    """Thesis analyst: investment thesis, catalysts, sector outlook."""
    config = await load_agent_config("positions_thesis")
    return create_agent(config, output_type=AnalystReport), config


# ── Run Individual Analyst ────────────────────────────────────────────────


async def _run_analyst(
    analyst_type: str,
    scan_date: date,
    trailing_stops_context: str = "",
    sector_context: str = "",
    drawdown_context: str = "",
    geopolitical_context: str = "",
    portfolio_context: str = "",
    regime_context: str = "",
    ticker_briefings: str = "",
    calibration_context: str = "",
    tickers_in_scope: list[str] | None = None,
) -> AnalystReport:
    """Create and run a single analyst agent.

    ``tickers_in_scope`` is the held-ticker list. When the model emits a
    broker call missing the required ``tickers`` argument, the broker
    appends the in-scope list to the validation hint so the next retry
    self-corrects on the first attempt.
    """
    creators = {
        "technical": _create_technical_agent,
        "value": _create_value_agent,
        "thesis": _create_thesis_agent,
    }
    agent, config = await creators[analyst_type]()
    prompt = f"Analyze all portfolio positions from your {analyst_type} perspective."
    # Prepend injected context (high attention at beginning)
    if ticker_briefings:
        prompt = f"{ticker_briefings}\n\n{prompt}"
    if calibration_context:
        prompt = f"{calibration_context}\n\n{prompt}"
    if regime_context:
        prompt = f"{regime_context}\n\n{prompt}"
    if portfolio_context:
        from pipeline.context_blocks import PORTFOLIO_HEADER

        prompt = f"{PORTFOLIO_HEADER}\n{portfolio_context}\n\n{prompt}"
    if sector_context:
        prompt += f"\n\n{sector_context}"
    if trailing_stops_context:
        prompt += f"\n\n{trailing_stops_context}"
    if drawdown_context:
        prompt += f"\n\n{drawdown_context}"
    if geopolitical_context:
        prompt += f"\n\n{geopolitical_context}"

    per_analyst_wall_s = int(OUTER_FALLBACK_STACK_WALL_S)

    for attempt in range(2):
        try:
            # HOOK-ALLOW: unguarded-agent-run reason=wrapped by await_with_hop_unwrap
            result = await await_with_hop_unwrap(
                agent.run(
                    prompt,
                    deps=AgentDeps(
                        scan_date=scan_date,
                        agent_key=getattr(config, "agent_key", "") or analyst_type,
                        tickers_in_scope=list(tickers_in_scope or []),
                    ),
                    usage_limits=build_usage_limits(config),
                ),
                timeout=per_analyst_wall_s,
            )
            return result.output
        except UsageLimitExceeded as e:
            # Deterministic failure — retry always fails identically, skip immediately
            logger.warning("Positions %s analyst hit usage limit (no retry): %s", analyst_type, e)
            return AnalystReport(
                views=[],
                summary=f"{analyst_type} analyst hit usage limit: {e}",
            )
        except (ValidationError, UnexpectedModelBehavior) as schema_err:
            # Schema contract violation — PydanticAI already retried twice via
            # output_retries. Re-raise so the caller sees the failure rather
            # than silently emitting an empty report.
            logger.error(
                "Positions %s analyst schema failure (no retry): %s", analyst_type, schema_err
            )
            raise
        except TimeoutError as timeout_exc:
            emit_silent_provider_hang_span(
                agent=f"positions_{analyst_type}",
                wall_s=per_analyst_wall_s,
                exception_type=type(timeout_exc).__name__,
                logger=logger,
                provider=provider_slug_from_timeout(timeout_exc),
                downstream_provider=downstream_provider_from_timeout(timeout_exc),
            )
            if attempt == 0:
                logger.warning(
                    "Positions %s analyst hit %ds wall (attempt 1) — retrying",
                    analyst_type,
                    per_analyst_wall_s,
                )
                continue
            logger.warning(
                "Positions %s analyst hit %ds wall (attempt 2) — giving up",
                analyst_type,
                per_analyst_wall_s,
            )
            return AnalystReport(
                views=[],
                summary=f"{analyst_type} analyst timed out after 2 attempts",
            )
        except Exception as e:
            # Transient: network flake, tool flake, JSON decode flake. Retry.
            if attempt == 0:
                logger.warning(
                    "Positions %s analyst failed (attempt 1): %s — retrying in 5s",
                    analyst_type,
                    e,
                )
                await asyncio.sleep(5)
            else:
                logger.warning("Positions %s analyst failed (attempt 2): %s", analyst_type, e)
                return AnalystReport(
                    views=[],
                    summary=f"{analyst_type} analyst transient failure after 2 attempts: {e}",
                )

    return AnalystReport(views=[], summary=f"{analyst_type} analyst failed")  # unreachable


# ── Public Entry Point ────────────────────────────────────────────────────


async def monitor_positions_ensemble(
    scan_date: date | None = None,
    trailing_stops_context: str = "",
    sector_rotation: dict | None = None,
    geopolitical_context: str = "",
    holdings: list | None = None,
    cash_balance: float = 0.0,
    deployable_cash: float = 0.0,
    market_level_dict: dict | None = None,
    macro_metrics_dict: dict | None = None,
    technicals: dict | None = None,
    enrichment_data: EnrichmentData | None = None,
    market_valuation: dict | None = None,
    commodity_prices: dict | None = None,
) -> dict:
    """Monitor positions using ensemble of 3 analysts + aggregator.

    Drop-in replacement for monitor_positions_with_agent().

    Args:
        scan_date: Date for analysis
        trailing_stops_context: Pre-computed trailing stops text to inject
        sector_rotation: Current sector rotation (hot/cold sectors) from Phase 1
        holdings: Pre-loaded holdings dict from PipelineContext
        cash_balance: Total cash in VND (from PipelineContext)
        deployable_cash: Deployable cash in VND (from PipelineContext)
        market_level_dict: Full Phase 1 market_level dict for compact regime block injection
        macro_metrics_dict: Full Phase 1 macro_metrics dict for compact regime block injection
        technicals: Batch-fetched technicals dict from Phase 0
        enrichment_data: EnrichmentData with flow, insider, RS for ticker briefing injection
        market_valuation: VN-Index PE/PB data from Phase 1 for regime context
        commodity_prices: Live commodity prices for per-ticker transmission

    Returns:
        Dict with alerts list and summary (same format).
    """
    if scan_date is None:
        scan_date = date.today()

    # Use pre-loaded holdings or fallback to fetch
    holdings_list: list = list(holdings) if holdings else []
    if not holdings_list:
        try:
            holdings_data = await get_holdings_async()
            if holdings_data and not holdings_data.get("error"):
                fetched = holdings_data.get("holdings", [])
                if isinstance(fetched, list):
                    holdings_list = fetched
        except Exception as e:
            report_caught("positions_ensemble.holdings_fetch", e)

    drawdown_context = ""
    if holdings_list:
        drawdown_context = compute_portfolio_drawdown_context(holdings_list)
        if drawdown_context:
            print(f"  [positions_ensemble] {drawdown_context.split(chr(10))[1]}")

    # Build compact portfolio context for injection
    from pipeline.context_blocks import (
        format_portfolio_block,
        format_regime_block,
        format_ticker_briefings,
    )
    from pipeline.context_blocks_calibration import build_calibration_blocks
    from pipeline.context_blocks_position_data import (
        format_thesis_pillars_block,
        format_valuation_block,
    )
    from pipeline.enrichment_position_data import extract_held_tickers

    portfolio_context = format_portfolio_block(holdings_list, cash_balance, deployable_cash)
    regime_context = format_regime_block(
        market_level_dict, macro_metrics_dict, market_valuation=market_valuation
    )

    # Build per-agent ticker briefings so each sees its OWN prior belief —
    # dedupe across dual-listed slices so we don't double-render a ticker.
    held_tickers = extract_held_tickers(holdings_list)
    geopolitical_shock = (macro_metrics_dict or {}).get("geopolitical_shock")
    briefings_technical = format_ticker_briefings(
        tickers=held_tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices=commodity_prices,
        macro_metrics=macro_metrics_dict,
        geopolitical_shock=geopolitical_shock,
        agent_key="positions_technical",
    )
    briefings_value = format_ticker_briefings(
        tickers=held_tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices=commodity_prices,
        macro_metrics=macro_metrics_dict,
        geopolitical_shock=geopolitical_shock,
        agent_key="positions_value",
    )
    briefings_thesis = format_ticker_briefings(
        tickers=held_tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices=commodity_prices,
        macro_metrics=macro_metrics_dict,
        geopolitical_shock=geopolitical_shock,
        agent_key="positions_thesis",
    )

    # Inject Phase-0-batched thesis + valuation so positions_thesis / positions_value
    # never need portfolio.get_thesis / fundamental.get_full_analysis tool calls.
    thesis_block = format_thesis_pillars_block(
        enrichment_data.position_thesis_prose if enrichment_data else {}
    )
    valuation_block = format_valuation_block(
        enrichment_data.position_valuation_prose if enrichment_data else {}
    )
    if thesis_block:
        briefings_thesis = f"{thesis_block}\n\n{briefings_thesis}"
    if valuation_block:
        briefings_value = f"{valuation_block}\n\n{briefings_value}"

    # Build per-agent calibration context from pre-fetched belief accuracy
    calibration = build_calibration_blocks(
        enrichment_data, ["positions_technical", "positions_value", "positions_thesis"]
    )

    # Build sector context string for analyst prompts
    sector_context = ""
    if sector_rotation:
        hot = sector_rotation.get("hot_sectors", [])
        cold = sector_rotation.get("cold_sectors", [])
        if hot or cold:
            sector_context = (
                "SECTOR ROTATION CONTEXT\n"
                f"Hot sectors (momentum tailwind): {', '.join(hot) or 'None'}\n"
                f"Cold sectors (momentum headwind): {', '.join(cold) or 'None'}\n"
                "Factor this into your position analysis — holdings in cold sectors "
                "may need earlier exits; hot sectors may support holding longer."
            )

    # Serialize the 3 analysts. Concurrent inflight LLM requests on one
    # OpenRouter key hit tail-latency stalls past the per-hop wall
    # (2026-04-20 silent-hang incident; serial Kimi 0% hang vs parallel
    # 30-60%). gated_fanout() is the shared cap — see ensemble_concurrency.
    _gated = gated_fanout()

    held_tickers_for_scope = list(held_tickers)

    # Coroutine builder for the gated fan-out. Per gated_fanout()'s contract
    # this MUST NOT raise — it only forwards args into the _run_analyst
    # coroutine constructor; keep it that way so a sibling failure during
    # gather assembly cannot leak an unawaited coroutine.
    def _analyst(analyst_type: str, briefings: str, calibration_context: str):
        return _run_analyst(
            analyst_type,
            scan_date=scan_date,
            trailing_stops_context=trailing_stops_context,
            sector_context=sector_context,
            drawdown_context=drawdown_context,
            geopolitical_context=geopolitical_context,
            portfolio_context=portfolio_context,
            regime_context=regime_context,
            ticker_briefings=briefings,
            calibration_context=calibration_context,
            tickers_in_scope=held_tickers_for_scope,
        )

    technical, value, thesis = await asyncio.gather(
        _gated(
            _analyst("technical", briefings_technical, calibration.get("positions_technical", ""))
        ),
        _gated(_analyst("value", briefings_value, calibration.get("positions_value", ""))),
        _gated(_analyst("thesis", briefings_thesis, calibration.get("positions_thesis", ""))),
    )

    # Persist analyst votes for audit trail
    votes = []
    for analyst_type, report in [("technical", technical), ("value", value), ("thesis", thesis)]:
        for view in report.views:
            votes.append(
                {
                    "ticker": view.ticker,
                    "analyst_type": analyst_type,
                    "action": view.action,
                    "confidence": view.confidence,
                    "reasoning": view.reasoning,
                    "counter_thesis": view.counter_thesis,
                }
            )
    await insert_ensemble_votes(scan_date, votes)

    # Read prior alerts from a previous retry attempt within the same scan_date
    # so the deterministic preserve_higher_urgency / COVERAGE_GAP_OVERRIDE rules
    # can merge across processes (SWI-183: GH Actions retry restarts as a fresh
    # process with no in-memory state).
    try:
        prior_alerts = await get_morning_position_alerts(scan_date)
    except Exception as exc:
        report_caught("positions_ensemble.prior_alerts_load", exc)
        prior_alerts = []
    if prior_alerts:
        logger.info(
            "positions_aggregator: loaded %d prior alerts from %s for cross-retry merge",
            len(prior_alerts),
            scan_date,
        )

    # Fan-in: aggregate (with regime + drawdown + sector + geopolitical context for conflict resolution)
    result = await aggregate_analyst_reports(
        technical,
        value,
        thesis,
        scan_date,
        sector_context,
        drawdown_context,
        geopolitical_context,
        regime_context,
        prior_alerts=prior_alerts,
    )

    alerts = list(result.get("alerts") or [])

    # Post-LLM deterministic safety net: enforce concentration + gain limits.
    # Structural invariant — counts/weights only; does NOT downgrade qualitative
    # actions. See agent-development skill: "Python / LLM split".
    try:
        if holdings_list:
            alerts = enforce_concentration_limits(alerts, holdings_list)
            overrides = [
                alert for alert in alerts if "[CONCENTRATION OVERRIDE]" in alert.get("reason", "")
            ]
            if overrides:
                print(
                    "  [positions_ensemble] Concentration overrides: "
                    + ", ".join(f"{alert['ticker']} → {alert['action']}" for alert in overrides)
                )
    except Exception as e:
        report_caught("positions_ensemble.concentration_enforcement", e)

    # Stamp coverage health LAST so concentration-injected alerts also carry it.
    responding, total, label = _compute_coverage_health(technical, value, thesis)
    for alert in alerts:
        alert["coverage_responding"] = responding
        alert["coverage_total"] = total
        alert["coverage_health"] = label

    result = dict(result)
    result["alerts"] = alerts

    # Persist immediately so a retry-killed process leaves prior_alerts behind
    # for the next attempt. phase_postprocess.py also re-upserts as a safety
    # net — that re-upsert is harmless under ON CONFLICT DO UPDATE.
    try:
        persisted = await upsert_with_passthrough(scan_date, alerts)
        logger.info(
            "positions_aggregator: upserted %d alerts (atomic in-monitor write)",
            persisted,
        )
    except Exception as exc:
        report_caught("positions_ensemble.upsert_with_passthrough", exc)

    return result


def _compute_coverage_health(
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
) -> tuple[int, int, str]:
    """Return (responding, total, label) for coverage health stamping.

    An analyst is "responding" when its report carries at least one view.
    Empty-views reports come from usage-limit / timeout / transient-failure
    paths in `_run_analyst` and represent a degraded coverage signal.
    """
    reports = (technical, value, thesis)
    responding = sum(1 for r in reports if r.views)
    total = len(reports)
    return responding, total, f"{responding}/{total}"
