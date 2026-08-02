"""Alerting helpers — pipeline-health notifications routed through Telegram."""

from .silent_hang_alert import maybe_emit_silent_hang_alert

__all__ = ["maybe_emit_silent_hang_alert"]
