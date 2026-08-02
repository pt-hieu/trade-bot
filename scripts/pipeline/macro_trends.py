"""Deterministic macro trend computation from historical data.

Computes 5-day indicator trends, regime transitions, and cross-asset
narrative patterns. All calculations are pure Python — no LLM involvement.
"""

import logging
import math

from shared.neon import MacroHistoryEntry, RegimeHistoryEntry

logger = logging.getLogger(__name__)

# Indicators tracked from macro_metrics history
INDICATOR_KEYS = [
    "vix_value",
    "dxy_value",
    "oil_price",
    "copper_price",
    "us_10y_yield",
    "shanghai_close",
    "usd_vnd_rate",
]

# Display labels and arrow symbols
INDICATOR_LABELS = {
    "vix_value": "VIX",
    "dxy_value": "DXY",
    "oil_price": "Oil",
    "copper_price": "Cu",
    "us_10y_yield": "10Y",
    "shanghai_close": "SSEC",
    "usd_vnd_rate": "USD/VND",
}

DIRECTION_ARROWS = {"UP": "\u2191", "DOWN": "\u2193", "FLAT": "\u2192"}

# Threshold for UP/DOWN classification (0.5%)
DIRECTION_THRESHOLD = 0.005


def compute_indicator_trends(macro_history: list[MacroHistoryEntry]) -> dict[str, dict]:
    """Compute 5-day directional trends for each macro indicator.

    Args:
        macro_history: Rows from get_macro_history(), newest first.

    Returns:
        Dict keyed by short indicator name (e.g. "vix"), each containing
        direction, latest, oldest, and formatted string.
    """
    if not macro_history or len(macro_history) < 2:
        return {}

    newest_row = macro_history[0]
    oldest_row = macro_history[-1]
    trends: dict[str, dict] = {}

    for indicator_key in INDICATOR_KEYS:
        latest_value = newest_row.get(indicator_key)
        oldest_value = oldest_row.get(indicator_key)

        if (
            latest_value is None
            or oldest_value is None
            or (
                isinstance(latest_value, float)
                and (math.isnan(latest_value) or math.isinf(latest_value))
            )
            or (
                isinstance(oldest_value, float)
                and (math.isnan(oldest_value) or math.isinf(oldest_value))
            )
        ):
            logger.debug(
                "Skipping %s: missing/NaN data (latest=%s, oldest=%s)",
                indicator_key,
                latest_value,
                oldest_value,
            )
            continue

        if oldest_value == 0:
            logger.debug("Skipping %s: oldest value is zero", indicator_key)
            continue

        # Direction logic: >0.5% change = UP/DOWN, else FLAT
        if latest_value > oldest_value * (1 + DIRECTION_THRESHOLD):
            direction = "UP"
        elif latest_value < oldest_value * (1 - DIRECTION_THRESHOLD):
            direction = "DOWN"
        else:
            direction = "FLAT"

        label = INDICATOR_LABELS[indicator_key]
        arrow = DIRECTION_ARROWS[direction]
        short_name = indicator_key.replace("_value", "").replace("_price", "").replace("_close", "")

        # Format value for display
        formatted_value = _format_indicator_value(indicator_key, latest_value)
        formatted_oldest = _format_indicator_value(indicator_key, oldest_value)

        if direction == "FLAT":
            formatted_string = f"{label}: {formatted_value} ({arrow})"
        else:
            formatted_string = f"{label}: {formatted_value} ({arrow} from {formatted_oldest}, 5d)"

        trends[short_name] = {
            "direction": direction,
            "latest": latest_value,
            "oldest": oldest_value,
            "formatted": formatted_string,
        }

    return trends


def _format_indicator_value(indicator_key: str, value: float) -> str:
    """Format a single indicator value for display."""
    if indicator_key == "usd_vnd_rate":
        return f"{value:,.0f}"
    if indicator_key in ("oil_price", "copper_price"):
        return f"${value:.1f}"
    if indicator_key == "us_10y_yield":
        return f"{value:.2f}%"
    if indicator_key == "shanghai_close":
        return f"{value:,.0f}"
    # vix, dxy — plain number
    return f"{value:.1f}"


def compute_regime_transition(regime_history: list[RegimeHistoryEntry]) -> str | None:
    """Detect regime change within last 3 entries.

    Args:
        regime_history: Rows from get_regime_history(), newest first.

    Returns:
        Transition description string, or None if no change detected.
    """
    if not regime_history or len(regime_history) < 2:
        return None

    current_regime = regime_history[0].get("regime")
    if not current_regime:
        logger.warning("compute_regime_transition: newest entry has no regime")
        return None

    # Check last 3 entries for a change
    check_window = regime_history[:3]
    for entry_index, entry in enumerate(check_window[1:], start=1):
        previous_regime = entry.get("regime")
        if previous_regime and previous_regime != current_regime:
            days_ago = entry_index
            # Determine direction
            escalation_order = ["CALM", "NEUTRAL", "CAUTIOUS", "ELEVATED", "RISK_OFF"]
            current_rank = _regime_rank(current_regime, escalation_order)
            previous_rank = _regime_rank(previous_regime, escalation_order)

            if current_rank > previous_rank:
                direction_label = "escalating"
            elif current_rank < previous_rank:
                direction_label = "de-escalating"
            else:
                direction_label = "changed"

            return (
                f"Regime: {current_regime} (was {previous_regime} "
                f"{days_ago}d ago \u2014 {direction_label})"
            )

    return None


def _regime_rank(regime: str, order: list[str]) -> int:
    """Return numeric rank for regime comparison. Unknown regimes get middle rank."""
    try:
        return order.index(regime)
    except ValueError:
        return len(order) // 2


def detect_cross_asset_narratives(
    trends: dict[str, dict],
    commodity_prices: dict | None = None,
    market_valuation: dict | None = None,
) -> list[str]:
    """Deterministic pattern matching for cross-asset narratives.

    Returns list of matched narrative labels. Skips rules that depend
    on data we don't have.
    """
    if not trends:
        return []

    narratives: list[str] = []

    def direction_is(indicator_short_name: str, expected_direction: str) -> bool:
        indicator_trend = trends.get(indicator_short_name)
        if not indicator_trend:
            return False
        return indicator_trend["direction"] == expected_direction

    # Pattern 1: Fed hawkish / EM pressure
    if (
        direction_is("dxy", "UP")
        and direction_is("us_10y_yield", "UP")
        and direction_is("copper", "DOWN")
    ):
        narratives.append("Fed hawkish / EM pressure")

    # Pattern 2: Geopolitical risk escalation
    if direction_is("oil", "UP") and direction_is("vix", "UP"):
        narratives.append("Geopolitical risk escalation")

    # Pattern 3: China slowdown / EM drag
    if direction_is("shanghai", "DOWN") and direction_is("copper", "DOWN"):
        narratives.append("China slowdown / EM drag")

    # Pattern 4: Steel margin expansion (from commodity_prices, not trends)
    if commodity_prices:
        steel_hrc_data = commodity_prices.get("steel_hrc")
        iron_ore_data = commodity_prices.get("iron_ore")
        if steel_hrc_data and iron_ore_data:
            steel_change = steel_hrc_data.get("change_5d_pct") or 0
            iron_change = iron_ore_data.get("change_5d_pct") or 0
            if steel_change > 2 and iron_change < 1:
                narratives.append("Steel margin expansion")

    # Pattern 5: Input cost shock (from commodity_prices + trends)
    if commodity_prices and direction_is("oil", "UP"):
        gas_vn_data = commodity_prices.get("gas_vn")
        if gas_vn_data:
            gas_change = gas_vn_data.get("change_5d_pct") or 0
            if gas_change > 3:
                narratives.append("Input cost shock")

    # Pattern 6: Oversold + valuation floor
    if market_valuation:
        pe_percentile = market_valuation.get("pe_percentile")
        if pe_percentile is not None and pe_percentile < 15:
            narratives.append("Oversold + valuation floor")

    return narratives


def format_trend_block(
    trends: dict[str, dict],
    regime_transition: str | None,
    narratives: list[str],
) -> str:
    """Format trends into a compact block (~60 tokens).

    Returns empty string if no trends available.
    """
    if not trends:
        return ""

    # Pick key indicators for the summary line
    summary_indicators = ["vix", "dxy", "oil", "copper", "us_10y_yield", "shanghai", "usd_vnd_rate"]
    indicator_parts = []
    for indicator_name in summary_indicators:
        indicator_trend = trends.get(indicator_name)
        if indicator_trend:
            indicator_parts.append(indicator_trend["formatted"])

    lines = ["## TRENDS (5d)"]
    if indicator_parts:
        lines.append(" | ".join(indicator_parts))

    # Regime transition + narratives on one line
    context_parts = []
    if regime_transition:
        context_parts.append(regime_transition)
    if narratives:
        context_parts.append("Signal: " + ", ".join(narratives))
    if context_parts:
        lines.append(" | ".join(context_parts))

    return "\n".join(lines)
