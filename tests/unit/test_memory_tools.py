"""Unit tests for memory tool helpers — similar days interpretation."""

import logging

from agents.tools.memory import _interpret_similar_days


class TestInterpretSimilarDays:
    def test_empty_days_returns_no_data(self):
        result = _interpret_similar_days([])
        assert "No historical data" in result

    def test_all_na_win_rates_returns_cautious(self):
        days = [
            {"win_rate": "N/A", "insight": "test"},
            {"win_rate": "N/A"},
            {"win_rate": "N/A"},
        ]
        result = _interpret_similar_days(days)
        assert "INSUFFICIENT DATA" in result
        assert "CAUTIOUS" in result

    def test_valid_win_rates_favorable(self):
        days = [
            {"win_rate": "70%"},
            {"win_rate": "65%"},
        ]
        result = _interpret_similar_days(days)
        assert "favorable" in result
        assert "INSUFFICIENT" not in result

    def test_valid_win_rates_challenging(self):
        days = [
            {"win_rate": "30%"},
            {"win_rate": "25%"},
        ]
        result = _interpret_similar_days(days)
        assert "challenging" in result

    def test_mixed_valid_and_na_uses_valid_only(self):
        days = [
            {"win_rate": "60%"},
            {"win_rate": "N/A"},
            {"win_rate": "70%"},
        ]
        result = _interpret_similar_days(days)
        assert "favorable" in result  # avg 65% >= 0.6
        assert "INSUFFICIENT" not in result

    def test_corrupt_win_rate_logs_warning(self, caplog):
        days = [{"win_rate": "not_a_number"}]
        with caplog.at_level(logging.WARNING):
            result = _interpret_similar_days(days)
        assert "Corrupt win_rate" in caplog.text
        assert "INSUFFICIENT DATA" in result  # falls through to else

    def test_insights_included(self):
        days = [
            {"win_rate": "50%", "insight": "Watch oil prices"},
        ]
        result = _interpret_similar_days(days)
        assert "Watch oil prices" in result
