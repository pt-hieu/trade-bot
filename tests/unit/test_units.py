"""Unit tests for shared/units.py — canonical conversion utilities."""

import pytest

from shared.units import rate_to_pct, thousands_to_vnd, vnd_to_thousands


class TestThousandsToVnd:
    @pytest.mark.parametrize(
        "thousands,expected_vnd",
        [
            (80.2, 80200),  # FPT ~80k
            (14.75, 14750),  # SHB ~14.75k
            (35.5, 35500),  # TCB ~35.5k
            (0.8, 800),  # Penny stock < 1k VND
            (0.0, 0),  # Zero
            (1200.5, 1200500),  # VNINDEX level
        ],
    )
    def test_conversion(self, thousands, expected_vnd):
        assert thousands_to_vnd(thousands) == expected_vnd

    def test_returns_int(self):
        result = thousands_to_vnd(35.123)
        assert isinstance(result, int)

    def test_rounding(self):
        # 35.1234 * 1000 = 35123.4 -> rounds to 35123
        assert thousands_to_vnd(35.1234) == 35123
        # 35.1236 * 1000 = 35123.6 -> rounds to 35124
        assert thousands_to_vnd(35.1236) == 35124

    def test_negative_price(self):
        assert thousands_to_vnd(-5.0) == -5000


class TestVndToThousands:
    @pytest.mark.parametrize(
        "vnd,expected_thousands",
        [
            (80200, 80.2),
            (14750, 14.75),
            (35500, 35.5),
            (800, 0.8),
            (0, 0.0),
        ],
    )
    def test_conversion(self, vnd, expected_thousands):
        assert vnd_to_thousands(vnd) == pytest.approx(expected_thousands)

    def test_returns_float(self):
        result = vnd_to_thousands(35000)
        assert isinstance(result, float)


class TestRateToPct:
    @pytest.mark.parametrize(
        "rate,expected_pct",
        [
            (0.2827, 28.27),  # FPT ROE
            (0.1601, 16.01),  # FPT net margin
            (0.005, 0.5),  # Small ROE (0.5%)
            (1.0, 100.0),  # 100% bounce rate
            (0.0, 0.0),  # Zero
            (-0.052, -5.2),  # Negative margin
            (0.0126, 1.26),  # Dividend yield
        ],
    )
    def test_conversion(self, rate, expected_pct):
        assert rate_to_pct(rate) == pytest.approx(expected_pct)

    def test_returns_float(self):
        result = rate_to_pct(0.5)
        assert isinstance(result, float)

    def test_precision_two_decimals(self):
        # 0.12345 * 100 = 12.345 -> rounds to 12.35
        assert rate_to_pct(0.12345) == 12.35
