"""Registry/dispatch + state materialisation tests for ExitStrategy."""

from __future__ import annotations

import pytest

from shared.rules.exit_atr_trail import ATRTrailExit
from shared.rules.exit_fixed_target import FixedTargetExit
from shared.rules.exit_strategy import (
    ATR_TRAIL_STRATEGIES,
    exit_state_from_rec,
    resolve_exit_strategy,
)


@pytest.mark.parametrize(
    "strategy",
    ["MEAN_REVERSION", "BOUNCE", "DIVERGENCE", "PULLBACK", "UNCLASSIFIED", "", None],
)
def test_dispatch_fixed_target(strategy: str | None) -> None:
    assert isinstance(resolve_exit_strategy(strategy), FixedTargetExit)
    assert resolve_exit_strategy(strategy).name == "FIXED_TARGET"


@pytest.mark.parametrize("strategy", ["TREND", "MOMENTUM", "BREAKOUT"])
def test_dispatch_atr_trail(strategy: str) -> None:
    assert isinstance(resolve_exit_strategy(strategy), ATRTrailExit)
    assert resolve_exit_strategy(strategy).name == "ATR_TRAIL"


def test_atr_trail_strategies_constant() -> None:
    assert frozenset({"TREND", "MOMENTUM", "BREAKOUT"}) == ATR_TRAIL_STRATEGIES


def test_exit_state_from_rec_fixed_target() -> None:
    rec = {
        "entry_price": 50_000,
        "stop_price": 45_000,
        "target_price": 60_000,
        "strategy": "MEAN_REVERSION",
    }
    state = exit_state_from_rec(rec)
    assert state["entry_price"] == 50_000
    assert state["stop_price"] == 45_000
    assert state["target_price"] == 60_000
    assert state["atr_at_entry"] is None
    assert state["trail_mult"] is None


def test_exit_state_from_rec_atr_trail() -> None:
    rec = {
        "entry_price_vnd": 72_500,
        "stop_price_vnd": 68_000,
        "target_price_vnd": None,
        "atr_at_entry_vnd": 1_200,
        "trail_mult": 2.5,
        "trail_peak_vnd": 78_000,
        "strategy": "TREND",
    }
    state = exit_state_from_rec(rec)
    assert state["entry_price"] == 72_500
    assert state["target_price"] is None
    assert state["atr_at_entry"] == 1_200
    assert state["trail_mult"] == 2.5
    assert state["peak_price"] == 78_000


def test_exit_state_none_safe() -> None:
    """NULL columns must not crash exit_state_from_rec (CLAUDE.md rule 13)."""
    rec = {"entry_price_vnd": None, "stop_price_vnd": None, "strategy": None}
    state = exit_state_from_rec(rec)
    assert state["entry_price"] == 0
    assert state["stop_price"] == 0
    assert state["target_price"] is None
