"""SWI-304: pre-removal guardrail unit tests."""

import pytest

from agents.watchlist_update import _should_block_removal


def test_recent_rally_blocks():
    blocked, reason, ret = _should_block_removal(
        "VIC", {"VIC": {"ret_5d": 0.066}}, holdings=set(), catalyst_tickers=set()
    )
    assert blocked is True
    assert "rally_block" in reason
    assert ret == pytest.approx(0.066)


def test_active_high_catalyst_blocks():
    blocked, reason, _ = _should_block_removal("FPT", {}, holdings=set(), catalyst_tickers={"FPT"})
    assert blocked is True
    assert reason == "active_high_catalyst"


def test_currently_held_blocks():
    blocked, reason, _ = _should_block_removal("TCB", {}, holdings={"TCB"}, catalyst_tickers=set())
    assert blocked is True
    assert reason == "currently_held"


def test_no_condition_allows_removal():
    blocked, reason, _ = _should_block_removal(
        "XYZ", {"XYZ": {"ret_5d": 0.01}}, holdings=set(), catalyst_tickers=set()
    )
    assert blocked is False
    assert reason == ""


def test_first_match_reason_wins_rally_over_held():
    blocked, reason, _ = _should_block_removal(
        "VIC",
        {"VIC": {"ret_5d": 0.10}},
        holdings={"VIC"},
        catalyst_tickers={"VIC"},
    )
    assert blocked is True
    assert "rally_block" in reason  # rally has precedence in the chain


def test_threshold_boundary_inclusive():
    # exactly at 5% — block (>=)
    blocked, _, _ = _should_block_removal(
        "X", {"X": {"ret_5d": 0.05}}, holdings=set(), catalyst_tickers=set()
    )
    assert blocked is True
    # 4.99% — allow
    blocked2, _, _ = _should_block_removal(
        "X", {"X": {"ret_5d": 0.0499}}, holdings=set(), catalyst_tickers=set()
    )
    assert blocked2 is False
