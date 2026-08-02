"""Belief aggregation: apply_base_rate_anchor (pure Python, no I/O)."""

import pytest

from agents.belief_aggregation import apply_base_rate_anchor
from agents.belief_models import BASE_RATE_BEAR, BASE_RATE_BULL, BASE_RATE_NEUTRAL


class TestApplyBaseRateAnchor:
    def test_extreme_bullish_prediction_pulled_toward_center(self):
        beliefs = [
            {
                "agent_key": "analyst_a",
                "bull_probability": 0.90,
                "base_probability": 0.07,
                "bear_probability": 0.03,
                "direction": "BULLISH",
            }
        ]

        result = apply_base_rate_anchor(beliefs)

        anchored_bull = result[0]["bull_probability"]
        assert anchored_bull == pytest.approx(0.834, abs=1e-4)
        assert anchored_bull < 0.90

    def test_base_rate_anchor_with_default_weight(self):
        beliefs = [
            {
                "agent_key": "analyst_a",
                "bull_probability": 0.60,
                "base_probability": 0.30,
                "bear_probability": 0.10,
                "direction": "BULLISH",
            }
        ]

        result = apply_base_rate_anchor(beliefs)

        expected_bull = round(0.9 * 0.60 + 0.1 * BASE_RATE_BULL, 4)
        expected_base = round(0.9 * 0.30 + 0.1 * BASE_RATE_NEUTRAL, 4)
        expected_bear = round(0.9 * 0.10 + 0.1 * BASE_RATE_BEAR, 4)

        assert result[0]["bull_probability"] == pytest.approx(expected_bull, abs=1e-4)
        assert result[0]["base_probability"] == pytest.approx(expected_base, abs=1e-4)
        assert result[0]["bear_probability"] == pytest.approx(expected_bear, abs=1e-4)

    def test_custom_base_rates_applied(self):
        beliefs = [
            {
                "agent_key": "analyst_a",
                "bull_probability": 0.50,
                "base_probability": 0.30,
                "bear_probability": 0.20,
                "direction": "BULLISH",
            }
        ]
        custom_rates = {"BULLISH": 0.50, "NEUTRAL": 0.30, "BEARISH": 0.20}

        result = apply_base_rate_anchor(beliefs, base_rates=custom_rates)

        expected_bull = round(0.9 * 0.50 + 0.1 * 0.50, 4)
        assert result[0]["bull_probability"] == pytest.approx(expected_bull, abs=1e-4)

    def test_anchor_weight_zero_leaves_probabilities_unchanged(self):
        original_bull = 0.75
        original_base = 0.15
        original_bear = 0.10
        beliefs = [
            {
                "agent_key": "analyst_a",
                "bull_probability": original_bull,
                "base_probability": original_base,
                "bear_probability": original_bear,
                "direction": "BULLISH",
            }
        ]

        result = apply_base_rate_anchor(beliefs, anchor_weight=0.0)

        assert result[0]["bull_probability"] == pytest.approx(original_bull, abs=1e-4)
        assert result[0]["base_probability"] == pytest.approx(original_base, abs=1e-4)
        assert result[0]["bear_probability"] == pytest.approx(original_bear, abs=1e-4)

    def test_probabilities_sum_to_one_after_anchoring(self):
        beliefs = [
            {
                "agent_key": "analyst_a",
                "bull_probability": 0.50,
                "base_probability": 0.30,
                "bear_probability": 0.20,
                "direction": "BULLISH",
            }
        ]

        result = apply_base_rate_anchor(beliefs)

        total = (
            result[0]["bull_probability"]
            + result[0]["base_probability"]
            + result[0]["bear_probability"]
        )
        assert total == pytest.approx(1.0, abs=1e-3)

    def test_modifies_beliefs_in_place_and_returns_them(self):
        beliefs = [
            {
                "agent_key": "analyst_a",
                "bull_probability": 0.60,
                "base_probability": 0.30,
                "bear_probability": 0.10,
                "direction": "BULLISH",
            }
        ]
        original_list_id = id(beliefs)

        result = apply_base_rate_anchor(beliefs)

        assert id(result) == original_list_id
        assert beliefs[0]["bull_probability"] != 0.60

    def test_multiple_beliefs_all_anchored(self):
        beliefs = [
            {
                "agent_key": "analyst_a",
                "bull_probability": 0.80,
                "base_probability": 0.15,
                "bear_probability": 0.05,
                "direction": "BULLISH",
            },
            {
                "agent_key": "analyst_b",
                "bull_probability": 0.10,
                "base_probability": 0.20,
                "bear_probability": 0.70,
                "direction": "BEARISH",
            },
        ]

        result = apply_base_rate_anchor(beliefs)

        assert result[0]["bull_probability"] < 0.80
        assert result[1]["bull_probability"] > 0.10

    def test_probabilities_rounded_to_four_decimal_places(self):
        beliefs = [
            {
                "agent_key": "analyst_a",
                "bull_probability": 0.333,
                "base_probability": 0.334,
                "bear_probability": 0.333,
                "direction": "NEUTRAL",
            }
        ]

        result = apply_base_rate_anchor(beliefs)

        for key in ("bull_probability", "base_probability", "bear_probability"):
            value = result[0][key]
            assert round(value, 4) == value, f"{key} not rounded to 4 decimal places"
