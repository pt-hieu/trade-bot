"""Tests for the SWI-255 EXECUTION_FABRICATION validator check."""

from __future__ import annotations

from agents.retro.validate import validate_eval_commentary


def _pre(ticker: str, **overrides) -> dict:
    base = {
        "ticker": ticker,
        "recommendation": "HOLD",
        "status": "HOLD",
        "entry_hit": False,
        "stop_hit": True,
        "target_hit": False,
        "trade_executed": False,
        "eod_price": 44800,
        "pnl_percent": -3.5,
        "day_change": 1.8,
        "direction_correct": False,
    }
    base.update(overrides)
    return base


def _analysis(ticker: str, text: str) -> dict:
    return {"ticker": ticker, "analysis": text, "error_type": "N/A", "lesson": ""}


def test_flags_executed_correctly_when_trade_not_executed():
    """ACV 2026-05-05: 'EXIT executed correctly' fabrication."""
    result = validate_eval_commentary(
        [_analysis("ACV", "ACV EXIT executed correctly — stop at 44,910 touched intraday")],
        [_pre("ACV", trade_executed=False)],
    )
    fab = [v for v in result.violations if v.check == "EXECUTION_FABRICATION"]
    assert fab, "expected EXECUTION_FABRICATION"


def test_passes_signal_language():
    """signal-language rephrasing should NOT trigger the check."""
    result = validate_eval_commentary(
        [
            _analysis(
                "ACV",
                "Intraday touched stop at 44.91k; signal cancelled but bounced +1.8% EOD.",
            )
        ],
        [_pre("ACV", trade_executed=False)],
    )
    fab = [v for v in result.violations if v.check == "EXECUTION_FABRICATION"]
    assert not fab


def test_passes_when_trade_actually_executed():
    """When trade_executed=True, outcome verbs are factual, not fabrication."""
    result = validate_eval_commentary(
        [_analysis("ACV", "Position closed at 44,910 per stop discipline.")],
        [_pre("ACV", trade_executed=True)],
    )
    fab = [v for v in result.violations if v.check == "EXECUTION_FABRICATION"]
    assert not fab
