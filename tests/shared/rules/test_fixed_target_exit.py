"""FixedTargetExit behaviour tests — preserves pre-refactor MR semantics."""

from __future__ import annotations

from shared.rules.exit_fixed_target import FixedTargetExit
from shared.rules.exit_strategy import ExitState


def _state(entry: int = 50_000, stop: int = 45_000, target: int = 60_000) -> ExitState:
    return ExitState(
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        atr_at_entry=None,
        trail_mult=None,
        peak_price=None,
    )


def test_rr_gate_passes_when_rr_above_floor() -> None:
    exit_strategy = FixedTargetExit()
    # risk=5_000 reward=10_000 → gross R:R 2.0
    assert exit_strategy.rr_gate(_state(), rr_floor=1.5) is True


def test_rr_gate_fails_when_rr_below_floor() -> None:
    exit_strategy = FixedTargetExit()
    assert exit_strategy.rr_gate(_state(), rr_floor=3.5) is False


def test_evaluate_bars_target_hit_same_day() -> None:
    exit_strategy = FixedTargetExit()
    bars = [{"date": "2026-01-02", "open": 49_000, "high": 61_000, "low": 48_500, "close": 60_500}]
    result = exit_strategy.evaluate_bars(_state(), bars, "2026-01-02")
    assert result["status"] == "WIN"
    assert result["target_hit"] is True


def test_evaluate_bars_stop_before_target() -> None:
    """Stop and target both touched same bar → LOSS wins."""
    exit_strategy = FixedTargetExit()
    bars = [{"date": "2026-01-02", "open": 49_000, "high": 61_000, "low": 44_000, "close": 55_000}]
    result = exit_strategy.evaluate_bars(_state(), bars, "2026-01-02")
    assert result["status"] == "LOSS"


def test_alert_condition_fires_on_target() -> None:
    trigger = FixedTargetExit().alert_condition(_state(), current_price=60_500, prev_close=59_000)
    assert trigger is not None
    assert trigger["kind"] == "TARGET_HIT"


def test_to_db_row_shape() -> None:
    row = FixedTargetExit().to_db_row(_state())
    assert row["target_price_vnd"] == 60_000
    assert row["atr_at_entry_vnd"] is None
    assert row["trail_mult"] is None


def test_exit_description() -> None:
    text = FixedTargetExit().exit_description(_state())
    assert "Target 60.0k" in text
    assert "R:R 2.0" in text
