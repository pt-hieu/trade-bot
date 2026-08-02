"""
Alert condition evaluation — extracted from alert_monitor for testability.

Handles both single-condition and compound (ALL/ANY) alert evaluation.
"""

import html
import logging

from shared.rules.exit_strategy import exit_state_from_rec, resolve_exit_strategy

logger = logging.getLogger(__name__)

VALID_CONDITION_TYPES = frozenset(
    {"price_below", "price_above", "rsi_below", "rsi_above", "volume_spike"}
)


def evaluate_single_condition(
    cond_type: str,
    cond_value: float | None,
    price_data: dict,
    tech_data: dict,
) -> tuple[bool, float | None]:
    """Evaluate one condition against live price/technical data.

    Args:
        cond_type: One of VALID_CONDITION_TYPES
        cond_value: Threshold value (None = skip)
        price_data: {open, high, low, close, volume}
        tech_data: {rsi, volume_sma20, ...}

    Returns:
        (triggered, actual_value) — actual_value is None if not triggered.
    """
    if cond_value is None:
        return False, None
    threshold = float(cond_value)

    if cond_type == "price_below":
        low = price_data.get("low")
        if low is not None and low <= threshold:
            return True, float(low)

    elif cond_type == "price_above":
        high = price_data.get("high")
        if high is not None and high >= threshold:
            return True, float(high)

    elif cond_type == "rsi_below":
        rsi = tech_data.get("rsi")
        if rsi is not None and float(rsi) <= threshold:
            return True, float(rsi)

    elif cond_type == "rsi_above":
        rsi = tech_data.get("rsi")
        if rsi is not None and float(rsi) >= threshold:
            return True, float(rsi)

    elif cond_type == "volume_spike":
        vol = price_data.get("volume")
        vol_sma = tech_data.get("volume_sma20")
        if vol and vol_sma and float(vol_sma) > 0:
            ratio = float(vol) / float(vol_sma)
            if ratio >= threshold:
                return True, round(ratio, 3)

    return False, None


def evaluate_alert(
    alert: dict,
    prices: dict[str, dict],
    technicals: dict[str, dict],
) -> tuple[bool, dict]:
    """Evaluate compound alert using ALL/ANY logic.

    Returns:
        (triggered, triggered_values) where triggered_values maps
        condition_type → actual value at trigger time.
        On no trigger, returns (False, {}).
    """
    ticker = alert["ticker"]
    price_data = prices.get(ticker, {})
    tech_data = technicals.get(ticker, {})
    conditions = alert.get("conditions", [])
    logic = alert.get("condition_logic", "ALL")

    if not conditions:
        return False, {}

    results: list[bool] = []
    values: dict[str, float] = {}

    for cond in conditions:
        ctype = cond.get("condition_type", "")
        cval = cond.get("condition_value")
        hit, actual = evaluate_single_condition(ctype, cval, price_data, tech_data)
        results.append(hit)
        if hit and actual is not None:
            values[ctype] = actual

    triggered = any(results) if logic == "ANY" else all(results)
    return triggered, (values if triggered else {})


def format_alert_message(alert: dict, triggered_values: dict) -> str:
    """Format Telegram HTML notification for a triggered alert."""
    ticker = alert["ticker"]
    action = alert.get("recommended_action", "WATCH")
    priority_emoji = {"high": "🔴", "normal": "🟡", "low": "⚪"}.get(
        alert.get("priority", "normal"), "🟡"
    )
    conditions = alert.get("conditions", [])
    logic = alert.get("condition_logic", "ALL")

    lines = [f"{priority_emoji} <b>ALERT: {ticker} — {action}</b>"]

    if len(conditions) == 1:
        cond = conditions[0]
        ctype = cond.get("condition_type", "")
        cval = cond.get("condition_value", "")
        actual = triggered_values.get(ctype, "—")
        lines.append(f"Condition: {ctype.replace('_', ' ')} {cval} → {actual}")
    elif conditions:
        logic_word = "ALL of" if logic == "ALL" else "ANY of"
        lines.append(f"Conditions ({logic_word}):")
        for cond in conditions:
            ctype = cond.get("condition_type", "")
            cval = cond.get("condition_value", "")
            actual = triggered_values.get(ctype)
            hit_marker = "✓" if actual is not None else "·"
            lines.append(
                f"  {hit_marker} {ctype.replace('_', ' ')} {cval}"
                + (f" → {actual}" if actual is not None else "")
            )

    if alert.get("rationale"):
        # LLM-authored free text into a parse_mode="HTML" message — escape it.
        lines.append(f"Reason: {html.escape(str(alert['rationale']))}")

    if alert.get("entry_price"):
        lines.append(f"Entry: {alert['entry_price']:,.0f}")
    if alert.get("stop_price"):
        lines.append(f"Stop: {alert['stop_price']:,.0f}")

    strategy = alert.get("strategy")
    if strategy:
        try:
            exit_line = resolve_exit_strategy(strategy).exit_description(exit_state_from_rec(alert))
        except Exception as error:
            logger.warning(
                "exit_description failed for %s (strategy=%s): %s",
                ticker,
                strategy,
                error,
            )
            exit_line = None
        if exit_line:
            lines.append(f"Exit: {exit_line}")
        elif alert.get("target_price"):
            lines.append(f"Target: {alert['target_price']:,.0f}")
    elif alert.get("target_price"):
        lines.append(f"Target: {alert['target_price']:,.0f}")

    lines.append(f"\nSource: {alert['source']} ({alert['source_date']})")
    return "\n".join(lines)
