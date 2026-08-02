"""SWI-57: catalyst_boost_dropped log_warn probe."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch


def _call(boosted, signals, picks):
    from pipeline import phase_picks

    with patch.object(phase_picks, "log_warn") as mock:
        phase_picks._log_catalyst_boost_dropped(boosted, signals, picks, date(2026, 5, 3))
    return mock


def test_no_boosted_no_emit():
    mock = _call(None, [], [])
    assert not mock.called
    mock = _call(set(), [], [])
    assert not mock.called


def test_all_boosted_picked_no_emit():
    mock = _call({"FPT"}, [{"ticker": "FPT", "signal": "BUY"}], [{"ticker": "FPT"}])
    assert not mock.called


def test_partitions_no_buy_vs_filtered():
    boosted = {"FPT", "MWG"}
    signals = [
        {"ticker": "FPT", "signal": "BUY"},  # boosted, BUY but no pick → filtered
        {"ticker": "MWG", "signal": "HOLD"},  # boosted, no BUY → no_buy
    ]
    picks: list[dict] = []
    mock = _call(boosted, signals, picks)
    assert mock.called
    args, kwargs = mock.call_args
    assert args[0] == "catalyst_boost_dropped"
    assert kwargs["boosted_no_pick"] == ["MWG"]
    assert kwargs["boosted_filtered"] == ["FPT"]
    assert kwargs["scan_date"] == "2026-05-03"
