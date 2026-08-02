"""Exhaustiveness + correctness tests for retro deterministic prefixes.

Pyright is in `basic` mode, so match-exhaustiveness is not enforced at
type-check time. The parametrized `test_format_rule_prefix_covers_*`
test is the load-bearing exhaustiveness check — adding a new RetroRule
literal MUST add a branch to format_rule_prefix or this test fails.
"""

from __future__ import annotations

from typing import get_args

import pytest

from agents.retro.render import format_rule_prefix
from shared.narrative import format_execution_prefix
from shared.rules.retro_rule_classifier import RetroRule


def _row(**overrides) -> dict:
    base = {
        "ticker": "ACV",
        "day_change": 0.5,
        "pnl_percent": -1.0,
        "actual_pl_pct": 0.0,
        "actual_exit_price_vnd": 0,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("rule", list(get_args(RetroRule)))
def test_format_rule_prefix_covers_every_literal(rule):
    out = format_rule_prefix(rule, _row())
    assert out, f"empty prefix for {rule}"
    assert isinstance(out, str)


def test_longterm_thesis_intact_uses_day_change():
    out = format_rule_prefix("LONGTERM_THESIS_INTACT", _row(day_change=0.8))
    assert "LONGTERM thesis intact" in out
    assert "+0.8%" in out
    assert "SWING" not in out  # SWI-135: no SWING phrasing on LONGTERM rows


def test_swing_hold_passes_when_day_positive():
    out = format_rule_prefix("SWING_HOLD", _row(day_change=1.2))
    assert "passed" in out


def test_swing_hold_fails_when_day_non_positive():
    out = format_rule_prefix("SWING_HOLD", _row(day_change=0.0))
    assert "failed" in out


def test_format_execution_prefix_not_executed_when_false():
    assert format_execution_prefix({"trade_executed": False}) == "NOT_EXECUTED."


def test_format_execution_prefix_not_executed_when_missing():
    assert format_execution_prefix({}) == "NOT_EXECUTED."


def test_format_execution_prefix_executed():
    out = format_execution_prefix(
        {"trade_executed": True, "actual_exit_price_vnd": 44910, "actual_pl_pct": -3.5}
    )
    assert out == "EXECUTED: exit=44,910VND, pnl=-3.50%."


def test_format_execution_prefix_handles_none_safe():
    # actual_exit_price_vnd=None should not crash (CLAUDE.md None-safe rule)
    out = format_execution_prefix(
        {"trade_executed": True, "actual_exit_price_vnd": None, "actual_pl_pct": None}
    )
    assert "EXECUTED:" in out
