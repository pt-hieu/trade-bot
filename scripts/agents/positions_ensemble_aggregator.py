"""Aggregator agent for positions ensemble — fan-in step."""

from __future__ import annotations

import logging
from datetime import date

from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior

from shared.agent_config import build_usage_limits, load_agent_config
from shared.errors import ProviderUnavailable
from shared.observability import emit_silent_provider_hang_span, emit_ticker_drop_span

from .agent_factory import AgentDeps, create_agent
from .belief_collection import collect_beliefs_from_views
from .model.wrappers import (
    OUTER_DISABLE_FALLBACK_WALL_S,
    downstream_provider_from_timeout,
    provider_slug_from_timeout,
)
from .positions import PositionMonitorResult
from .positions_ensemble_fallback import (
    collect_ticker_union,
    derive_alerts_from_subreports,
)
from .positions_ensemble_models import AnalystReport
from .positions_ensemble_rules import _calc_consensus, _get_dissent
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)

_AGGREGATOR_PHASE_WALL_SECONDS = int(OUTER_DISABLE_FALLBACK_WALL_S)


def _format_coverage_health_block(
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
) -> str:
    """Compact text block reporting how many analysts returned views.

    Injected into the aggregator prompt so the LLM can apply the
    "COVERAGE HEALTH JUDGMENT" rule from positions_aggregator.yaml.
    Coverage count is deterministic Python; the action decision under
    that count remains the LLM's call.
    """
    pairs = [("technical", technical), ("value", value), ("thesis", thesis)]
    responding = [name for name, report in pairs if report.views]
    missing = [name for name, report in pairs if not report.views]
    label = f"{len(responding)}/{len(pairs)}"
    lines = [
        "## COVERAGE HEALTH",
        f"Analysts responding: {label} ({', '.join(responding) or 'none'})",
    ]
    if missing:
        lines.append(f"Analysts missing: {', '.join(missing)}")
    return "\n".join(lines)


def _format_analyst_report(name: str, report: AnalystReport) -> str:
    """Render one analyst report as a compact text block for aggregator context."""
    lines = [f"## {name} Analyst Report", f"Summary: {report.summary}"]
    for view in report.views:
        counter = f" | COUNTER: {view.counter_thesis}" if view.counter_thesis else ""
        lines.append(
            f"- {view.ticker}: {view.action} (confidence {view.confidence}/10) — "
            f"{view.reasoning}{counter}"
        )
        belief = view.belief
        lines.append(
            f"  BELIEF: {belief.direction} "
            f"(bull={belief.bull_probability:.2f} base={belief.base_probability:.2f} "
            f"bear={belief.bear_probability:.2f}) "
            f"conviction={belief.conviction:.2f} [{belief.belief_status}]"
        )
    return "\n".join(lines)


def _collect_beliefs(
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
    aggregated: list,
) -> list[dict]:
    beliefs = collect_beliefs_from_views(
        [("technical", technical), ("value", value), ("thesis", thesis)],
        agent_key_prefix="positions",
        scope_name="positions",
        logger=logger,
    )
    for aggregated_belief in aggregated:
        beliefs.append({"agent_key": "positions_aggregator", **aggregated_belief.model_dump()})
    return beliefs


def _enrich_alert(
    alert,
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
) -> dict:
    if alert.action.upper() in ("EXIT", "TRIM") and not alert.counter_thesis:
        logger.warning("Missing counter_thesis for %s %s", alert.action, alert.ticker)
    enriched = alert.model_dump()
    enriched["consensus"] = _calc_consensus(alert.ticker, alert.action, technical, value, thesis)
    enriched["dissenting_views"] = _get_dissent(
        alert.ticker, alert.action, technical, value, thesis
    )
    return enriched


async def aggregate_analyst_reports(
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
    scan_date: date,
    sector_context: str = "",
    drawdown_context: str = "",
    geopolitical_context: str = "",
    regime_context: str = "",
    prior_alerts: list[dict] | None = None,
) -> dict:
    """Aggregate 3 analyst reports into final position alerts.

    ``prior_alerts``: when a prior aggregator run within the same
    scan_date succeeded with higher-urgency actions, pass them here so
    the deterministic ``preserve_higher_urgency`` rule can prevent a
    cross-run silent EXIT→HOLD downgrade (Phase 2 §2.4).
    """
    config = await load_agent_config("positions_aggregator")
    # HOOK-ALLOW: no-broker-tools (fan-in synthesizer of 3 sub-reports; no tool surface)
    agent = create_agent(config, output_type=PositionMonitorResult)

    coverage_block = _format_coverage_health_block(technical, value, thesis)
    run_prompt = (
        f"{coverage_block}\n\n"
        "Here are the 3 analyst reports on current portfolio positions.\n"
        "Synthesize them into final recommendations per the conflict resolution rules.\n\n"
        + "\n\n".join(
            [
                _format_analyst_report("Technical", technical),
                _format_analyst_report("Value", value),
                _format_analyst_report("Thesis", thesis),
            ]
        )
    )
    for prefix in (regime_context, sector_context, drawdown_context, geopolitical_context):
        if prefix:
            run_prompt = f"{prefix}\n\n{run_prompt}"

    try:
        result = await run_agent_with_total_timeout(
            agent,
            run_prompt,
            agent_name="positions_aggregator",
            deps=AgentDeps(
                scan_date=None,
                agent_key="positions_aggregator",
                tickers_in_scope=sorted(collect_ticker_union(technical, value, thesis)),
            ),
            total_timeout_s=float(_AGGREGATOR_PHASE_WALL_SECONDS),
            usage_limits=build_usage_limits(config),
        )
        emit_ticker_drop_span(
            agent="positions_aggregator",
            expected=collect_ticker_union(technical, value, thesis),
            produced={alert.ticker.upper() for alert in result.output.alerts},
            logger=logger,
        )
        alerts = [_enrich_alert(alert, technical, value, thesis) for alert in result.output.alerts]
        beliefs = _collect_beliefs(technical, value, thesis, result.output.beliefs)
        if prior_alerts:
            from shared.rules.aggregator_passthrough import preserve_higher_urgency

            alerts = preserve_higher_urgency(prior_alerts, alerts)
        return {"alerts": alerts, "summary": result.output.summary, "beliefs": beliefs}

    except (TimeoutError, ProviderUnavailable) as degradation:
        # Zero-alerts on real holdings is strictly worse than on watchlist
        # picks — derive conservative HOLD/TRIM/EXIT from sub-agents instead.
        logger.error(
            "positions_aggregator degraded (%s): %s — using sub-agent fallback",
            type(degradation).__name__,
            degradation,
        )
        if isinstance(degradation, TimeoutError):
            # Alertable span — replaces the tokens=None/None heuristic
            # used by pipeline-review (MON-2026-04-13-002).
            emit_silent_provider_hang_span(
                agent="positions_aggregator",
                wall_s=_AGGREGATOR_PHASE_WALL_SECONDS,
                exception_type=type(degradation).__name__,
                logger=logger,
                provider=provider_slug_from_timeout(degradation),
                downstream_provider=downstream_provider_from_timeout(degradation),
            )
        fallback_result = derive_alerts_from_subreports(
            technical=technical,
            value=value,
            thesis=thesis,
            degradation_type=type(degradation).__name__,
        )
        if prior_alerts:
            from shared.rules.aggregator_passthrough import preserve_higher_urgency

            fallback_result["alerts"] = preserve_higher_urgency(
                prior_alerts, fallback_result.get("alerts") or []
            )
        return fallback_result
    except (ValidationError, UnexpectedModelBehavior) as schema_err:
        # Schema contract violation — do not swallow.
        logger.error("positions_aggregator schema failure (no retry): %s", schema_err)
        raise
    except Exception as error:
        logger.exception("positions_aggregator unexpected error")
        return {
            "alerts": [],
            "summary": f"Aggregator failed: {error}",
            "beliefs": [],
            "error": str(error),
        }
