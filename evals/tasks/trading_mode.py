"""
Trading mode eval task — mostly deterministic, LLM only for REALLOCATION.

The determine_mode() function is pure Python (no LLM).
This eval tests the full pipeline including LLM-based stagnant position identification.
"""

from pydantic import BaseModel
from pydantic_ai import Agent

# Re-use the production output type
from agents.trading_mode import TradingModeResult, determine_mode
from evals.helpers import get_eval_model, load_prompt


class TradingModeInput(BaseModel):
    """Input data for a trading_mode eval case."""

    deployable_cash: float
    position_alerts: list[dict] = []
    sector_rotation: dict = {}
    longterm_tickers: list[str] = []
    holdings: dict = {}


class TradingModeMetadata(BaseModel):
    """Metadata with expected values for grading."""

    mode: str  # NORMAL, LOW_CASH, REALLOCATION
    difficulty: str = "easy"
    note: str = ""


# Keep for backwards compat
TradingModeExpected = TradingModeMetadata


async def trading_mode_task(inputs: TradingModeInput) -> TradingModeResult:
    """Eval task — deterministic for NORMAL/LOW_CASH, LLM for REALLOCATION."""
    mode = determine_mode(inputs.deployable_cash)

    if mode == "NORMAL":
        return TradingModeResult(
            mode="NORMAL",
            reason=f"Deployable cash {inputs.deployable_cash:,.0f} VND is healthy",
            stagnant_positions=[],
            reallocation_targets=[],
        )

    if mode == "LOW_CASH":
        return TradingModeResult(
            mode="LOW_CASH",
            reason=f"Deployable cash {inputs.deployable_cash:,.0f} VND — only TRIM/EXIT",
            stagnant_positions=[],
            reallocation_targets=[],
        )

    # REALLOCATION — use LLM to identify stagnant positions
    prompt_text = await load_prompt("trading_mode")
    agent = Agent(
        get_eval_model("light"),
        system_prompt=prompt_text,
        output_type=TradingModeResult,
        output_retries=3,
    )

    @agent.tool_plain
    async def tool_get_technicals(ticker: str) -> dict:
        """Get technical data for a ticker."""
        return {"ticker": ticker, "trend": "SIDEWAYS", "rsi": 45.0, "note": "mock data"}

    @agent.tool_plain
    async def tool_get_holdings() -> dict:
        """Get portfolio holdings."""
        return inputs.holdings

    alerts_str = ""
    for alert in inputs.position_alerts:
        ticker = alert.get("ticker", "")
        action = alert.get("action", "")
        reason = alert.get("reason", "")
        alerts_str += f"- {ticker}: {action} - {reason}\n"

    hot = inputs.sector_rotation.get("hot", [])
    cold = inputs.sector_rotation.get("cold", [])

    prompt = f"""Mode is REALLOCATION (zero deployable cash). Identify:
1. Stagnant positions to EXIT (skip long-term holdings)
2. Better reallocation targets from hot sectors

## Position Alerts
{alerts_str or "No alerts"}

## Sector Rotation
- HOT: {", ".join(hot) if hot else "None"}
- COLD: {", ".join(cold) if cold else "None"}

## Long-Term Holdings (DO NOT flag as stagnant)
{", ".join(inputs.longterm_tickers) if inputs.longterm_tickers else "None"}"""

    result = await agent.run(prompt)
    return result.output
