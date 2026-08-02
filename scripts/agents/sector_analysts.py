#!/usr/bin/env python3
"""
Sector Analyst Sub-Agents — fan-out layer for sector ensemble.

Three specialized analysts run in parallel:
  - Technical: price action, momentum, relative strength
  - News: articles, catalysts, sentiment
  - Enrichment: flow, insider activity, valuation history

Each returns a SectorAnalystReport consumed by the sector aggregator.
"""

import asyncio
import logging
import time
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

from shared.agent_config import build_usage_limits, load_agent_config
from shared.observability import emit_silent_provider_hang_span
from shared.observability import span as logfire_span

from .agent_factory import AgentDeps, create_agent
from .belief_models import TickerBelief
from .model.wrappers import (
    OUTER_FALLBACK_STACK_WALL_S,
    await_with_hop_unwrap,
    downstream_provider_from_timeout,
    provider_slug_from_timeout,
)
from .tools.native_tools import BrokerLoopBreaker

# SWI-180: native BrokerLoopBreaker kinds (iteration_limit, error_signature,
# unlock_overuse) are all terminal — re-prompting the same model with the same
# context will trip them again. Keep the empty set so the recoverable branch
# below is dormant; revisit if a future kind becomes legitimately retryable.
RECOVERABLE_BREAKER_KINDS: frozenset[str] = frozenset()

logger = logging.getLogger(__name__)


class SectorAnalystTimeout(RuntimeError):
    """SWI-141 / Fix 7c: analyst hung past the per-attempt wall on both
    retries. Raising forces the upstream gather to count this as a
    failed_sector_count + lets the per-ticker coverage gate surface the
    silent-partial publish that the prior shaped-like-success return
    enabled."""

    def __init__(self, sector_name: str, analyst_type: str, wall_s: int) -> None:
        super().__init__(
            f"Sector {sector_name} {analyst_type} analyst hit {wall_s}s wall "
            f"on both attempts — raising so failed_sector_count increments"
        )
        self.sector_name = sector_name
        self.analyst_type = analyst_type


class SectorAnalystFailure(RuntimeError):
    """Mirrors SectorAnalystTimeout for the non-Timeout exception path."""

    def __init__(self, sector_name: str, analyst_type: str, cause: Exception) -> None:
        super().__init__(
            f"Sector {sector_name} {analyst_type} analyst transient failure "
            f"after 2 attempts: {cause}"
        )
        self.sector_name = sector_name
        self.analyst_type = analyst_type
        self.__cause__ = cause


# ── Analyst Output Models ─────────────────────────────────────────────────


class SectorAnalystView(BaseModel):
    """Single analyst's view on one ticker."""

    ticker: str
    signal: Literal["BUY", "WATCH", "WAIT", "AVOID"]
    confidence: int  # 1-10
    reasoning: str = Field(max_length=300)  # 2-3 sentences max
    key_risk: str | None = Field(default=None, max_length=200)  # 1 sentence counter-argument
    belief: TickerBelief  # REQUIRED — see BELIEF OUTPUT FORMAT in agent yaml


class SectorAnalystReport(BaseModel):
    """Full report from one sector analyst covering all tickers."""

    views: list[SectorAnalystView]
    summary: str = Field(max_length=500)  # 2-3 sentences sector overview


# ── Analyst Config Keys ───────────────────────────────────────────────────

_ANALYST_KEYS = {
    "technical": "sector_technical",
    "news": "sector_news",
    "enrichment": "sector_enrichment",
}


# ── Run Individual Analyst ────────────────────────────────────────────────


async def _run_sector_analyst(
    analyst_type: str,
    sector_name: str,
    tickers: list[str],
    scan_date: date,
    regime_context: str = "",
    ticker_briefings: str = "",
    articles_context: str = "",
    calibration_context: str = "",
    shared_cache: dict | None = None,
) -> SectorAnalystReport:
    """Load config, create agent, run analyst, return SectorAnalystReport.

    Args:
        analyst_type: "technical", "news", or "enrichment"
        sector_name: e.g. "banking"
        tickers: list of tickers in this sector
        scan_date: analysis date
        regime_context: optional regime text injected into prompt
        ticker_briefings: pre-built compact briefings for all sector tickers (context injection)
        articles_context: pre-built article headlines for news analyst (context injection)
        calibration_context: pre-fetched belief accuracy for this agent (context injection)
        shared_cache: optional per-sector dict shared across the 3 sibling analysts so
            repeated tool calls (e.g. `narrative.get_active`) for the same ticker set
            hit the cache instead of refetching.

    Returns:
        SectorAnalystReport (empty views + error summary on failure)
    """
    agent_key = _ANALYST_KEYS[analyst_type]
    tickers_str = ", ".join(tickers)

    prompt = (
        f"Analyze {sector_name} sector tickers: {tickers_str}\n"
        f"Provide your {analyst_type} assessment."
    )
    # Prepend injected context blocks (attention ordering: critical data at beginning)
    if ticker_briefings:
        prompt = f"{ticker_briefings}\n\n{prompt}"
    if calibration_context:
        prompt = f"{calibration_context}\n\n{prompt}"
    if articles_context and analyst_type == "news":
        prompt = f"{articles_context}\n\n{prompt}"
    if regime_context:
        prompt = f"{regime_context}\n\n{prompt}"

    # ``tickers_in_scope`` arms the broker's missing-``tickers`` hint with
    # the exact sector member list, so a GLM-5 ``args:{}`` retry on a
    # batch tool (fundamental.get_full_analysis, technical.get_technicals)
    # gets coached on the first attempt instead of looping.
    config = await load_agent_config(agent_key)
    deps = AgentDeps(
        scan_date=scan_date,
        agent_key=agent_key,
        tickers_in_scope=list(tickers),
        tool_cache=shared_cache if shared_cache is not None else {},
    )
    agent = create_agent(config, output_type=SectorAnalystReport)
    usage_limits = build_usage_limits(config)

    per_attempt_wall_s = int(OUTER_FALLBACK_STACK_WALL_S)

    for attempt in range(2):
        attempt_start = time.monotonic()
        try:
            with logfire_span(
                "sector_subagent_attempt",
                analyst_type=analyst_type,
                sector_name=sector_name,
                ticker_count=len(tickers),
                attempt=attempt + 1,
                wall_s_budget=per_attempt_wall_s,
            ):
                # HOOK-ALLOW: unguarded-agent-run reason=wrapped by await_with_hop_unwrap
                result = await await_with_hop_unwrap(
                    agent.run(prompt, deps=deps, usage_limits=usage_limits),
                    timeout=per_attempt_wall_s,
                )
            return result.output
        except BrokerLoopBreaker as breaker:
            # New (2026-05-04): broker tool-loop signal. Distinct from a
            # schema-unsatisfiable UnexpectedModelBehavior — the data needed
            # to answer is already in context, the model just won't stop
            # poking. Recoverable kinds may benefit from one same-model
            # retry (the breaker message is fed back as a hint and GLM-5
            # sometimes recovers); terminal kinds degrade-return so the
            # sector's existing 1-2-failed branch can produce signals from
            # the surviving sub-agents via _derive_signals_from_subreports.
            recoverable = breaker.breaker_kind in RECOVERABLE_BREAKER_KINDS
            if recoverable and attempt == 0:
                logger.warning(
                    "Sector %s %s analyst hit broker loop-breaker "
                    "(%s, attempt 1) — retrying same model with breaker "
                    "hint fed back",
                    sector_name,
                    analyst_type,
                    breaker.breaker_kind,
                )
                continue
            with logfire_span(
                "sector_subagent_loopbreaker_degraded",
                breaker_kind=breaker.breaker_kind,
                analyst_type=analyst_type,
                sector_name=sector_name,
                attempt=attempt,
            ):
                pass
            logger.warning(
                "Sector %s %s analyst broker loop-breaker terminal "
                "(%s, attempt %d) — degrading to empty-views report",
                sector_name,
                analyst_type,
                breaker.breaker_kind,
                attempt + 1,
            )
            return SectorAnalystReport(
                views=[],
                summary=(
                    f"[BROKER_LOOP_DEGRADED:{breaker.breaker_kind}] "
                    f"{analyst_type} analyst tripped loop-breaker on "
                    f"attempt {attempt + 1}."
                ),
            )
        except UsageLimitExceeded as e:
            # Deterministic failure — retry always fails identically, skip immediately
            logger.warning(
                "Sector %s %s analyst hit usage limit (no retry): %s",
                sector_name,
                analyst_type,
                e,
            )
            return SectorAnalystReport(
                views=[],
                summary=f"{analyst_type} analyst hit usage limit: {e}",
            )
        except (ValidationError, UnexpectedModelBehavior) as schema_err:
            # Schema contract violation. PydanticAI already retried twice
            # internally (output_retries=2); an outer retry won't help if
            # the model structurally can't satisfy the schema. Re-raise
            # so sector.py sees the exception and the sector is marked
            # failed via the phase_parallel isinstance(value, Exception)
            # branch.
            logger.error(
                "Sector %s %s analyst schema failure (no retry): %s",
                sector_name,
                analyst_type,
                schema_err,
            )
            raise
        except TimeoutError as timeout_exc:
            measured_wall_s = time.monotonic() - attempt_start
            slug = provider_slug_from_timeout(timeout_exc)
            logger.warning(
                "sector_subagent_attempt timed out: sector=%s analyst=%s ticker_count=%d "
                "attempt=%d measured_wall_s=%.1f budget=%ds provider=%s",
                sector_name,
                analyst_type,
                len(tickers),
                attempt + 1,
                measured_wall_s,
                per_attempt_wall_s,
                slug or "unknown",
            )
            emit_silent_provider_hang_span(
                agent=agent_key,
                wall_s=per_attempt_wall_s,
                exception_type=type(timeout_exc).__name__,
                logger=logger,
                provider=slug,
                downstream_provider=downstream_provider_from_timeout(timeout_exc),
                sector=sector_name,
            )
            if attempt == 0:
                logger.warning(
                    "Sector %s %s analyst hit %ds wall (attempt 1) — retrying",
                    sector_name,
                    analyst_type,
                    per_attempt_wall_s,
                )
                continue
            logger.warning(
                "Sector %s %s analyst hit %ds wall (attempt 2) — raising",
                sector_name,
                analyst_type,
                per_attempt_wall_s,
            )
            raise SectorAnalystTimeout(sector_name, analyst_type, per_attempt_wall_s) from None
        except Exception as e:
            # Transient: network flake, tool flake, JSON decode flake. Retry.
            if attempt == 0:
                logger.warning(
                    "Sector %s %s analyst failed (attempt 1): %s — retrying in 5s",
                    sector_name,
                    analyst_type,
                    e,
                )
                await asyncio.sleep(5)
            else:
                logger.warning(
                    "Sector %s %s analyst failed (attempt 2): %s — raising",
                    sector_name,
                    analyst_type,
                    e,
                )
                raise SectorAnalystFailure(sector_name, analyst_type, e) from e

    return SectorAnalystReport(views=[], summary=f"{analyst_type} analyst failed")  # unreachable


# ── Report Formatter ──────────────────────────────────────────────────────


def _fmt_sector_report(name: str, report: SectorAnalystReport) -> str:
    """Format a SectorAnalystReport as plain text for the aggregator prompt."""
    lines = [f"## {name.title()} Analyst Report"]
    lines.append(f"Summary: {report.summary}")
    for v in report.views:
        risk_suffix = f" | KEY RISK: {v.key_risk}" if v.key_risk else ""
        lines.append(
            f"- {v.ticker}: {v.signal} (confidence {v.confidence}/10) — {v.reasoning}{risk_suffix}"
        )
        belief = v.belief
        lines.append(
            f"  BELIEF: {belief.direction} "
            f"(bull={belief.bull_probability:.2f} base={belief.base_probability:.2f} "
            f"bear={belief.bear_probability:.2f}) "
            f"conviction={belief.conviction:.2f} target={belief.price_target_vnd:,} "
            f"in {belief.timeframe_days}d [{belief.belief_status}]"
        )
        lines.append(f'  "{belief.belief_narrative}"')
    return "\n".join(lines)
