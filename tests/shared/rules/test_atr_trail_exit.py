"""ATRTrailExit gate + alert tests."""

from __future__ import annotations

import pytest

from shared.rules.exit_atr_trail import ATRTrailExit
from shared.rules.exit_strategy import ExitState


def _state(
    entry: int = 50_000,
    stop: int = 45_000,
    atr: int = 1_000,
    adx: float | None = 30.0,
    catalyst: bool = False,
    strategy: str = "TREND",
    daily_limit_pct: float = 0.07,
) -> ExitState:
    return ExitState(
        entry_price=entry,
        stop_price=stop,
        target_price=None,
        atr_at_entry=atr,
        trail_mult=2.5,
        peak_price=None,
        strategy=strategy,
        adx=adx,
        has_positive_catalyst=catalyst,
        daily_limit_pct=daily_limit_pct,
    )


def test_rr_gate_passes_on_adx_strength() -> None:
    assert ATRTrailExit().rr_gate(_state(adx=30.0, catalyst=False), rr_floor=3.0) is True


def test_rr_gate_passes_on_positive_catalyst() -> None:
    assert ATRTrailExit().rr_gate(_state(adx=10.0, catalyst=True), rr_floor=3.0) is True


def test_rr_gate_passes_on_breakout_strategy() -> None:
    assert (
        ATRTrailExit().rr_gate(
            _state(adx=10.0, catalyst=False, strategy="BREAKOUT"),
            rr_floor=3.0,
        )
        is True
    )


def test_rr_gate_fails_without_signals() -> None:
    state = _state(adx=10.0, catalyst=False, strategy="TREND")
    assert ATRTrailExit().rr_gate(state, rr_floor=3.0) is False


def test_rr_gate_fails_on_excessive_loss() -> None:
    # Stop implies 30% drawdown — loss cap bites even with ADX>25.
    state = _state(entry=50_000, stop=35_000, adx=30.0)
    assert ATRTrailExit().rr_gate(state, rr_floor=3.0) is False


def test_build_exit_state_requires_atr() -> None:
    with pytest.raises(ValueError):
        ATRTrailExit().build_exit_state(
            levels={"nearest_support": 48_000, "swing_low": 47_000},
            close=50_000,
            atr=None,
            regime="NEUTRAL",
        )


def test_build_exit_state_shape() -> None:
    state = ATRTrailExit().build_exit_state(
        levels={"nearest_support": 48_000, "swing_low": 47_000},
        close=50_000,
        atr=1_000,
        regime="NEUTRAL",
    )
    assert state["entry_price"] == 48_000
    assert state["target_price"] is None
    assert state["atr_at_entry"] == 1_000
    assert state["trail_mult"] == 2.5
    assert state["stop_price"] < state["entry_price"]


def test_alert_tracks_peak_and_fires_trail_break() -> None:
    exit_strategy = ATRTrailExit()
    state = _state(entry=50_000, stop=45_000, atr=1_000)
    # Initial poll at rally high — establishes peak.
    assert exit_strategy.alert_condition(state, current_price=60_000, prev_close=59_000) is None
    assert state["peak_price"] == 60_000
    # Pullback to 57_000 — below trail (60_000 − 2.5×1_000 = 57_500).
    trigger = exit_strategy.alert_condition(state, current_price=57_000, prev_close=60_000)
    assert trigger is not None
    assert trigger["kind"] == "TRAIL_BREAK"


def test_alert_floor_lock_flag() -> None:
    exit_strategy = ATRTrailExit()
    state = _state(entry=50_000, stop=45_000, atr=1_000)
    # Establish peak first.
    exit_strategy.alert_condition(state, current_price=60_000, prev_close=59_000)
    # Next poll: price at HOSE floor (prev_close 60_000 × 0.93 = 55_800).
    trigger = exit_strategy.alert_condition(state, current_price=55_800, prev_close=60_000)
    assert trigger is not None
    assert trigger["kind"] == "LIKELY_FLOOR_LOCKED"


def test_to_db_row_leaves_target_null() -> None:
    row = ATRTrailExit().to_db_row(_state())
    assert row["target_price_vnd"] is None
    assert row["atr_at_entry_vnd"] == 1_000
    assert row["trail_mult"] == 2.5
