"""Unit tests for recommendation_builder/validator — parsing."""

import pytest  # noqa: F401

from tests.unit._fixtures.recommendation_builder import _parse_alert_price


class TestParseAlertPrice:
    """Pure parsing — no external state."""

    @pytest.mark.parametrize(
        "input_value, expected",
        [
            ("93k", 93000),
            ("93,000", 93000),
            ("N/A", None),
            ("n/a", None),
            (None, None),
            (50000, 50000),
            (0, None),
            (-1, None),
            (50000.0, 50000),
            ("", None),
            ("1.5k", 1500),
            ("abc", None),
        ],
    )
    def test_parse(self, input_value, expected):
        assert _parse_alert_price(input_value) == expected


# ---------------------------------------------------------------------------
# build_structured_recommendations — builder tests
# ---------------------------------------------------------------------------
