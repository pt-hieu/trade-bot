"""Deterministic exit plan computation for swing trade picks."""


def compute_exit_plan(
    entry: float,
    stop: float,
    conservative_target: float | None,
    aggressive_target: float | None,
    range_20d_low: float | None,
) -> dict:
    """Compute staged exit plan for a swing trade.

    Leg 1: Take 50% at conservative target, move stop to breakeven.
    Leg 2: Runner to aggressive target with trailing stop at 20d low.
    Time stop: Exit if flat after 10 sessions.

    If no aggressive target, exit 100% at conservative.

    Args:
        entry: Entry price in VND.
        stop: Stop-loss price in VND.
        conservative_target: R1 / nearest resistance target.
        aggressive_target: Swing high / extended target (may be None).
        range_20d_low: 20-day low for trailing stop (may be None).

    Returns:
        Dict with legs list and time_stop string.
    """
    if not conservative_target:
        return {"legs": [], "time_stop": "Exit if flat after 10 sessions"}

    legs = []

    if aggressive_target and aggressive_target > conservative_target * 1.02:
        # Two-leg exit
        legs.append(
            {
                "leg": 1,
                "pct": 50,
                "target": conservative_target,
                "action": f"Take 50% at {conservative_target:,.0f}",
                "stop_adjust": f"Move stop to breakeven ({entry:,.0f})",
            }
        )
        trailing = range_20d_low if range_20d_low else stop
        legs.append(
            {
                "leg": 2,
                "pct": 50,
                "target": aggressive_target,
                "action": f"Runner to {aggressive_target:,.0f}",
                "trailing_stop": f"Trailing at 20d low ({trailing:,.0f})",
            }
        )
    else:
        # Single-leg exit
        legs.append(
            {
                "leg": 1,
                "pct": 100,
                "target": conservative_target,
                "action": f"Exit 100% at {conservative_target:,.0f}",
                "stop_adjust": None,
            }
        )

    return {
        "legs": legs,
        "time_stop": "Exit if flat after 10 sessions",
    }
