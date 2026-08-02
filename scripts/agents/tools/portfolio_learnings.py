"""Learnings retrieval — selective queries against learning patterns and insights."""

from shared.neon import (
    get_learnings_summary as _get_learnings_summary_async,
)
from shared.neon import (
    get_losing_patterns as _get_losing_patterns_async,
)
from shared.neon import (
    get_macro_patterns as _get_macro_patterns_async,
)
from shared.neon import (
    get_midday_patterns as _get_midday_patterns_async,
)
from shared.neon import (
    get_mode_compliance as _get_mode_compliance_async,
)
from shared.neon import (
    get_rotation_patterns as _get_rotation_patterns_async,
)
from shared.neon import (
    get_sector_insights as _get_sector_insights_async,
)
from shared.neon import (
    get_ticker_insights as _get_ticker_insights_async,
)
from shared.neon import (
    get_winning_patterns as _get_winning_patterns_async,
)


def _normalize_bias(bias: str) -> str:
    """Normalize descriptive bias values to bullish/bearish/neutral."""
    bias_lower = bias.lower()
    if any(word in bias_lower for word in ["strong", "resilient", "bullish", "hot", "opportunity"]):
        return "bullish"
    elif any(word in bias_lower for word in ["weak", "bearish", "cold", "choppy", "downtrend"]):
        return "bearish"
    return "neutral"


def _get_sector_bias(insights: list, sector: str | None) -> dict:
    """Return sector insights grouped by bullish/bearish bias."""
    if sector:
        insights = [s for s in insights if sector.lower() in s.get("sector", "").lower()]

    hot = [s["sector"] for s in insights if _normalize_bias(s.get("bias", "")) == "bullish"]
    cold = [s["sector"] for s in insights if _normalize_bias(s.get("bias", "")) == "bearish"]

    return {"query": "sector_bias", "hot": hot, "cold": cold, "data": insights}


def _get_ticker_accuracy(insights: list, ticker: str | None) -> dict:
    """Return ticker accuracy grouped by high/low thresholds."""
    if ticker:
        insights = [t for t in insights if t.get("ticker", "").upper() == ticker.upper()]
    return {
        "query": "ticker_accuracy",
        "high": [t["ticker"] for t in insights if t.get("recent_accuracy", 0) >= 70],
        "low": [t["ticker"] for t in insights if t.get("recent_accuracy", 0) <= 30],
        "data": insights,
    }


async def get_learnings_async(
    query: str,
    sector: str | None = None,
    ticker: str | None = None,
    action: str | None = None,
    limit: int = 5,
) -> dict:
    """Get learnings from database with selective retrieval (async).

    Args:
        query: Query type - "summary", "winning_patterns", "losing_patterns",
               "sector_bias", "ticker_accuracy", etc.
        sector: Filter patterns/sectors by sector name
        ticker: Filter ticker accuracy by ticker symbol
        action: Filter patterns by action type (BUY, EXIT, SKIP, etc.)
        limit: Max patterns to return (default: 5)

    Returns:
        Dict with requested data only
    """
    try:
        if query == "summary":
            summary = await _get_learnings_summary_async()
            return {"query": "summary", "data": summary}
        elif query == "winning_patterns":
            patterns = await _get_winning_patterns_async(sector, action, limit)
            return {"query": "winning_patterns", "count": len(patterns), "data": patterns}
        elif query == "losing_patterns":
            patterns = await _get_losing_patterns_async(action, limit)
            return {"query": "losing_patterns", "count": len(patterns), "data": patterns}
        elif query == "sector_bias":
            insights = await _get_sector_insights_async(sector)
            return _get_sector_bias(insights, sector)
        elif query == "ticker_accuracy":
            insights = await _get_ticker_insights_async(ticker)
            return _get_ticker_accuracy(insights, ticker)
        elif query == "midday_insights":
            data = await _get_midday_patterns_async()
            return {"query": "midday_insights", "data": data}
        elif query == "mode_compliance":
            data = await _get_mode_compliance_async()
            return {"query": "mode_compliance", "data": data}
        elif query == "rotation_patterns":
            data = await _get_rotation_patterns_async(sector)
            return {"query": "rotation_patterns", "data": data}
        elif query == "macro_patterns":
            data = await _get_macro_patterns_async()
            return {"query": "macro_patterns", "data": data}
        elif query == "calibration":
            from shared.neon.learnings import get_calibration_insights

            data = await get_calibration_insights()
            return {"query": "calibration", "data": data}
        else:
            valid = "summary, winning_patterns, losing_patterns, sector_bias, ticker_accuracy, midday_insights, mode_compliance, rotation_patterns, macro_patterns, calibration"
            return {"error": f"Unknown query type: {query!r}. Valid types: {valid}"}
    except Exception as e:
        return {"error": f"Failed to query learnings: {e}"}
