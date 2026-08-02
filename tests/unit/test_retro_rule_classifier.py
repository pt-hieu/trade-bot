"""Parametric coverage for classify_retro_rule.

Pure deterministic classifier — no async, no DB, no LLM. One test per
rule label plus a fallback case.
"""

from __future__ import annotations

import pytest

from shared.rules.retro_rule_classifier import classify_retro_rule


def _base_eval(**overrides) -> dict:
    row = {
        "ticker": "FPT",
        "recommendation": "BUY",
        "status": "PENDING",
        "entry_hit": False,
        "stop_hit": False,
        "target_hit": False,
        "pnl_percent": None,
        "day_change": None,
        "trade_executed": False,
        "actual_pl_pct": None,
        "plan_type": "SWING",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        # SWING entry outcomes
        (
            {
                "recommendation": "BUY",
                "entry_hit": True,
                "target_hit": True,
                "status": "WIN",
            },
            "SWING_TARGET_HIT",
        ),
        (
            {
                "recommendation": "BUY",
                "entry_hit": True,
                "stop_hit": True,
                "status": "LOSS",
            },
            "SWING_STOPPED",
        ),
        (
            {"recommendation": "BUY", "entry_hit": False, "status": "MISSED"},
            "SWING_MISSED",
        ),
        (
            {"recommendation": "BUY", "entry_hit": True, "status": "PENDING"},
            "SWING_PENDING",
        ),
        (
            {"recommendation": "BUY", "entry_hit": True, "status": "WIN"},
            "SWING_WIN",
        ),
        (
            {"recommendation": "BUY", "entry_hit": True, "status": "LOSS"},
            "SWING_LOSS",
        ),
        # SWING hold-family
        (
            {"recommendation": "HOLD", "day_change": 1.2, "status": "HOLD"},
            "SWING_HOLD",
        ),
        (
            {"recommendation": "HOLD", "stop_hit": True, "status": "STOP_BREACHED"},
            "SWING_STOPPED",
        ),
        (
            {"recommendation": "HOLD", "pnl_percent": 3.5, "status": "HOLD"},
            "SWING_WIN",
        ),
        (
            {"recommendation": "HOLD", "pnl_percent": -4.1, "status": "HOLD"},
            "SWING_LOSS",
        ),
        # Structural EXCLUDED actions
        (
            {"recommendation": "WATCH", "status": "EXCLUDED"},
            "WATCH_MISS",
        ),
        (
            {"recommendation": "WAIT", "status": "EXCLUDED"},
            "WAIT_UNMET",
        ),
        (
            {"recommendation": "SKIP", "status": "EXCLUDED"},
            "SKIP_CORRECT",
        ),
        (
            {"recommendation": "AVOID", "status": "EXCLUDED"},
            "SKIP_CORRECT",
        ),
        # LONGTERM plan-type
        (
            {"plan_type": "LONGTERM", "pnl_percent": -25.0, "status": "HOLD"},
            "LONGTERM_CATASTROPHIC",
        ),
        (
            {"plan_type": "LONGTERM", "pnl_percent": -5.0, "status": "HOLD"},
            "LONGTERM_THESIS_INTACT",
        ),
        (
            {"plan_type": "LONGTERM", "pnl_percent": 3.0, "status": "HOLD"},
            "LONGTERM_THESIS_INTACT",
        ),
        (
            {"plan_type": "LONGTERM", "status": "EXCLUDED"},
            "LONGTERM_EXCLUDED",
        ),
        # Manual trade closure
        (
            {"trade_executed": True, "actual_pl_pct": 4.2},
            "TRADE_EXECUTED_WIN",
        ),
        (
            {"trade_executed": True, "actual_pl_pct": -2.1},
            "TRADE_EXECUTED_LOSS",
        ),
    ],
)
def test_classify_retro_rule(overrides: dict, expected: str) -> None:
    eval_row = _base_eval(**overrides)
    assert classify_retro_rule(eval_row) == expected


def test_classify_retro_rule_unknown_shape_returns_unclassified() -> None:
    """An action the classifier doesn't recognise maps to UNCLASSIFIED, not None."""
    eval_row = _base_eval(recommendation="UNKNOWN_ACTION", status="HOLD")
    assert classify_retro_rule(eval_row) == "UNCLASSIFIED"


def test_classify_retro_rule_longterm_threshold_honours_override() -> None:
    """Custom longterm_catastrophic_pct raises the catastrophic floor."""
    eval_row = _base_eval(plan_type="LONGTERM", pnl_percent=-15.0, status="HOLD")
    # -15% is above the default 20% floor, so thesis intact.
    assert classify_retro_rule(eval_row) == "LONGTERM_THESIS_INTACT"
    # But with a stricter 10% floor the same row is catastrophic.
    assert classify_retro_rule(eval_row, longterm_catastrophic_pct=10.0) == "LONGTERM_CATASTROPHIC"
