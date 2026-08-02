"""Tests for watchlist universe gate in recommendation_builder.

Group 5 of 2026-04-19 pipeline review fixes. Resolves MON-2026-04-19-005
(VIC off-universe emission). Fails closed on upstream universe-fetch failure.
"""

from __future__ import annotations

import pytest

from pipeline.phase_recommendations import _build_valid_tickers
from pipeline.recommendation_builder import build_structured_recommendations


def _sector_signal(ticker: str, action: str = "BUY") -> dict:
    return {
        "ticker": ticker,
        "action": action,
        "rationale": "test signal",
        "signal_confidence": 0.6,
    }


def test_off_universe_ticker_dropped(caplog):
    """VIC not in swing/longterm/portfolio → dropped with REC_OFF_WATCHLIST warning."""
    recs = build_structured_recommendations(
        pre_computed_picks=[],
        position_alerts={"alerts": []},
        sector_signals=[_sector_signal("VIC"), _sector_signal("FPT")],
        holdings=[{"ticker": "FPT", "plan_type": "SWING"}],
        trading_mode={"mode": "NORMAL"},
        valid_tickers=frozenset({"FPT"}),
    )
    tickers = {r["ticker"] for r in recs}
    assert "VIC" not in tickers


def test_on_universe_ticker_kept():
    recs = build_structured_recommendations(
        pre_computed_picks=[],
        position_alerts={"alerts": []},
        sector_signals=[_sector_signal("FPT")],
        holdings=[{"ticker": "FPT", "plan_type": "SWING"}],
        trading_mode={"mode": "NORMAL"},
        valid_tickers=frozenset({"FPT"}),
    )
    tickers = {r["ticker"] for r in recs}
    assert "FPT" in tickers


def test_valid_tickers_none_no_filter():
    """Backward-compat: valid_tickers=None → no filter (legacy callers)."""
    recs = build_structured_recommendations(
        pre_computed_picks=[],
        position_alerts={"alerts": []},
        sector_signals=[_sector_signal("VIC"), _sector_signal("FPT")],
        holdings=[],
        trading_mode={"mode": "NORMAL"},
    )
    tickers = {r["ticker"] for r in recs}
    assert {"VIC", "FPT"}.issubset(tickers)


class TestBuildValidTickers:
    def test_all_three_sources_merged(self):
        result = _build_valid_tickers(
            swing_watchlist_tickers={"FPT", "TCB"},
            longterm_watchlist={"HPG": {}, "MSN": {}},
            holdings=[{"ticker": "VHM", "plan_type": "SWING"}],
        )
        assert result == frozenset({"FPT", "TCB", "HPG", "MSN", "VHM"})

    def test_universe_fetch_failed_when_all_empty(self):
        with pytest.raises(RuntimeError, match="UNIVERSE_FETCH_FAILED"):
            _build_valid_tickers(
                swing_watchlist_tickers=set(),
                longterm_watchlist={},
                holdings=[],
            )

    def test_universe_fetch_failed_on_none_inputs(self):
        with pytest.raises(RuntimeError, match="UNIVERSE_FETCH_FAILED"):
            _build_valid_tickers(
                swing_watchlist_tickers=None,
                longterm_watchlist=None,
                holdings=None,
            )

    def test_single_source_nonempty_ok(self):
        result = _build_valid_tickers(
            swing_watchlist_tickers=None,
            longterm_watchlist=None,
            holdings=[{"ticker": "FPT", "plan_type": "SWING"}],
        )
        assert "FPT" in result

    def test_normalizes_to_uppercase(self):
        result = _build_valid_tickers(
            swing_watchlist_tickers={"fpt"},
            longterm_watchlist={"hpg": {}},
            holdings=[{"ticker": "vhm", "plan_type": "SWING"}],
        )
        assert result == frozenset({"FPT", "HPG", "VHM"})
