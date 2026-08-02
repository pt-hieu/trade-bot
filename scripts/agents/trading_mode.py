#!/usr/bin/env python3
"""
Trading Mode Agent using PydanticAI.

Determines the current trading mode based on capital status and position health.
"""

from datetime import date

from pydantic import BaseModel
from pydantic_ai import Agent

from shared.agent_config import load_agent_config
from shared.trading_config import get_trading_config

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout


class TradingModeResult(BaseModel):
    """Result from trading mode determination."""

    mode: str  # NORMAL, LOW_CASH, REALLOCATION
    reason: str
    stagnant_positions: list[str]  # Tickers to consider exiting
    reallocation_targets: list[str]  # Better opportunities


async def create_trading_mode_agent(
    scan_date: date | None = None,
) -> Agent[AgentDeps, TradingModeResult]:
    """Create a trading mode agent."""
    if scan_date is None:
        scan_date = date.today()
    config = await load_agent_config("trading_mode")
    # HOOK-ALLOW: no-tickers-scope (trading_mode is config-only, no ticker scope)
    return create_agent(config, output_type=TradingModeResult)


def determine_mode(deployable_cash: float) -> str:
    """Deterministic trading mode from deployable cash.

    Returns: NORMAL, LOW_CASH, or REALLOCATION.
    """
    low_cash_threshold = get_trading_config().low_cash_threshold
    if deployable_cash > low_cash_threshold:
        return "NORMAL"
    elif deployable_cash > 0:
        return "LOW_CASH"
    else:
        return "REALLOCATION"


async def determine_trading_mode(
    deployable_cash: float,
    position_alerts: dict,
    sector_rotation: dict,
    longterm_watchlist: list[str],
    scan_date: date | None = None,
    portfolio_context: str = "",
) -> dict:
    """Determine the current trading mode.

    Mode is deterministic from cash. LLM only used for REALLOCATION
    to identify stagnant positions and reallocation targets (qualitative).

    Args:
        deployable_cash: Available cash for trading (total - min_cash_reserve)
        position_alerts: Output from position monitor agent
        sector_rotation: Output from sector rotation agent
        longterm_watchlist: List of long-term core holding tickers
        scan_date: Date for data lookup

    Returns:
        Dict with mode, reason, stagnant_positions, reallocation_targets
    """
    mode = determine_mode(deployable_cash)

    # NORMAL: no LLM needed
    if mode == "NORMAL":
        return {
            "mode": "NORMAL",
            "reason": f"Deployable cash {deployable_cash:,.0f} VND is healthy",
            "stagnant_positions": [],
            "reallocation_targets": [],
        }

    # LOW_CASH: no LLM needed (only TRIM/EXIT allowed)
    if mode == "LOW_CASH":
        return {
            "mode": "LOW_CASH",
            "reason": f"Deployable cash {deployable_cash:,.0f} VND — only TRIM/EXIT",
            "stagnant_positions": [],
            "reallocation_targets": [],
        }

    # REALLOCATION: use LLM to identify stagnant positions (qualitative)
    alerts = position_alerts.get("alerts", [])
    hot_sectors = sector_rotation.get("hot", [])
    cold_sectors = sector_rotation.get("cold", [])

    alerts_str = ""
    for alert in alerts:
        ticker = alert.get("ticker", "")
        action = alert.get("action", "")
        urgency = alert.get("urgency", "")
        reason = alert.get("reason", "")
        target = alert.get("target", "N/A")
        stop = alert.get("stop", "N/A")
        alerts_str += (
            f"- {ticker}: {action} ({urgency}) - {reason} [Target: {target}, Stop: {stop}]\n"
        )

    if not alerts_str:
        alerts_str = "No position alerts available"

    portfolio_section = ""
    if portfolio_context:
        from pipeline.context_blocks import PORTFOLIO_HEADER

        portfolio_section = f"\n{PORTFOLIO_HEADER}\n{portfolio_context}\n"

    prompt = f"""Mode is REALLOCATION (zero deployable cash). Identify:
1. Stagnant positions to EXIT (skip long-term holdings)
2. Better reallocation targets from hot sectors
{portfolio_section}
## Position Alerts
{alerts_str}

## Sector Rotation
- HOT: {", ".join(hot_sectors) if hot_sectors else "None"}
- COLD: {", ".join(cold_sectors) if cold_sectors else "None"}

## Long-Term Holdings (DO NOT flag as stagnant)
{", ".join(longterm_watchlist) if longterm_watchlist else "None"}

Analyze positions using technical.get_technicals if needed."""

    agent = await create_trading_mode_agent(scan_date)
    deps_scan_date = scan_date if scan_date is not None else date.today()

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="trading_mode",
            deps=AgentDeps(
                scan_date=deps_scan_date,
                agent_key="trading_mode",
                hot_sectors=list(hot_sectors),
                cold_sectors=list(cold_sectors),
                holdings_tickers=list(longterm_watchlist or []),
            ),
            total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
        )
        return {
            "mode": "REALLOCATION",
            "reason": result.output.reason,
            "stagnant_positions": result.output.stagnant_positions,
            "reallocation_targets": result.output.reallocation_targets,
        }
    except Exception as e:
        return {
            "mode": "REALLOCATION",
            "reason": f"Zero cash, LLM analysis failed ({e})",
            "stagnant_positions": [],
            "reallocation_targets": [],
        }
