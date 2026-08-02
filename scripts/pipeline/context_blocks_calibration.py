"""Context block formatters for inject-instead-of-tool data.

Pre-fetched data (belief accuracy, trades, learnings, memory patterns)
formatted as compact text blocks for injection into agent user prompts.

Token budgets documented per function. All headers include
"pre-loaded — analyze directly" to signal data is already available.
"""

from __future__ import annotations

import json

from shared.rules.calibration import CALIBRATION_STALENESS_DAYS, MIN_CALIBRATION_SAMPLE

# ── Header Constants ──────────────────────────────────────────────────────

CALIBRATION_HEADER = "## CALIBRATION DATA (pre-loaded — analyze directly)"
TRADES_HEADER = "## RECENT TRADES (pre-loaded — analyze directly)"
LEARNINGS_HEADER = "## LEARNINGS (pre-loaded — analyze directly)"
MEMORY_HEADER = "## HISTORICAL PATTERNS (pre-loaded — analyze directly)"
ROTATION_HEADER = "## SECTOR ROTATION DATA (pre-loaded — analyze directly)"
SECTOR_DATA_HEADER = "## SECTOR DATA (pre-loaded — analyze directly)"
EXECUTED_TRADES_HEADER = "## EXECUTED TRADES TODAY (pre-loaded — analyze directly)"
MIDDAY_PRICES_HEADER = "## MIDDAY PRICES (pre-loaded — analyze directly)"


# ── Helpers ───────────────────────────────────────────────────────────────


def _wrap_block(header: str, prose: str) -> str:
    """Wrap prose with a pre-loaded header. Returns empty string if no prose."""
    return f"{header}\n{prose}" if prose else ""


def build_calibration_blocks(
    enrichment_data: object | None,
    agent_keys: list[str],
) -> dict[str, str]:
    """Build per-agent calibration blocks from pre-fetched belief accuracy.

    Args:
        enrichment_data: EnrichmentData (or None). Reads .belief_accuracy dict.
        agent_keys: Agent keys to build blocks for.

    Returns:
        Dict mapping agent_key to formatted calibration block (empty string if unavailable).
    """
    belief_accuracy = (
        (enrichment_data.belief_accuracy if enrichment_data else {}) or {}  # type: ignore[union-attr]
    )
    return {key: format_calibration_block(belief_accuracy.get(key) or "") for key in agent_keys}


# ── Format Functions ──────────────────────────────────────────────────────


def format_calibration_block(accuracy_prose: str) -> str:
    """Format belief accuracy for injection into agent prompt."""
    return _wrap_block(CALIBRATION_HEADER, accuracy_prose)


def _format_calibration_staleness_banner(calibration_row: dict) -> str:
    """Positive-phrased staleness banner driven by calibration row only.

    Triggers when swing_sample_size < MIN_CALIBRATION_SAMPLE OR
    staleness_days > CALIBRATION_STALENESS_DAYS. Phrasing follows the
    abstinence rule: "proceed with normal entry sizing".
    """
    swing_sample_size = calibration_row.get("swing_sample_size")
    staleness_days = calibration_row.get("staleness_days")
    sample_low = swing_sample_size is not None and swing_sample_size < MIN_CALIBRATION_SAMPLE
    stale = (staleness_days or 0) > CALIBRATION_STALENESS_DAYS
    if not (sample_low or stale):
        return ""
    days_text = f"{staleness_days}" if staleness_days is not None else "many"
    return (
        f"  NOTE: Calibration data is stale ({days_text} days since last trade exit) — "
        "proceed with normal entry sizing; do not require larger samples before acting."
    )


def format_trades_block(trades_prose: str) -> str:
    """Format recent trades for injection."""
    return _wrap_block(TRADES_HEADER, trades_prose)


def format_learnings_block(learnings_cache: dict[str, dict], query_keys: list[str]) -> str:
    """Format pre-fetched learnings for specific query keys.

    Args:
        learnings_cache: Dict mapping query_key to learnings result dict.
        query_keys: Which query results to include in this block.
    """
    if not learnings_cache:
        return ""

    parts = [LEARNINGS_HEADER]
    for key in query_keys:
        data = learnings_cache.get(key)
        if not data or "error" in data:
            continue
        content = data.get("data")
        if content is None:
            continue
        # Format based on query type
        if key == "summary" and isinstance(content, dict):
            parts.append("\n### Trading Summary")
            for field_key, value in content.items():
                parts.append(f"  {field_key}: {value}")
        elif key == "calibration" and isinstance(content, dict):
            parts.append("\n### Calibration Insights")
            for field_key, value in content.items():
                parts.append(f"  {field_key}: {value}")
            staleness_banner = _format_calibration_staleness_banner(content)
            if staleness_banner:
                parts.append(staleness_banner)
        elif key == "sector_bias":
            # Use pre-computed hot/cold lists from _get_sector_bias()
            hot = data.get("hot") or []
            cold = data.get("cold") or []
            parts.append(
                f"\n### Sector Bias\n  Hot: {', '.join(hot) or 'none'}"
                f"\n  Cold: {', '.join(cold) or 'none'}"
            )
        elif key == "ticker_accuracy":
            # Use pre-computed high/low lists from _get_ticker_accuracy()
            high = data.get("high") or []
            low = data.get("low") or []
            parts.append(
                f"\n### Ticker Accuracy\n  High accuracy: {', '.join(high) or 'none'}"
                f"\n  Low accuracy: {', '.join(low) or 'none'}"
            )
        elif isinstance(content, list):
            parts.append(f"\n### {key.replace('_', ' ').title()}")
            for item in content[:5]:  # Cap at 5 items
                if isinstance(item, dict):
                    parts.append(f"  - {json.dumps(item, default=str)}")
                else:
                    parts.append(f"  - {item}")
        elif isinstance(content, dict):
            parts.append(f"\n### {key.replace('_', ' ').title()}")
            for field_key, value in content.items():
                parts.append(f"  {field_key}: {value}")

        # Accuracy gating: warn when overall_accuracy is below baseline.
        # Check the full response dict (`data`), not `content` (which is data["data"])
        # — overall_accuracy lives at the top level for macro/rotation patterns.
        if key not in ("sector_bias", "ticker_accuracy", "summary", "calibration"):
            response_data = data.get("data")
            if isinstance(response_data, dict) and "overall_accuracy" in response_data:
                accuracy = response_data.get("overall_accuracy")
                if accuracy is not None:
                    try:
                        accuracy_float = float(accuracy)
                        if accuracy_float < 0.50:
                            parts.append(
                                f"  WARNING: Historical accuracy {accuracy_float:.0%}"
                                " (below 50%). Treat as directional context only."
                            )
                    except (ValueError, TypeError):
                        pass

    return "\n".join(parts) if len(parts) > 1 else ""


def format_memory_block(
    similar_days: str,
    trading_rules: str,
    winning_patterns: str,
    losing_patterns: str,
) -> str:
    """Format Entry Strategist memory tools (pre-fetched with known params).

    Injects full data — memory tools already return compact results
    (3 similar days, 5 rules, 3 patterns).
    """
    parts = [MEMORY_HEADER]

    if similar_days:
        parts.append(f"\n### Similar Days\n{similar_days}")

    if trading_rules:
        parts.append(f"\n### Trading Rules\n{trading_rules}")

    if winning_patterns:
        parts.append(f"\n### Winning Patterns\n{winning_patterns}")

    if losing_patterns:
        parts.append(f"\n### Losing Patterns\n{losing_patterns}")

    return "\n".join(parts) if len(parts) > 1 else ""


def format_rotation_block(rotation_prose: str) -> str:
    """Format sector rotation data for injection."""
    return _wrap_block(ROTATION_HEADER, rotation_prose)


def format_sector_data_block(sector_data_prose: str) -> str:
    """Format sector RSI/price data for injection."""
    return _wrap_block(SECTOR_DATA_HEADER, sector_data_prose)


def format_executed_trades_block(executed_trades_prose: str) -> str:
    """Format today's executed trades for injection."""
    return _wrap_block(EXECUTED_TRADES_HEADER, executed_trades_prose)


def format_midday_prices_block(midday_prices: dict) -> str:
    """Format midday OHLCV prices for injection.

    Budget: ~300 tokens.
    """
    if not midday_prices:
        return ""
    lines = [MIDDAY_PRICES_HEADER]
    for ticker, data in sorted(midday_prices.items()):
        if isinstance(data, dict):
            open_price = data.get("open") or 0
            high = data.get("high") or 0
            low = data.get("low") or 0
            close = data.get("close") or 0
            volume = data.get("volume") or 0
            change_pct = data.get("change_pct") or 0
            lines.append(
                f"  {ticker} | O:{open_price:,.0f} H:{high:,.0f} L:{low:,.0f} "
                f"C:{close:,.0f} | Vol:{volume:,.0f} | Chg:{change_pct:+.1f}%"
            )
    return "\n".join(lines)
