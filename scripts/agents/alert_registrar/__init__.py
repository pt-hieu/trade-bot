"""
Alert Registrar — deterministic alert registration from pipeline data.

Runs as a pipeline phase after synthesis. Registers price/technical alerts in the DB
via deterministic paths only: picks, trailing stops, dip-buys.
"""

from .conflict_resolution import (
    resolve_alert_conflicts,
    send_immediate_position_directives,
)
from .deterministic import (
    register_picks_as_alerts,
    register_trailing_stop_alerts,
)
from .dip_buy import register_dip_buy_alerts

__all__ = [
    # Deterministic alert registration
    "register_picks_as_alerts",
    "register_trailing_stop_alerts",
    "register_dip_buy_alerts",
    # Conflict resolution
    "resolve_alert_conflicts",
    "send_immediate_position_directives",
]
