"""Centralized pipeline decision rules — pure deterministic Python.

No async, no DB, no LLM. All functions are pure and testable.

Modules:
    constraints        — urgency, reachability, composition, circuit breakers
    entry_gates        — entry gate decision (entries_allowed + reason)
    rr_floors          — R:R floor constants and regime-based computation
    geopolitical       — shock phase config, date parsing, validation
    catalyst_lifecycle — phase status resolution with grace period
    catalyst_news      — catalyst-news keyword matching and spike detection
    catalyst_override  — catalyst-aware context boosting for entry strategist
    exit_strategy      — ExitStrategy Protocol + dispatch
    exit_fixed_target  — FixedTargetExit for MR/BOUNCE/PULLBACK/DIVERGENCE
    exit_atr_trail     — ATRTrailExit for TREND/MOMENTUM/BREAKOUT
    trail_sim          — Pure ATR trailing-stop simulator used by retro
"""

from .exit_atr_trail import ATRTrailExit
from .exit_fixed_target import FixedTargetExit
from .exit_strategy import (
    ATR_TRAIL_STRATEGIES,
    AlertKind,
    AlertTrigger,
    ExitEvalResult,
    ExitFamilyName,
    ExitState,
    ExitStatus,
    ExitStrategy,
    TrailBar,
    exit_state_from_rec,
    resolve_exit_strategy,
)
from .trail_sim import TrailResult, TrailStatus, simulate_atr_trail

__all__ = [
    "ATR_TRAIL_STRATEGIES",
    "ATRTrailExit",
    "AlertKind",
    "AlertTrigger",
    "ExitEvalResult",
    "ExitFamilyName",
    "ExitState",
    "ExitStatus",
    "ExitStrategy",
    "FixedTargetExit",
    "TrailBar",
    "TrailResult",
    "TrailStatus",
    "exit_state_from_rec",
    "resolve_exit_strategy",
    "simulate_atr_trail",
]
