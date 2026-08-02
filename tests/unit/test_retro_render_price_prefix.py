"""SWI-255: stamp_deterministic_prefix injects an EOD price stamp on HOLD rows.

The agent prompt's per-ticker analysis line already carries a kVND EOD
in retro_commentary input (see test_retro_commentary_format), but the
LLM-stamped narrative carries no deterministic price anchor for HOLD
rows. Without one, the agent free-composes prices when the prompt
contains conflicting shapes elsewhere (TCB 2026-05-13 incident).
"""

from __future__ import annotations

from agents.retro.render import stamp_deterministic_prefix


def test_hold_row_gets_price_prefix() -> None:
    row = {
        "rule_applied": "LONGTERM_THESIS_INTACT",
        "day_change": -0.6,
        "pnl_percent": 3.4,
        "eod_price": 33.6,
        "prev_close": 33.75,
        "trade_executed": False,
    }
    stamped = stamp_deterministic_prefix(row, "Thesis intact.")
    assert "EOD: 33.6k VND" in stamped
    assert "prev close: 33.8k VND" in stamped
    assert "Thesis intact." in stamped


def test_executed_row_omits_price_prefix() -> None:
    row = {
        "rule_applied": "TRADE_EXECUTED_WIN",
        "actual_pl_pct": 5.2,
        "actual_exit_price_vnd": 105_200,
        "trade_executed": True,
        "eod_price": 105.2,
        "prev_close": 100.0,
    }
    stamped = stamp_deterministic_prefix(row, "Clean exit at target.")
    # Execution prefix carries the deterministic exit price already.
    assert "exit=105,200VND" in stamped
    # Don't double-stamp HOLD-style price prefix.
    assert "[EOD:" not in stamped


def test_missing_eod_or_prev_skips_prefix() -> None:
    row = {
        "rule_applied": "SWING_PENDING",
        "day_change": 0.0,
        "trade_executed": False,
        # eod_price + prev_close intentionally absent
    }
    stamped = stamp_deterministic_prefix(row, "Pending entry.")
    assert "[EOD:" not in stamped
