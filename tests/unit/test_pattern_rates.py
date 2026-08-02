"""Tests for deterministic pattern extraction logic."""

from agents.retro.patterns import (
    _build_action_patterns,
    _calc_sector_stats,
    _calc_ticker_stats,
    _classify_sector_bias,
    calc_action_stats,
    extract_patterns,
)


class TestCalcActionStats:
    """Calculate per-action win/total from daily records."""

    def test_basic_counts(self):
        records = [
            {
                "evaluations": [
                    {"recommendation": "BUY", "won": True},
                    {"recommendation": "BUY", "won": False},
                    {"recommendation": "AVOID", "won": True},
                ]
            }
        ]
        stats = calc_action_stats(records, 7)
        assert stats["BUY"]["total"] == 2
        assert stats["BUY"]["won"] == 1
        assert stats["AVOID"]["total"] == 1
        assert stats["AVOID"]["won"] == 1

    def test_rolling_window(self):
        """Only last N records are counted."""
        records = [
            {"evaluations": [{"recommendation": "BUY", "won": True}]},
            {"evaluations": [{"recommendation": "BUY", "won": False}]},
            {"evaluations": [{"recommendation": "BUY", "won": True}]},
        ]
        stats = calc_action_stats(records, 2)
        assert stats["BUY"]["total"] == 2
        assert stats["BUY"]["won"] == 1

    def test_empty_records(self):
        stats = calc_action_stats([], 7)
        assert stats == {}


class TestCalcTickerStats:
    def test_basic(self):
        records = [
            {
                "evaluations": [
                    {"ticker": "FPT", "won": True},
                    {"ticker": "FPT", "won": False},
                    {"ticker": "VHM", "won": True},
                ]
            }
        ]
        stats = _calc_ticker_stats(records, 7)
        assert stats["FPT"] == {"total": 2, "won": 1}
        assert stats["VHM"] == {"total": 1, "won": 1}

    def test_no_ticker(self):
        records = [{"evaluations": [{"won": True}]}]
        stats = _calc_ticker_stats(records, 7)
        assert stats == {}


class TestCalcSectorStats:
    def test_aggregation(self):
        ticker_stats = {
            "FPT": {"total": 3, "won": 2},
            "VNG": {"total": 2, "won": 1},
            "VHM": {"total": 4, "won": 1},
        }
        sector_map = {"FPT": "Technology", "VNG": "Technology", "VHM": "Real Estate"}
        stats = _calc_sector_stats(ticker_stats, sector_map)
        assert stats["Technology"] == {"total": 5, "won": 3}
        assert stats["Real Estate"] == {"total": 4, "won": 1}

    def test_unmapped_ticker(self):
        ticker_stats = {"XYZ": {"total": 3, "won": 2}}
        stats = _calc_sector_stats(ticker_stats, {})
        assert stats == {}


class TestClassifySectorBias:
    def test_bullish(self):
        assert _classify_sector_bias(0.6) == "bullish"
        assert _classify_sector_bias(0.8) == "bullish"

    def test_bearish(self):
        assert _classify_sector_bias(0.4) == "bearish"
        assert _classify_sector_bias(0.1) == "bearish"

    def test_neutral(self):
        assert _classify_sector_bias(0.5) == "neutral"
        assert _classify_sector_bias(0.41) == "neutral"
        assert _classify_sector_bias(0.59) == "neutral"


class TestBuildActionPatterns:
    def test_splits_by_threshold(self):
        action_stats = {
            "BUY": {"total": 10, "won": 7},  # 70% → winning
            "HOLD": {"total": 5, "won": 1},  # 20% → losing
        }
        winning, losing = _build_action_patterns(action_stats, None, {})
        assert len(winning) == 1
        assert len(losing) == 1
        assert winning[0]["win_rate"] == 0.7
        assert losing[0]["win_rate"] == 0.2

    def test_filters_by_sample_size(self):
        action_stats = {
            "BUY": {"total": 3, "won": 3},  # sample < 5 → excluded
            "HOLD": {"total": 5, "won": 4},  # sample >= 5 → included
        }
        winning, losing = _build_action_patterns(action_stats, None, {})
        assert len(winning) == 1
        assert winning[0]["sample_size"] == 5

    def test_actionable_rule_template(self):
        action_stats = {"BUY": {"total": 10, "won": 8}}
        winning, _ = _build_action_patterns(action_stats, None, {})
        assert "BUY" in winning[0]["actionable_rule"]
        assert "80%" in winning[0]["actionable_rule"]

    def test_avoid_rule_template(self):
        action_stats = {"EXIT": {"total": 10, "won": 3}}
        _, losing = _build_action_patterns(action_stats, None, {})
        assert "EXIT" in losing[0]["avoid_rule"]
        assert "70%" in losing[0]["avoid_rule"]

    def test_includes_top_sector(self):
        action_stats = {"BUY": {"total": 5, "won": 4}}
        ticker_stats = {"FPT": {"total": 3, "won": 3}}
        sector_map = {"FPT": "Technology"}
        winning, _ = _build_action_patterns(action_stats, sector_map, ticker_stats)
        assert "Technology" in winning[0]["actionable_rule"]


class TestExtractPatterns:
    async def test_empty_records(self):
        result = await extract_patterns([], 7)
        assert result == {
            "winning_patterns": [],
            "losing_patterns": [],
            "sector_insights": [],
            "ticker_insights": [],
            "actionable_rules": [],
            "strategy_insights": [],
            "calibration_insights": {},
        }

    async def test_none_records(self):
        result = await extract_patterns(None, 7)
        assert result["winning_patterns"] == []

    async def test_full_pipeline(self):
        records = [
            {
                "evaluations": [
                    {"ticker": "FPT", "recommendation": "BUY", "won": True},
                    {"ticker": "FPT", "recommendation": "BUY", "won": True},
                    {"ticker": "FPT", "recommendation": "BUY", "won": True},
                    {"ticker": "FPT", "recommendation": "BUY", "won": True},
                    {"ticker": "FPT", "recommendation": "BUY", "won": True},
                    {"ticker": "VHM", "recommendation": "BUY", "won": False},
                    {"ticker": "VHM", "recommendation": "BUY", "won": False},
                    {"ticker": "VHM", "recommendation": "HOLD", "won": False},
                    {"ticker": "VHM", "recommendation": "HOLD", "won": False},
                    {"ticker": "VHM", "recommendation": "HOLD", "won": False},
                    {"ticker": "VHM", "recommendation": "HOLD", "won": False},
                    {"ticker": "VHM", "recommendation": "HOLD", "won": False},
                ]
            }
        ]
        sector_map = {"FPT": "Technology", "VHM": "Real Estate"}
        result = await extract_patterns(records, 7, sector_map)

        # BUY: 5/7 = 71% → winning (>= _MIN_SAMPLE_SIZE=5)
        assert len(result["winning_patterns"]) == 1
        assert result["winning_patterns"][0]["win_rate"] == 0.71

        # HOLD: 0/5 = 0% → losing (>= _MIN_SAMPLE_SIZE=5)
        assert len(result["losing_patterns"]) == 1
        assert result["losing_patterns"][0]["win_rate"] == 0.0

        # Sector insights (both >= _MIN_SAMPLE_SIZE=5)
        sectors = {s["sector"]: s for s in result["sector_insights"]}
        assert sectors["Technology"]["bias"] == "bullish"  # 5/5 = 100%
        assert sectors["Real Estate"]["bias"] == "bearish"  # 0/7 = 0%

        # Ticker insights (both >= _MIN_SAMPLE_SIZE=5)
        tickers = {t["ticker"]: t for t in result["ticker_insights"]}
        assert tickers["FPT"]["recent_accuracy"] == 1.0
        assert tickers["VHM"]["recent_accuracy"] == 0.0
