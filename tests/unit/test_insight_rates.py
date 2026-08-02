"""Tests for deterministic sector/ticker insight rate calculation and normalization."""

import pytest

from agents.retro.patterns import _calc_sector_stats, _calc_ticker_stats

# ---------------------------------------------------------------------------
# _calc_ticker_stats
# ---------------------------------------------------------------------------


class TestCalcTickerStats:
    """Calculate per-ticker win/total from daily evaluation records."""

    def test_basic_counts(self):
        records = [
            {
                "evaluations": [
                    {"ticker": "VHM", "won": True},
                    {"ticker": "VHM", "won": False},
                    {"ticker": "TCB", "won": True},
                ]
            }
        ]
        stats = _calc_ticker_stats(records, 7)
        assert stats["VHM"]["total"] == 2
        assert stats["VHM"]["won"] == 1
        assert stats["TCB"]["total"] == 1
        assert stats["TCB"]["won"] == 1

    def test_multiple_days(self):
        records = [
            {"evaluations": [{"ticker": "FPT", "won": True}]},
            {"evaluations": [{"ticker": "FPT", "won": False}]},
            {"evaluations": [{"ticker": "FPT", "won": True}]},
        ]
        stats = _calc_ticker_stats(records, 7)
        assert stats["FPT"]["total"] == 3
        assert stats["FPT"]["won"] == 2

    def test_rolling_window(self):
        """Only last N records are counted."""
        records = [
            {"evaluations": [{"ticker": "VHM", "won": True}]},  # excluded
            {"evaluations": [{"ticker": "VHM", "won": False}]},  # included
            {"evaluations": [{"ticker": "VHM", "won": True}]},  # included
        ]
        stats = _calc_ticker_stats(records, 2)
        assert stats["VHM"]["total"] == 2
        assert stats["VHM"]["won"] == 1

    def test_empty_records(self):
        stats = _calc_ticker_stats([], 7)
        assert stats == {}

    def test_missing_ticker(self):
        """Evaluations without ticker are skipped."""
        records = [
            {
                "evaluations": [
                    {"ticker": "VHM", "won": True},
                    {"won": True},  # no ticker
                    {"ticker": None, "won": True},  # None ticker
                ]
            }
        ]
        stats = _calc_ticker_stats(records, 7)
        assert len(stats) == 1
        assert stats["VHM"]["total"] == 1

    def test_won_false_and_missing(self):
        """won=False counts as total but not won; missing won (None) = EXCLUDED, skipped."""
        records = [
            {
                "evaluations": [
                    {"ticker": "SSI", "won": False},
                    {"ticker": "SSI"},  # no won field → won is None → EXCLUDED, skipped
                ]
            }
        ]
        stats = _calc_ticker_stats(records, 7)
        assert stats["SSI"]["total"] == 1  # only won=False counts; None-won is EXCLUDED
        assert stats["SSI"]["won"] == 0


# ---------------------------------------------------------------------------
# _calc_sector_stats
# ---------------------------------------------------------------------------


class TestCalcSectorStats:
    """Aggregate ticker stats into sector stats using a sector map."""

    def test_basic_aggregation(self):
        ticker_stats = {
            "VHM": {"total": 5, "won": 3},
            "NLG": {"total": 3, "won": 1},
            "TCB": {"total": 4, "won": 2},
        }
        sector_map = {
            "VHM": "real_estate",
            "NLG": "real_estate",
            "TCB": "banking",
        }
        stats = _calc_sector_stats(ticker_stats, sector_map)
        assert stats["real_estate"]["total"] == 8  # 5+3
        assert stats["real_estate"]["won"] == 4  # 3+1
        assert stats["banking"]["total"] == 4
        assert stats["banking"]["won"] == 2

    def test_unmapped_ticker_skipped(self):
        """Tickers not in sector_map don't appear in sector stats."""
        ticker_stats = {
            "VHM": {"total": 5, "won": 3},
            "XYZ": {"total": 2, "won": 1},  # not in map
        }
        sector_map = {"VHM": "real_estate"}
        stats = _calc_sector_stats(ticker_stats, sector_map)
        assert "real_estate" in stats
        assert len(stats) == 1  # XYZ excluded

    def test_empty_ticker_stats(self):
        stats = _calc_sector_stats({}, {"VHM": "real_estate"})
        assert stats == {}

    def test_empty_sector_map(self):
        ticker_stats = {"VHM": {"total": 5, "won": 3}}
        stats = _calc_sector_stats(ticker_stats, {})
        assert stats == {}

    def test_single_ticker_sector(self):
        ticker_stats = {"FPT": {"total": 10, "won": 7}}
        sector_map = {"FPT": "technology"}
        stats = _calc_sector_stats(ticker_stats, sector_map)
        assert stats["technology"]["total"] == 10
        assert stats["technology"]["won"] == 7


# ---------------------------------------------------------------------------
# Normalization logic (inline in insert_learnings.py)
# ---------------------------------------------------------------------------


class TestNormalization:
    """Verify normalize_rate() from shared.neon.insert_learnings."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0.50, 0.50),  # already 0-1 → unchanged
            (0.0, 0.0),  # zero → unchanged
            (1.0, 1.0),  # edge: exactly 1.0 → unchanged
            (50.0, 0.50),  # 0-100 scale → normalized
            (100.0, 1.0),  # 100% → 1.0
            (33.33, 0.3333),  # fractional percentage
            (1.01, 0.0101),  # just above 1.0 → normalized
        ],
    )
    def test_normalize(self, raw, expected):
        from shared.neon.insert_learnings import normalize_rate

        assert normalize_rate(raw) == pytest.approx(expected, abs=1e-4)

    def test_none_passthrough(self):
        from shared.neon.insert_learnings import normalize_rate

        assert normalize_rate(None) is None
