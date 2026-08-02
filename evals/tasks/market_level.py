"""
Market level eval task — creates fresh agent with mocked tools per trial.

Tools return input data directly → no API needed.
Prompts loaded from YAML config files (scripts/agents/configs/).

Dataset typing: Dataset[MarketLevelInput, MarketRegimeResult, MarketLevelMetadata]
- expected_output: Not used (typed as MarketRegimeResult but we skip it)
- metadata: Contains expected regime + min_confidence for evaluator grading
"""

from pydantic import BaseModel
from pydantic_ai import Agent

# Re-use the production output type
from agents.market_level import MarketRegimeResult
from evals.helpers import get_eval_model, load_prompt


class MarketLevelInput(BaseModel):
    """Input data for a market_level eval case."""

    vnindex_technicals: dict
    sector_rotation: dict
    regime_history: list[dict] = []
    news_results: list[dict] = []


class MarketLevelMetadata(BaseModel):
    """Metadata for eval grading — contains expected values."""

    regime: str  # Expected: RISK_ON, RISK_OFF, NEUTRAL
    min_confidence: float = 0.4
    difficulty: str = "easy"
    type: str = "positive"
    note: str = ""


# Keep for backwards compat
MarketLevelExpected = MarketLevelMetadata


async def market_level_task(inputs: MarketLevelInput) -> MarketRegimeResult:
    """Eval task — creates fresh agent with mocked tools per trial.

    Each invocation is isolated: new agent, no shared state.
    """
    prompt_text = await load_prompt("market_level")
    agent = Agent(
        get_eval_model("critic"),
        system_prompt=prompt_text,
        output_type=MarketRegimeResult,
        output_retries=3,
    )

    # Mocked tools — return input data directly
    @agent.tool_plain
    async def tool_get_vnindex() -> dict:
        """Get VN-Index technicals: RSI, Stochastic, Bollinger, support/resistance."""
        return inputs.vnindex_technicals

    @agent.tool_plain
    async def tool_get_rotation() -> dict:
        """Get sector rotation data: hot sectors, cold sectors, rotation signal."""
        return inputs.sector_rotation

    @agent.tool_plain
    async def tool_get_history() -> list[dict]:
        """Get last 5 days of regime history for trend analysis."""
        return inputs.regime_history

    @agent.tool_plain
    async def tool_search_news(query: str) -> str:
        """Search for market news and catalysts."""
        articles = inputs.news_results or []
        return "\n".join(a.get("title", "") for a in articles[:3]) or "No articles."

    result = await agent.run("Analyze current market conditions and classify the regime.")
    return result.output
