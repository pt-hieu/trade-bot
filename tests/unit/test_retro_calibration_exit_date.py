"""SWI-15: latest_exit derivation + missing-exit_date warn."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from agents.retro import calibration


def _record(evals):
    return {"evaluations": evals}


def test_latest_exit_derived_from_closed_evals():
    records = [
        _record(
            [
                {
                    "recommendation": "BUY",
                    "entry_hit": True,
                    "won": True,
                    "exit_date": "2026-04-20",
                    "ticker": "FPT",
                },
                {
                    "recommendation": "BUY",
                    "entry_hit": True,
                    "won": False,
                    "exit_date": "2026-04-25",
                    "ticker": "MWG",
                },
            ]
        )
    ]
    with patch.object(calibration, "log_warn"):
        out = calibration.calc_calibration_stats(
            records, rolling_days=7, scan_date=date(2026, 5, 3)
        )
    assert out["last_trade_exit_date"] == "2026-04-25"


def test_log_warn_fires_for_closed_eval_missing_exit_date():
    records = [
        _record(
            [
                {
                    "recommendation": "BUY",
                    "entry_hit": True,
                    "won": True,
                    "exit_date": None,
                    "ticker": "VHM",
                },
            ]
        )
    ]
    with patch.object(calibration, "log_warn") as mock_warn:
        calibration.calc_calibration_stats(records, rolling_days=7, scan_date=date(2026, 5, 3))
    assert mock_warn.called
    args, kwargs = mock_warn.call_args
    assert args[0] == "calibration_missing_exit_date"
    assert kwargs["ticker"] == "VHM"


def test_open_eval_does_not_warn():
    records = [
        _record(
            [
                {
                    "recommendation": "BUY",
                    "entry_hit": True,
                    "won": None,  # PENDING
                    "exit_date": None,
                    "ticker": "VCB",
                },
            ]
        )
    ]
    with patch.object(calibration, "log_warn") as mock_warn:
        calibration.calc_calibration_stats(records, rolling_days=7, scan_date=date(2026, 5, 3))
    assert not mock_warn.called
