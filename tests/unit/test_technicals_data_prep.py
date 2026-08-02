"""Unit tests for data/technicals.py: numpy sanitisation + range/level helpers."""

import numpy as np
import pandas as pd

from data.technicals import (
    _sanitize_numpy,
    calculate_range_levels,
    find_nearest_levels,
)


class TestSanitizeNumpy:
    """Tests for _sanitize_numpy helper."""

    def test_float64(self):
        assert _sanitize_numpy(np.float64(3.14)) == 3.14
        assert type(_sanitize_numpy(np.float64(3.14))) is float

    def test_int64(self):
        assert _sanitize_numpy(np.int64(42)) == 42
        assert type(_sanitize_numpy(np.int64(42))) is int

    def test_bool_(self):
        assert _sanitize_numpy(np.bool_(True)) is True
        assert type(_sanitize_numpy(np.bool_(True))) is bool

    def test_nested_dict(self):
        data = {
            "rsi": np.float64(45.2),
            "ma20": np.float64(102.5),
            "closed_at_low": np.bool_(False),
            "volume": np.int64(1000000),
            "name": "VHM",
        }
        result = _sanitize_numpy(data)
        assert type(result["rsi"]) is float
        assert type(result["ma20"]) is float
        assert type(result["closed_at_low"]) is bool
        assert type(result["volume"]) is int
        assert type(result["name"]) is str

    def test_nested_list_in_dict(self):
        data = {"values": [np.float64(1.0), np.float64(2.0)]}
        result = _sanitize_numpy(data)
        assert all(type(v) is float for v in result["values"])

    def test_none_passthrough(self):
        assert _sanitize_numpy(None) is None

    def test_plain_types_unchanged(self):
        assert _sanitize_numpy(42) == 42
        assert _sanitize_numpy(3.14) == 3.14
        assert _sanitize_numpy("hello") == "hello"

    def test_ndarray_to_list(self):
        arr = np.array([1.0, 2.0, 3.0])
        result = _sanitize_numpy(arr)
        assert isinstance(result, list)
        assert result == [1.0, 2.0, 3.0]


class TestCalculateRangeLevels:
    """Tests for calculate_range_levels function."""

    def test_calculates_20d_high_low(self):
        df = pd.DataFrame(
            {
                "high": list(range(100, 130)),
                "low": list(range(90, 120)),
            }
        )

        result = calculate_range_levels(df, window=20)

        assert result["range_20d_high"] == 129.0
        assert result["range_20d_low"] == 100.0

    def test_empty_on_insufficient_data(self):
        df = pd.DataFrame({"high": [10, 11, 12], "low": [9, 10, 11]})

        result = calculate_range_levels(df, window=20)

        assert result == {}


class TestFindNearestLevels:
    """Tests for find_nearest_levels function."""

    def test_finds_nearest_support(self):
        result = find_nearest_levels(
            price=100,
            ma20=95,
            ma50=90,
            swing_high=110,
            swing_low=85,
            range_high=115,
            range_low=80,
        )
        assert result["nearest_support"] == 95

    def test_finds_nearest_resistance(self):
        result = find_nearest_levels(
            price=100,
            ma20=95,
            ma50=90,
            swing_high=105,
            swing_low=85,
            range_high=115,
            range_low=80,
        )
        assert result["nearest_resistance"] == 105

    def test_handles_none_values(self):
        result = find_nearest_levels(
            price=100,
            ma20=None,
            ma50=None,
            swing_high=105,
            swing_low=None,
            range_high=None,
            range_low=95,
        )
        assert result["nearest_support"] == 95
        assert result["nearest_resistance"] == 105

    def test_no_support_when_price_lowest(self):
        result = find_nearest_levels(
            price=50,
            ma20=100,
            ma50=90,
            swing_high=110,
            swing_low=60,
            range_high=115,
            range_low=70,
        )
        assert "nearest_support" not in result

    def test_no_resistance_when_price_highest(self):
        result = find_nearest_levels(
            price=150,
            ma20=100,
            ma50=90,
            swing_high=110,
            swing_low=60,
            range_high=115,
            range_low=70,
        )
        assert "nearest_resistance" not in result
