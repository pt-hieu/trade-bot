"""SWI-255: retro_commentary input must use a single kVND price shape.

Three drifted shapes (``:,.0f`` truncation, ``:,.1f`` w/ suffix, raw
``:,VND`` integer) coexisted on 2026-05-13. The retro_commentary agent
reconciled the inconsistency by inventing ``34,750`` for TCB. This test
pins every price field in ``format_evals_for_llm`` output to the
``<num>.<digit>k`` shape so the precision gap can't reopen.
"""

from __future__ import annotations

import re

from agents.retro.commentary import format_evals_for_llm

_KVND_PATTERN = re.compile(r"\d[\d,]*\.\d+k")


def _tcb_hold_row() -> dict:
    return {
        "ticker": "TCB",
        "plan_type": "LONGTERM",
        "rule_applied": "LONGTERM_THESIS_INTACT",
        "recommendation": "HOLD",
        "status": "HOLD",
        "entry_hit": False,
        "stop_hit": False,
        "target_hit": False,
        "pnl_percent": 3.4,
        "day_change": -0.6,
        "prev_close": 33.75,
        "eod_price": 33.6,
        "trade_executed": False,
    }


def _executed_row() -> dict:
    return {
        "ticker": "FPT",
        "plan_type": "SWING",
        "rule_applied": "TRADE_EXECUTED_WIN",
        "recommendation": "BUY",
        "status": "WIN",
        "entry_hit": True,
        "stop_hit": False,
        "target_hit": True,
        "pnl_percent": 5.2,
        "day_change": 2.3,
        "prev_close": 100.0,
        "eod_price": 105.2,
        "trade_executed": True,
        "actual_exit_price_vnd": 105_200,
        "actual_pl_pct": 5.2,
    }


def test_eod_renders_as_kvnd_not_truncated_integer() -> None:
    out = format_evals_for_llm([_tcb_hold_row()])
    assert "EOD:33.6k" in out
    # the old shape was a bare ``"EOD:34"`` (banker-rounded :,.0f) — must
    # never appear again.
    assert "EOD:34 " not in out
    assert "EOD:34\n" not in out


def test_prev_close_renders_as_kvnd() -> None:
    out = format_evals_for_llm([_tcb_hold_row()])
    assert "prev:33.8k" in out  # 33.75 -> 33.8 banker-rounded
    assert "prev:34" not in out


def test_executed_exit_renders_as_kvnd() -> None:
    out = format_evals_for_llm([_executed_row()])
    # actual_exit_price_vnd is raw VND; divided by 1000 then format_kvnd.
    assert "exit=105.2k" in out
    # legacy ``exit=105,200VND`` shape must not return.
    assert "VND" not in out.split("exit=")[1].split(" ")[0]


def test_every_price_field_matches_kvnd_shape() -> None:
    rows = [_tcb_hold_row(), _executed_row()]
    out = format_evals_for_llm(rows)
    for label in ("EOD:", "prev:", "exit="):
        for line in out.splitlines():
            if label not in line:
                continue
            chunk = line.split(label, 1)[1].split(" ", 1)[0]
            assert _KVND_PATTERN.match(chunk), f"{label} value {chunk!r} does not match kVND shape"
