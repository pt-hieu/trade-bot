#!/usr/bin/env python3
"""
Market Regime Agent using PydanticAI.

Classifies market conditions as RISK_ON, RISK_OFF, or NEUTRAL.
"""

import logging
from datetime import date
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pipeline.types import FlatTechnicalsRow

from pydantic import BaseModel
from pydantic_ai import Agent

from shared.agent_config import load_agent_config

logger = logging.getLogger(__name__)

from .agent_factory import AgentDeps, create_agent


class MarketRegimeResult(BaseModel):
    """Market regime classification result."""

    regime: Literal["RISK_ON", "RISK_OFF", "NEUTRAL"]
    regime_confidence: float  # 0.0 to 1.0
    key_signal: str  # Main technical signal driving the classification
    recommendation: str  # Trading stance recommendation


async def create_market_agent(
    scan_date: date | None = None,
) -> Agent[AgentDeps, MarketRegimeResult]:
    """Create a market regime agent with tools."""
    if scan_date is None:
        scan_date = date.today()
    config = await load_agent_config("market_level")
    # HOOK-ALLOW: no-tickers-scope (market_level emits global regime, not ticker-scoped)
    return create_agent(config, output_type=MarketRegimeResult)


async def classify_regime_with_agent(
    scan_date: date | None = None,
    vnindex_technicals: "FlatTechnicalsRow | dict | None" = None,
    rotation_context: str = "",
    learnings_context: str = "",
) -> dict:
    """Classify market regime using the agentic approach.

    Args:
        scan_date: Date for data lookup (defaults to today)
        vnindex_technicals: Pre-fetched VN-Index technicals (injected as context)
        rotation_context: Pre-fetched sector rotation data (injected)
        learnings_context: Pre-fetched macro_patterns learnings (injected)

    Returns:
        Dict with regime, regime_confidence, key_signal, recommendation
    """
    agent = await create_market_agent(scan_date)

    vnindex_context = _format_vnindex_context(vnindex_technicals)

    injected_blocks = vnindex_context
    if rotation_context:
        injected_blocks += f"\n\n{rotation_context}"
    if learnings_context:
        injected_blocks += f"\n\n{learnings_context}"

    prompt = f"""{injected_blocks}

Analyze current market conditions and classify the regime.

Steps:
1. Review VN-Index technicals above (pre-loaded)
2. Review sector rotation data above (pre-loaded)
3. Review macro calibration history above (pre-loaded)
4. Optionally search for macro news if signals are unclear
5. Classify as RISK_ON, RISK_OFF, or NEUTRAL with confidence level

Be decisive - pick a clear regime even if signals are mixed. Use confidence to express uncertainty."""

    try:
        # HOOK-ALLOW: unguarded-agent-run reason=pre-existing call, outside this type-annotation commit's scope
        result = await agent.run(
            prompt,
            deps=AgentDeps(
                scan_date=scan_date if scan_date is not None else date.today(),
                agent_key="market_level",
            ),
        )
        return {
            "regime": result.output.regime,
            "regime_confidence": result.output.regime_confidence,
            "key_signal": result.output.key_signal,
            "recommendation": result.output.recommendation,
        }
    except Exception as e:
        logger.warning(f"market_level regime detection failed: {e}")
        return {
            "regime": "NEUTRAL",
            "regime_confidence": 0.3,
            "key_signal": f"Error: {e}",
            "recommendation": "Wait for clarity - regime detection failed",
        }


def _format_vnindex_context(technicals: "FlatTechnicalsRow | dict | None") -> str:
    """Format VN-Index technicals as compact context block for injection."""
    if not technicals or "error" in technicals:
        return "## VN-INDEX TECHNICALS: UNAVAILABLE\nNo VN-Index data available — apply INSUFFICIENT DATA RULE."

    close = technicals.get("close")
    rsi = technicals.get("rsi")
    ma20 = technicals.get("ma20") or technicals.get("sma20")
    ma50 = technicals.get("ma50") or technicals.get("sma50")

    lines = ["## VN-INDEX TECHNICALS (pre-loaded)"]

    parts = []
    if close is not None:
        parts.append(f"Close: {close:,.1f}" if isinstance(close, float) else f"Close: {close:,}")
    if rsi is not None:
        parts.append(f"RSI: {rsi:.1f}")
    if ma20 is not None:
        parts.append(f"MA20: {ma20:,.1f}")
    if ma50 is not None:
        parts.append(f"MA50: {ma50:,.1f}")
    if parts:
        lines.append(" | ".join(parts))

    if close and (ma20 or ma50):
        position_parts = []
        if ma20:
            pct_vs_ma20 = (close - ma20) / ma20 * 100
            position_parts.append(f"vs MA20: {pct_vs_ma20:+.1f}%")
        if ma50:
            pct_vs_ma50 = (close - ma50) / ma50 * 100
            position_parts.append(f"vs MA50: {pct_vs_ma50:+.1f}%")
        lines.append(" | ".join(position_parts))

    trend = technicals.get("trend")
    pattern = technicals.get("pattern")
    analysis = technicals.get("analysis")
    if trend:
        lines.append(f"Trend: {trend}")
    if pattern:
        lines.append(f"Pattern: {pattern}")
    if analysis:
        lines.append(f"Analysis: {analysis}")

    levels = technicals.get("levels") or {}
    support = levels.get("nearest_support") or levels.get("range_20d_low")
    resistance = levels.get("nearest_resistance") or levels.get("range_20d_high")
    if support is not None or resistance is not None:
        level_parts = []
        if support is not None:
            level_parts.append(f"Support: {support:,.0f}")
        if resistance is not None:
            level_parts.append(f"Resistance: {resistance:,.0f}")
        lines.append(" | ".join(level_parts))

    return "\n".join(lines)
