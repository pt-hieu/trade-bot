#!/usr/bin/env python3
"""
Long-Term Watchlist Agent using PydanticAI.

Analyzes stocks from the 4-year investment watchlist against entry zones.
"""

from datetime import date

from pydantic import BaseModel
from pydantic_ai import Agent

from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout


def classify_longterm_status(price: float, entry_zone: float) -> tuple[float, str]:
    """Deterministic gap_pct and status from price vs entry zone.

    Returns:
        (gap_pct, status) where status is BUY ZONE/NEAR ENTRY/WATCH/WAIT.
    """
    if not entry_zone or entry_zone <= 0:
        return (0.0, "WAIT")
    gap_pct = round(((price - entry_zone) / entry_zone) * 100, 1)
    if gap_pct <= 0:
        status = "BUY ZONE"
    elif gap_pct <= 5:
        status = "NEAR ENTRY"
    elif gap_pct <= 15:
        status = "WATCH"
    else:
        status = "WAIT"
    return (gap_pct, status)


class LongtermStock(BaseModel):
    """Analysis for a single long-term stock."""

    ticker: str
    status: str  # BUY ZONE, NEAR ENTRY, WATCH, WAIT (pre-computed)
    price: float
    entry_zone: float
    gap_pct: float  # pre-computed
    rsi: str
    conviction: str
    sector: str = "unknown"
    action: str  # Specific recommendation


class LongtermAnalysisResult(BaseModel):
    """Result from long-term watchlist analysis."""

    stocks: list[LongtermStock]
    actionable: list[str]  # Tickers that are in BUY ZONE or NEAR ENTRY
    summary: str


async def create_longterm_agent(
    scan_date: date | None = None,
) -> tuple[Agent[AgentDeps, LongtermAnalysisResult], AgentConfig]:
    """Create a long-term analysis agent with tools."""
    if scan_date is None:
        scan_date = date.today()
    config = await load_agent_config("longterm")
    # HOOK-ALLOW: no-tickers-scope (longterm agent ranges over the full watchlist)
    agent = create_agent(config, output_type=LongtermAnalysisResult)
    return agent, config


async def analyze_longterm_with_agent(
    scan_date: date | None = None,
    geopolitical_context: str = "",
    regime_context: str = "",
    vn_economy_context: str = "",
) -> str:
    """Analyze long-term watchlist using the agentic approach.

    Args:
        scan_date: Date for data lookup (defaults to today)

    Returns:
        Formatted analysis string
    """
    agent, config = await create_longterm_agent(scan_date)
    deps_scan_date = scan_date if scan_date is not None else date.today()

    prompt = """Analyze the long-term investment watchlist.

Steps:
1. Get all watchlist stocks with entry zones
2. For each stock, call technical.get_technicals(ticker, entry_zone=<entry_zone_vnd>)
   - gap_pct and status are PRE-COMPUTED in the response — use them directly
   - Do NOT recalculate gap_pct or status yourself
3. For BUY ZONE/NEAR ENTRY stocks, read research for context
4. Generate recommendations sorted by conviction and gap from entry

Focus on identifying actionable opportunities (BUY ZONE or NEAR ENTRY with good RSI)."""

    if regime_context:
        prompt += f"\n\n{regime_context}"

    if geopolitical_context:
        prompt += f"\n\n{geopolitical_context}"

    if vn_economy_context:
        prompt += f"\n\n{vn_economy_context}"

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="longterm",
            deps=AgentDeps(scan_date=deps_scan_date, agent_key="longterm"),
            total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
            usage_limits=build_usage_limits(config),
        )

        # Format output
        lines = ["LONG-TERM OPPORTUNITIES"]
        lines.append("")

        for stock in result.output.stocks:
            gap_str = f"{stock.gap_pct:+.1f}%" if stock.gap_pct else "N/A"
            price_k = f"{stock.price / 1000:.1f}k" if stock.price else "N/A"
            entry_k = f"{stock.entry_zone / 1000:.0f}k" if stock.entry_zone else "N/A"
            lines.append(
                f"{stock.ticker}: {stock.status} | {price_k} vs {entry_k} ({gap_str}) | "
                f"RSI {stock.rsi} | {stock.conviction} | {stock.action}"
            )

        if result.output.actionable:
            lines.append("")
            lines.append(f"ACTIONABLE: {', '.join(result.output.actionable)}")

        lines.append("")
        lines.append(result.output.summary)

        return "\n".join(lines)

    except Exception as e:
        return f"Long-term analysis failed: {e}"
