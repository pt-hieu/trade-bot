"""Deterministic foreign flow streak classification.

Counts consecutive buy/sell days and classifies trend strength.
No LLM — pure Python arithmetic per CLAUDE.md rule.
"""


def classify_flow_streak(flow_history: list[dict]) -> dict:
    """Classify foreign flow streak from daily history.

    Args:
        flow_history: List of {date, net, signal?, pattern?} ordered newest-first.

    Returns:
        {streak_days, direction, trend, total_net, history}
    """
    if not flow_history:
        return {
            "streak_days": 0,
            "direction": "NEUTRAL",
            "trend": "INSUFFICIENT_DATA",
            "total_net": 0.0,
            "history": [],
        }

    consecutive_buy = 0
    consecutive_sell = 0
    total_net = 0.0

    for entry in flow_history:
        net = entry.get("net", 0)
        total_net += net

        if net > 0:
            if consecutive_sell > 0:
                break  # streak broken
            consecutive_buy += 1
        elif net < 0:
            if consecutive_buy > 0:
                break  # streak broken
            consecutive_sell += 1
        else:
            break  # zero = streak broken

    streak_days = max(consecutive_buy, consecutive_sell)
    if consecutive_buy > consecutive_sell:
        direction = "BUY"
    elif consecutive_sell > 0:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    if streak_days >= 5:
        trend = f"STRONG_{direction}"
    elif streak_days >= 3:
        trend = f"BUILDING_{direction}"
    else:
        trend = "NO_STREAK"

    return {
        "streak_days": streak_days,
        "direction": direction,
        "trend": trend,
        "total_net": round(total_net, 2),
        "history": flow_history,
    }
