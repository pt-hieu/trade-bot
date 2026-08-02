#!/usr/bin/env python3
"""Position alert models shared by positions_ensemble_aggregator."""

from pydantic import BaseModel

from .belief_models import AggregatedBelief


class PositionAlert(BaseModel):
    """Alert for a single position with rich context."""

    ticker: str
    action: str  # HOLD, TRIM, ADD, EXIT, EVALUATE
    urgency: str  # high, medium, low
    reason: str
    target: str  # Price target or "N/A"
    stop: str  # Stop-loss or "N/A"
    entry_price: str | None = None
    current_price: str | None = None
    pct_from_entry: str | None = None
    weight_pct: str | None = None
    volume_signal: str | None = None
    counter_thesis: str | None = None


class PositionMonitorResult(BaseModel):
    """Result from position aggregator — alerts + reconciled beliefs."""

    alerts: list[PositionAlert]
    summary: str
    beliefs: list[AggregatedBelief] = []
