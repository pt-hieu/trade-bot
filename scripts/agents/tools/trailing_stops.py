"""Deterministic trailing stop computation for portfolio holdings."""

from shared.trading_config import get_trading_config


def compute_trailing_stop(
    entry: float,
    current: float,
    plan_type: str,
    weight_pct: float,
    old_stop: float | None = None,
    breakeven_stop: int | None = None,
) -> dict:
    """Deterministic trailing stop for holdings.

    LONGTERM positions get no stop (thesis-based, not technical).
    SWING positions get progressively tighter trailing stops as gains increase.

    Args:
        entry: Average cost in VND (e.g., 93000)
        current: Current price in VND
        plan_type: "LONGTERM" or "SWING"
        weight_pct: Portfolio weight percentage
        old_stop: Previous stop level (trail never moves down)
        breakeven_stop: Pre-set catastrophic floor on the holding record (VND).
            When provided AND the position is underwater (gain_pct < 0), the
            function returns a `breakeven_floor` row so the catastrophic-floor
            alert path stays inside the existing trailing_stops writer +
            register_trailing_stop_alerts reader (no parallel registrar).
            SWI-157 Option A (2026-05-14): hit by ACV today — open underwater
            SWING shipped without a morning stop alert because the underwater
            branch returned `stop=None`.

    Returns:
        Dict with stop, stop_type, action_hint, and optional note.
    """
    gain_pct = ((current - entry) / entry) * 100 if entry > 0 else 0
    cfg = get_trading_config()

    if plan_type == "LONGTERM":
        catastrophic_floor = 1.0 - (cfg.longterm_catastrophic_pct / 100)
        catastrophic = round(entry * catastrophic_floor, 1) if entry > 0 else None
        result: dict = {
            "stop": None,
            "stop_type": "thesis_based",
            "action_hint": "HOLD",
            "catastrophic_stop": catastrophic,
            "thesis_checkpoints": [
                "ROE deterioration 2+ consecutive quarters",
                "Sector thesis break (regulatory/structural)",
                "Revenue/presales growth turns negative YoY",
            ],
        }
        if weight_pct > cfg.longterm_review_weight_pct:
            result["action_hint"] = "REVIEW_CONCENTRATION"
            result["note"] = (
                f"Weight {weight_pct:.1f}% > {cfg.longterm_review_weight_pct:.0f}% — consider trimming"
            )
        return result

    # SWING trailing stops
    if gain_pct < 0:
        if breakeven_stop is not None and breakeven_stop > 0:
            return {
                "stop": int(breakeven_stop),
                "stop_type": "breakeven_floor",
                "action_hint": "USE_BREAKEVEN",
            }
        return {"stop": None, "stop_type": "technical", "action_hint": "USE_LEVELS"}
    if gain_pct < cfg.breakeven_gain_pct:
        return {"stop": entry, "stop_type": "breakeven", "action_hint": "HOLD"}
    if gain_pct < cfg.half_trail_gain_pct:
        trail = entry + (current - entry) * 0.5
        stop = round(trail)
        if old_stop:
            stop = max(stop, old_stop)
        return {"stop": stop, "stop_type": "trailing_50pct", "action_hint": "HOLD"}

    # tight_trail_gain_pct%+ — tight trail
    floor_pct = cfg.tight_current_floor_pct / 100
    lock_pct = cfg.tight_gain_lock_pct / 100
    trail = max(current * floor_pct, entry + (current - entry) * lock_pct)
    stop = round(trail)
    if old_stop:
        stop = max(stop, old_stop)
    return {"stop": stop, "stop_type": "trailing_tight", "action_hint": "TRIM_OR_TRAIL"}
