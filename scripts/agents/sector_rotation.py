#!/usr/bin/env python3
"""
Sector Rotation Agent using PydanticAI.

Detects hot and cold sectors based on RSI and regime awareness.
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)

from pydantic import BaseModel
from pydantic_ai import Agent

from shared.agent_config import load_agent_config

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout


class SectorRotationResult(BaseModel):
    """Sector rotation analysis result."""

    hot_sectors: list[str]
    cold_sectors: list[str]
    rotation_signal: str
    reasoning: str
    market_regime: str  # Current regime for context


async def create_rotation_agent(
    scan_date: date | None = None,
) -> Agent[AgentDeps, SectorRotationResult]:
    """Create a sector rotation agent with tools."""
    if scan_date is None:
        scan_date = date.today()
    config = await load_agent_config("sector_rotation")
    # HOOK-ALLOW: no-tickers-scope (sector_rotation operates on VN market scope)
    return create_agent(config, output_type=SectorRotationResult)


async def detect_rotation_with_agent(
    scan_date: date | None = None,
    sector_data_context: str = "",
    learnings_context: str = "",
    global_risk_regime: str | None = None,
) -> dict:
    """Detect sector rotation using the agentic approach.

    Args:
        scan_date: Date for data lookup (defaults to today)
        sector_data_context: Pre-fetched sector RSI/price data (injected)
        learnings_context: Pre-fetched rotation_patterns learnings (injected)
        global_risk_regime: Authoritative regime label from macro pipeline.
            Echoed into the result as ``global_risk_regime`` so downstream
            consumers always have the gate-aligned label (Phase 2 §2.8).

    Returns:
        Dict with hot_sectors, cold_sectors, rotation_signal, reasoning,
        market_regime (technical, context only) and global_risk_regime
        (authoritative — matches gate composition).
    """
    agent = await create_rotation_agent(scan_date)
    deps_scan_date = scan_date if scan_date is not None else date.today()

    injected_blocks = ""
    if sector_data_context:
        injected_blocks += f"{sector_data_context}\n\n"
    if learnings_context:
        injected_blocks += f"{learnings_context}\n\n"

    prompt = f"""{injected_blocks}Analyze sector rotation in the Vietnamese market.

Steps:
1. Review RSI and technical data above (pre-loaded)
2. Review rotation accuracy history above (pre-loaded)
3. Optionally search for sector news if signals are unclear
4. Identify hot sectors (receiving money) and cold sectors (losing money)
5. Determine the rotation signal

Apply regime awareness - in RISK_OFF, defensive sectors are HOT even if overbought."""

    # Resolve once — both branches echo this label so the gate-aligned
    # value never drifts between success and failure paths.
    authoritative_regime = global_risk_regime or "CAUTIOUS"
    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="sector_rotation",
            deps=AgentDeps(scan_date=deps_scan_date, agent_key="sector_rotation"),
            total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
        )
        # SWI-133 / Fix 5: producer-side reconcile so Logfire spans + raw
        # JSON outputs ship the gate-aligned regime, not the raw LLM
        # emission. Single source of truth — downstream consumers no
        # longer need to re-reconcile.
        from pipeline.helpers import reconcile_regimes

        reconciled_regime = reconcile_regimes(result.output.market_regime, authoritative_regime)
        return {
            "hot_sectors": result.output.hot_sectors,
            "cold_sectors": result.output.cold_sectors,
            "rotation_signal": result.output.rotation_signal,
            "reasoning": result.output.reasoning,
            "market_regime": reconciled_regime,
            "global_risk_regime": authoritative_regime,
        }
    except Exception as e:
        logger.warning("Sector rotation detection failed: %s", e)
        return {
            "hot_sectors": [],
            "cold_sectors": [],
            "rotation_signal": f"Error: {e}",
            "reasoning": "Sector rotation detection failed",
            "market_regime": "NEUTRAL",
            "global_risk_regime": authoritative_regime,
        }
