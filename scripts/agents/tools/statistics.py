#!/usr/bin/env python3
"""
Statistical analysis tools for probability assessments.

Provides historical pattern statistics to enable quantitative recommendations.
Allows agents to make statements like "67% bounce rate when RSI<30 with hammer pattern".

All tools return a "prose" field with natural language summaries.
Agents should PREFER using the prose field for analysis.
"""

from typing import Literal

from shared.api.statistics import (
    get_consecutive_pattern_days as _get_consecutive_pattern_days_async,
)
from shared.api.statistics import (
    get_pattern_outcome_stats as _get_pattern_outcome_stats_async,
)
from shared.api.statistics import (
    get_price_action_analysis as _get_price_action_analysis_async,
)
from shared.api.statistics import (
    get_rsi_oversold_bounces as _get_rsi_oversold_bounces_async,
)
from shared.lint_markers import allow_single_ticker_fetcher

# ============================================================================
# Prose Formatters - Convert dict data to natural language strings
# ============================================================================


def _format_oversold_prose(data: dict, ticker: str | None = None, days_back: int = 90) -> str:
    """Convert oversold stats dict to natural prose."""
    if "error" in data:
        return f"RSI Oversold Stats: {data['error']}"

    bounce_rate = data.get("bounce_rate", 0)
    avg_change = data.get("avg_next_day_change", 0)
    max_consec = data.get("max_consecutive", 0)
    by_ticker = data.get("by_ticker", {})

    ticker_str = f" for {ticker}" if ticker else ""
    parts = [f"RSI Oversold Statistics{ticker_str} ({days_back} days):"]

    # Main stats
    bounce_pct = bounce_rate * 100
    parts.append(f"Bounce rate: {bounce_pct:.0f}% of RSI<30 occurrences bounced next day.")
    parts.append(f"Average next-day change: {avg_change:+.1f}%.")
    parts.append(f"Max consecutive oversold days: {max_consec}.")

    # Top tickers if available
    if by_ticker:
        sorted_tickers = sorted(by_ticker.items(), key=lambda x: x[1], reverse=True)[:3]
        ticker_strs = [f"{t} ({r * 100:.0f}%)" for t, r in sorted_tickers]
        parts.append(f"Best bounce rate by ticker: {', '.join(ticker_strs)}.")

    return " ".join(parts)


def _format_pattern_prose(
    data: dict, pattern: str, rsi_min: float, rsi_max: float, days_back: int
) -> str:
    """Convert pattern stats dict to natural prose."""
    if "error" in data:
        return f"Pattern Stats: {data['error']}"

    win_rate = data.get("win_rate", 0)
    avg_move = data.get("avg_move", 0)
    best_zone = data.get("best_rsi_zone", "N/A")
    sample = data.get("sample_size", 0)

    rsi_range = f"RSI {rsi_min:.0f}-{rsi_max:.0f}" if rsi_min > 0 or rsi_max < 100 else "all RSI"
    parts = [f"{pattern.title()} Pattern Statistics ({rsi_range}, {days_back} days):"]

    win_pct = win_rate * 100
    parts.append(f"Win rate: {win_pct:.0f}% (next day green).")
    parts.append(f"Average move: {avg_move:+.1f}%.")

    if best_zone and best_zone != "N/A":
        parts.append(f"Best RSI zone: {best_zone}.")

    parts.append(f"Sample size: {sample} occurrences.")

    return " ".join(parts)


def _format_price_action_prose(data: dict, days_back: int) -> str:
    """Convert price action stats dict to natural prose. SWI-125: by_rsi_zone and with_high_volume are nested {count, reversal_rate} dicts."""
    if "error" in data:
        return f"Price Action Stats: {data['error']}"

    reversal_rate: float = data.get("reversal_rate") or 0.0
    high_vol: dict[str, float] = data.get("with_high_volume") or {}
    by_rsi: dict[str, dict[str, float]] = data.get("by_rsi_zone") or {}

    parts = [f"Price Action Statistics ({days_back} days):"]

    parts.append(f"Close-at-low reversal rate: {reversal_rate * 100:.0f}%.")

    high_vol_rate = float(high_vol.get("reversal_rate") or 0.0)
    if high_vol_rate:
        parts.append(f"With high volume: {high_vol_rate * 100:.0f}% reversal rate.")

    if by_rsi:
        rsi_parts = [
            f"{zone} = {float(payload.get('reversal_rate') or 0.0) * 100:.0f}% reversal"
            for zone, payload in by_rsi.items()
        ]
        parts.append(f"By RSI zone: {', '.join(rsi_parts)}.")

    return " ".join(parts)


def _format_streak_prose(data: dict, ticker: str, condition: str, days_back: int) -> str:
    """Convert streak stats dict to natural prose. SWI-125: distribution is dict[int, int]; render as relative frequency."""
    if "error" in data:
        return f"Streak Stats: {data['error']}"

    max_consec = int(data.get("max_consecutive") or 0)
    avg_consec = float(data.get("avg_consecutive") or 0.0)
    current = int(data.get("current_streak") or 0)
    dist: dict[int, int] = data.get("distribution") or {}

    cond_name = condition.replace("_", " ").title()
    parts = [f"{ticker} {cond_name} Streak Statistics ({days_back} days):"]

    parts.append(f"Max consecutive days: {max_consec}.")
    parts.append(f"Average streak length: {avg_consec:.1f} days.")
    parts.append(f"Current streak: {current} days.")

    if dist:
        total = sum(dist.values()) or 1
        dist_parts = [
            f"{length} day{'s' if length != 1 else ''} ({(count / total) * 100:.0f}%)"
            for length, count in sorted(dist.items())
        ]
        parts.append(f"Distribution: {', '.join(dist_parts)}.")

    return " ".join(parts)


# ============================================================================
# Async Functions for PydanticAI Agents
# ============================================================================


@allow_single_ticker_fetcher  # historical-pattern aggregate over one ticker; batch semantic not meaningful
async def get_oversold_stats_async(
    ticker: str | None = None,
    rsi_threshold: float = 30.0,
    days_back: int = 90,
) -> dict:
    """Get RSI oversold statistics for probability assessment.

    Use this to answer questions like "What % of time does RSI < 30 bounce next day?"

    Args:
        ticker: Optional filter by specific ticker
        rsi_threshold: RSI level to consider oversold (default 30)
        days_back: Historical lookback period (default 90)

    Returns:
        Dict with bounce_rate, avg_next_day_change, max_consecutive, and prose summary.
        Use result["prose"] for natural language description.
    """
    try:
        result = await _get_rsi_oversold_bounces_async(ticker, rsi_threshold, days_back)
        result["prose"] = _format_oversold_prose(result, ticker, days_back)
        return result
    except Exception as e:
        error_result = {"error": f"Failed to fetch oversold stats: {e}"}
        error_result["prose"] = f"RSI Oversold Stats: Failed to fetch - {e}"
        return error_result


async def get_pattern_stats_async(
    pattern: str,
    rsi_min: float = 0,
    rsi_max: float = 100,
    days_back: int = 90,
) -> dict:
    """Get candlestick pattern outcome statistics.

    Use this to answer questions like "What's the win rate for hammer patterns at RSI<35?"

    Args:
        pattern: Pattern name (hammer, doji, bullish_engulfing, bearish_engulfing)
        rsi_min: Minimum RSI for filtering
        rsi_max: Maximum RSI for filtering
        days_back: Historical lookback period

    Returns:
        Dict with win_rate, avg_move, best_rsi_zone, and prose summary.
        Use result["prose"] for natural language description.
    """
    try:
        result = await _get_pattern_outcome_stats_async(pattern, rsi_min, rsi_max, days_back)
        result["prose"] = _format_pattern_prose(result, pattern, rsi_min, rsi_max, days_back)
        return result
    except Exception as e:
        error_result = {"error": f"Failed to fetch pattern stats: {e}"}
        error_result["prose"] = f"Pattern Stats: Failed to fetch - {e}"
        return error_result


async def get_price_action_stats_async(days_back: int = 30) -> dict:
    """Get closed-at-low and reversal statistics.

    Use this to answer questions like "How often do stocks that close at the low reverse?"

    Args:
        days_back: Historical lookback period

    Returns:
        Dict with reversal_rate, with_high_volume stats, by_rsi_zone breakdown, and prose summary.
        Use result["prose"] for natural language description.
    """
    try:
        result = await _get_price_action_analysis_async(days_back=days_back)
        result["prose"] = _format_price_action_prose(result, days_back)
        return result
    except Exception as e:
        error_result = {"error": f"Failed to fetch price action stats: {e}"}
        error_result["prose"] = f"Price Action Stats: Failed to fetch - {e}"
        return error_result


@allow_single_ticker_fetcher  # streak windows are per-ticker time series; batch semantic not meaningful
async def get_streak_stats_async(
    ticker: str,
    condition: str,
    days_back: int = 90,
) -> dict:
    """Get consecutive pattern/condition statistics.

    Use this to answer questions like "How many consecutive days can RSI stay below 20?"

    Args:
        ticker: Stock ticker
        condition: Condition to track (rsi_below_30, rsi_below_20, closed_at_low)
        days_back: Historical lookback period

    Returns:
        Dict with max_consecutive, avg_consecutive, distribution, current_streak, and prose summary.
        Use result["prose"] for natural language description.
    """
    try:
        result = await _get_consecutive_pattern_days_async(ticker, condition, days_back)
        result["prose"] = _format_streak_prose(result, ticker, condition, days_back)
        return result
    except Exception as e:
        error_result = {"error": f"Failed to fetch streak stats: {e}"}
        error_result["prose"] = f"Streak Stats: Failed to fetch - {e}"
        return error_result


# ============================================================================
# Agent Tool Functions - Return string for LLM agents
# ============================================================================


async def tool_get_oversold_stats(
    ticker: str | None = None,
    rsi_threshold: float = 30.0,
    days_back: int = 90,
) -> str:
    """Get RSI oversold bounce statistics.

    Args:
        ticker: Optional filter by specific ticker
        rsi_threshold: RSI level to consider oversold (default 30)
        days_back: Historical lookback period (default 90)

    For use by LLM agents. Returns natural prose string.
    """
    result = await get_oversold_stats_async(ticker, rsi_threshold, days_back)
    return result.get("prose", str(result))


async def tool_get_pattern_stats(
    pattern: str,
    rsi_min: float = 0,
    rsi_max: float = 100,
    days_back: int = 90,
) -> str:
    """Get candlestick pattern outcome statistics.

    Args:
        pattern: Pattern name (hammer, doji, bullish_engulfing, bearish_engulfing)
        rsi_min: Minimum RSI for filtering
        rsi_max: Maximum RSI for filtering
        days_back: Historical lookback period

    For use by LLM agents. Returns natural prose string.
    """
    result = await get_pattern_stats_async(pattern, rsi_min, rsi_max, days_back)
    return result.get("prose", str(result))


async def tool_get_price_action(days_back: int = 30) -> str:
    """Get close-at-low reversal statistics.

    Args:
        days_back: Historical lookback period

    For use by LLM agents. Returns natural prose string.
    """
    result = await get_price_action_stats_async(days_back)
    return result.get("prose", str(result))


async def tool_get_streak_stats(
    ticker: str,
    condition: str,
    days_back: int = 90,
) -> str:
    """Get consecutive pattern/condition statistics.

    Args:
        ticker: Stock ticker
        condition: Condition to track (rsi_below_30, rsi_below_20, closed_at_low)
        days_back: Historical lookback period

    For use by LLM agents. Returns natural prose string.
    """
    result = await get_streak_stats_async(ticker, condition, days_back)
    return result.get("prose", str(result))


async def tool_get_strategy_performance() -> str:
    """Get strategy win rates by market regime and rolling performance metrics.

    Shows which entry strategies (bounce, breakout, etc.) work best in each regime,
    plus 7d/30d/90d rolling win rates.
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        from shared.neon import get_rolling_performance, get_strategy_regime_stats

        regime_stats = await get_strategy_regime_stats()
        rolling = await get_rolling_performance()

        parts = ["Strategy Performance:"]

        if regime_stats:
            parts.append("  By Strategy x Regime:")
            for row in regime_stats[:8]:
                strategy = row.get("strategy") or "?"
                regime = row.get("regime") or "?"
                total = row.get("total_trades") or 0
                win_rate = row.get("win_rate_pct") or 0
                avg_pnl = row.get("avg_pnl_pct")
                pnl_str = f", avg {float(avg_pnl):+.1f}%" if avg_pnl is not None else ""
                parts.append(
                    f"    {strategy} in {regime}: {float(win_rate):.0f}% win ({total} trades{pnl_str})"
                )
        else:
            parts.append("  No strategy x regime data available (need more trades).")

        if rolling:
            parts.append("  Rolling Performance:")
            for window in ["7d", "30d", "90d"]:
                win_rate_key = f"win_rate_{window}"
                trades_key = f"trades_{window}"
                win_rate = rolling.get(win_rate_key)
                trades = rolling.get(trades_key)
                if win_rate is not None:
                    parts.append(
                        f"    {window}: {float(win_rate):.0f}% win rate ({trades or 0} trades)"
                    )

        return "\n".join(parts)
    except Exception as e:
        logger.warning("tool_get_strategy_performance failed: %s", e)
        return f"Strategy performance unavailable: {e}"


# ============================================================================
# Query Type Definitions
# ============================================================================

StatQueryType = Literal[
    "oversold_bounce",
    "pattern_outcome",
    "price_action",
    "consecutive_streak",
]
