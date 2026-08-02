"""Value-parity tests for retro_rule_classifier (SWI-206)."""

from __future__ import annotations

import pytest

from shared.rules.retro_rule_classifier import classify_retro_rule


def _row(**overrides) -> dict:
    base = {
        "plan_type": "SWING",
        "recommendation": "BUY",
        "status": "WIN",
        "entry_hit": True,
        "stop_hit": False,
        "target_hit": False,
        "pnl_percent": None,
        "day_change": None,
        "trade_executed": False,
        "actual_pl_pct": None,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "row,want",
    [
        (_row(target_hit=True), "SWING_TARGET_HIT"),
        (_row(stop_hit=True), "SWING_STOPPED"),
        (_row(entry_hit=False), "SWING_MISSED"),
        (_row(status="LOSS"), "SWING_LOSS"),
        (_row(recommendation="WATCH"), "WATCH_MISS"),
        (_row(recommendation="WAIT"), "WAIT_UNMET"),
        (_row(recommendation="SKIP"), "SKIP_CORRECT"),
        (
            _row(plan_type="LONGTERM", status="HELD", pnl_percent=-25.0),
            "LONGTERM_CATASTROPHIC",
        ),
        (_row(plan_type="LONGTERM", status="HELD", pnl_percent=-5.0), "LONGTERM_THESIS_INTACT"),
        (_row(trade_executed=True, actual_pl_pct=2.0), "TRADE_EXECUTED_WIN"),
        (_row(trade_executed=True, actual_pl_pct=-1.0), "TRADE_EXECUTED_LOSS"),
        (_row(trade_executed=True, actual_pl_pct=None), "TRADE_EXECUTED_WIN"),
        (_row(recommendation="UNKNOWN"), "UNCLASSIFIED"),
    ],
)
def test_value_parity(row: dict, want: str) -> None:
    assert classify_retro_rule(row) == want


def test_unclassified_emits(capture_emits: list[dict]) -> None:
    classify_retro_rule(_row(recommendation="UNKNOWN"))
    assert any(
        e["rule_id"] == "retro_rule" and e["outcome"] == "unclassified" for e in capture_emits
    )


def test_longterm_catastrophic_emits_coerced(capture_emits: list[dict]) -> None:
    classify_retro_rule(_row(plan_type="LONGTERM", status="HELD", pnl_percent=-30.0))
    assert any(
        e["reason"] == "longterm_catastrophic" and e["outcome"] == "coerced" for e in capture_emits
    )


def test_trade_executed_zero_pnl_emits(capture_emits: list[dict]) -> None:
    classify_retro_rule(_row(trade_executed=True, actual_pl_pct=None))
    assert any(
        e["reason"] == "trade_executed_zero_pnl" and e["outcome"] == "coerced"
        for e in capture_emits
    )
