"""
Unit tests for statistical analysis functions in scripts/data/technicals.py.

Tests for calculate_closed_at_low and calculate_volume_vs_avg functions.
"""

import pandas as pd

from data.technicals import (
    calculate_closed_at_low,
    calculate_volume_vs_avg,
)


class TestCalculateClosedAtLow:
    """Tests for calculate_closed_at_low function."""

    def test_close_at_exact_low(self):
        """Close at exact low should return True."""
        result = calculate_closed_at_low(high=100.0, low=90.0, close=90.0)
        assert result is True

    def test_close_at_bottom_10_percent(self):
        """Close within bottom 10% of range should return True."""
        # Range is 100-90=10, 10% of 10 = 1
        # Bottom 10% is 90-91, close at 90.5 should be True
        result = calculate_closed_at_low(high=100.0, low=90.0, close=90.5)
        assert result is True

    def test_close_at_exactly_10_percent_boundary(self):
        """Close at exactly 10% boundary should return True (<=)."""
        # Range is 100-90=10, 10% of 10 = 1
        # 10% boundary is at 91.0
        result = calculate_closed_at_low(high=100.0, low=90.0, close=91.0)
        assert result is True

    def test_close_above_10_percent(self):
        """Close above bottom 10% should return False."""
        # Range is 100-90=10, 10% of 10 = 1
        # Close at 91.1 is above 10% boundary
        result = calculate_closed_at_low(high=100.0, low=90.0, close=91.1)
        assert result is False

    def test_close_at_midpoint(self):
        """Close at midpoint should return False."""
        result = calculate_closed_at_low(high=100.0, low=90.0, close=95.0)
        assert result is False

    def test_close_at_high(self):
        """Close at high should return False."""
        result = calculate_closed_at_low(high=100.0, low=90.0, close=100.0)
        assert result is False

    def test_zero_range_returns_false(self):
        """Doji candle (zero range) should return False."""
        result = calculate_closed_at_low(high=100.0, low=100.0, close=100.0)
        assert result is False

    def test_very_small_range(self):
        """Very small range should still calculate correctly."""
        # Range = 0.1, 10% = 0.01
        result = calculate_closed_at_low(high=100.1, low=100.0, close=100.005)
        assert result is True

    def test_negative_prices(self):
        """Should handle negative prices (edge case)."""
        # Range is -90 to -100 = 10, bottom 10% would be -99 to -100
        result = calculate_closed_at_low(high=-90.0, low=-100.0, close=-99.5)
        assert result is True


class TestCalculateVolumeVsAvg:
    """Tests for calculate_volume_vs_avg function."""

    def test_average_volume(self):
        """Volume at average should return 1.0."""
        df = pd.DataFrame({"volume": [100] * 20})
        result = calculate_volume_vs_avg(df, window=20)
        assert result == 1.0

    def test_double_average_volume(self):
        """Volume at 2x average should return 2.0."""
        # 19 days at 100, last day at 200
        volumes = [100] * 19 + [200]
        df = pd.DataFrame({"volume": volumes})
        # Average of last 20 = (19*100 + 200) / 20 = 2100/20 = 105
        # Ratio = 200 / 105 = 1.90 (approx)
        result = calculate_volume_vs_avg(df, window=20)
        assert result == 1.9  # rounded to 2 decimals

    def test_half_average_volume(self):
        """Volume at half average should return ~0.5."""
        # 19 days at 200, last day at 100
        volumes = [200] * 19 + [100]
        df = pd.DataFrame({"volume": volumes})
        # Average = (19*200 + 100) / 20 = 195
        # Ratio = 100 / 195 = 0.51
        result = calculate_volume_vs_avg(df, window=20)
        assert result == 0.51

    def test_high_volume_spike(self):
        """High volume spike should return ratio > 1.5."""
        volumes = [100] * 19 + [500]  # 5x spike
        df = pd.DataFrame({"volume": volumes})
        # Average = (19*100 + 500) / 20 = 2400/20 = 120
        # Ratio = 500 / 120 = 4.17
        result = calculate_volume_vs_avg(df, window=20)
        assert result == 4.17

    def test_insufficient_data_returns_none(self):
        """Less than window size should return None."""
        df = pd.DataFrame({"volume": [100] * 10})
        result = calculate_volume_vs_avg(df, window=20)
        assert result is None

    def test_exactly_window_size(self):
        """Exactly window size should work — all same volume → ratio 1.0."""
        df = pd.DataFrame({"volume": [100] * 20})
        result = calculate_volume_vs_avg(df, window=20)
        assert result == 1.0

    def test_custom_window_size(self):
        """Custom window size should use specified period."""
        volumes = [100] * 9 + [200]  # 10 days
        df = pd.DataFrame({"volume": volumes})
        # With window=10: avg = (9*100 + 200) / 10 = 110
        # Ratio = 200 / 110 = 1.82
        result = calculate_volume_vs_avg(df, window=10)
        assert result == 1.82

    def test_zero_average_volume_returns_none(self):
        """Zero average volume should return None."""
        df = pd.DataFrame({"volume": [0] * 20})
        result = calculate_volume_vs_avg(df, window=20)
        assert result is None

    def test_large_dataset(self):
        """Should only use last N days for average."""
        # 100 days of data, window=20
        volumes = [50] * 80 + [100] * 20  # Old days at 50, recent at 100
        df = pd.DataFrame({"volume": volumes})
        # Should use last 20 days (all 100), so ratio = 1.0
        result = calculate_volume_vs_avg(df, window=20)
        assert result == 1.0

    def test_rounding_to_two_decimals(self):
        """Result should be rounded to 2 decimal places."""
        volumes = [100] * 19 + [333]
        df = pd.DataFrame({"volume": volumes})
        result = calculate_volume_vs_avg(df, window=20)
        # Should be rounded, not have many decimal places
        assert result == round(result, 2)
