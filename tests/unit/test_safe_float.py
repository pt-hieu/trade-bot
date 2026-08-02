"""Unit tests for shared.neon._utils.safe_float."""

from decimal import Decimal

from shared.neon._utils import safe_float


class TestSafeFloat:
    """safe_float must handle Decimal(0) without treating it as missing."""

    def test_decimal_zero_returns_zero(self):
        assert safe_float(Decimal("0.0")) == 0.0

    def test_decimal_zero_no_fractional(self):
        assert safe_float(Decimal("0")) == 0.0

    def test_none_returns_default_none(self):
        assert safe_float(None) is None

    def test_none_returns_custom_default(self):
        assert safe_float(None, default=0.5) == 0.5

    def test_positive_decimal(self):
        assert safe_float(Decimal("3.14")) == 3.14

    def test_negative_decimal(self):
        assert safe_float(Decimal("-1.5")) == -1.5

    def test_int_value(self):
        assert safe_float(42) == 42.0

    def test_float_value(self):
        assert safe_float(2.718) == 2.718

    def test_zero_int(self):
        assert safe_float(0) == 0.0

    def test_zero_float(self):
        assert safe_float(0.0) == 0.0

    def test_default_zero_with_none(self):
        assert safe_float(None, default=0) == 0

    def test_default_zero_with_decimal_zero(self):
        """Decimal(0) should return 0.0, not the default."""
        assert safe_float(Decimal("0"), default=99.0) == 0.0
