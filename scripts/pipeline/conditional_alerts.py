"""Build conditional-buy alert payloads for WATCH/WAIT recommendation rows.

The morning pipeline emits structured WATCH/WAIT plans with a trigger
price + plan_shape. This module turns those rows into alert payloads
that `scripts/shared/neon/alerts.register_alert` can persist atomically
with the recommendation insert. When the trigger fires intraday,
`scripts/run_alert_analysis.py` upgrades the WATCH into a real BUY in
`daily_recommendations`, closing the WATCH→BUY loop.
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict

from agents.retro.parser import SECTION_WHAT_TO_DO
from shared.market_calendar import next_n_trading_days


class _AlertCondition(TypedDict):
    type: str  # 'price_above' | 'price_below' | 'volume_spike'
    value: float
    params: dict


class ConditionalAlertPayload(TypedDict):
    ticker: str
    action_type: str
    source: str
    source_date: date
    rationale: str | None
    recommended_action: str
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    condition_logic: str
    expires_at: date
    priority: str
    conditions: list[_AlertCondition]
    alert_metadata: dict


# Trigger geometry per plan_shape:
#   BREAKOUT     — price_above(trigger) AND volume_spike(>=1.5x)
#   PULLBACK     — price_below(trigger)  (price retraces into MA20 zone)
#   TREND_PULLBACK — price_below(trigger)
#   BOUNCE       — price_below(trigger)  (touch of nearest_support)
#   MEAN_REVERT  — price_below(trigger)
#   NONE         — no alert registered
_PRICE_BELOW_SHAPES = frozenset({"PULLBACK", "TREND_PULLBACK", "BOUNCE", "MEAN_REVERT"})


def build_conditional_alert_payloads(
    recs: list[dict], scan_date: date, alert_horizon_days: int = 5
) -> list[ConditionalAlertPayload]:
    """Map WATCH/WAIT rec rows → alert payloads. Pure function."""
    expires_at = next_n_trading_days(scan_date, alert_horizon_days)
    payloads: list[ConditionalAlertPayload] = []

    for rec in recs:
        if rec.get("section") != SECTION_WHAT_TO_DO:
            continue
        if (rec.get("action") or "").upper() not in ("WATCH", "WAIT"):
            continue
        trigger_raw = rec.get("trigger_price")
        if not trigger_raw:
            continue
        try:
            trigger = float(trigger_raw)
        except (TypeError, ValueError):
            continue
        if trigger <= 0:
            continue

        shape = (rec.get("plan_shape") or "").upper()
        if shape == "BREAKOUT":
            conditions: list[_AlertCondition] = [
                {"type": "price_above", "value": trigger, "params": {}},
                {"type": "volume_spike", "value": 1.5, "params": {}},
            ]
        elif shape in _PRICE_BELOW_SHAPES:
            conditions = [{"type": "price_below", "value": trigger, "params": {}}]
        else:
            # NONE or unknown — no alert registered (row still ships).
            continue

        payloads.append(
            ConditionalAlertPayload(
                ticker=rec["ticker"],
                action_type="notify_and_analyze",
                source="conditional_watch",
                source_date=scan_date,
                rationale=rec.get("rationale"),
                recommended_action="BUY",
                entry_price=rec.get("trigger_price"),
                stop_price=rec.get("stop_price"),
                target_price=rec.get("target_price"),
                condition_logic="ALL",
                expires_at=expires_at,
                priority="normal",
                conditions=conditions,
                alert_metadata={
                    "plan_shape": shape,
                    "invalidation_note": rec.get("invalidation_note"),
                    "gate_floor_at_build": rec.get("gate_floor_at_build"),
                    "gate_passes_at_build": rec.get("gate_passes_at_build"),
                },
            )
        )

    return payloads
