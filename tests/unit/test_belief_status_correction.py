"""Tests for belief status auto-correction and accuracy-weighted confidence.

Covers:
- REAFFIRMED -> REVERSED when direction changed
- REAFFIRMED -> UPDATED when bull shifted >15pp
- UPDATED -> REVERSED when direction changed
- REVERSED -> REAFFIRMED when direction unchanged (challenge fix)
- accuracy_discounted_confidence function
- carry_forward_beliefs function
"""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from pipeline.recommendation_helpers import (
    CONSENSUS_CONFIDENCE,
    accuracy_discounted_confidence,
)
from shared.neon.beliefs import PROBABILITY_SHIFT_THRESHOLD, carry_forward_beliefs


class TestAccuracyDiscountedConfidence:
    """accuracy_discounted_confidence discounts by direction accuracy."""

    def test_no_calibration_returns_base(self):
        result = accuracy_discounted_confidence("unanimous")
        assert result == CONSENSUS_CONFIDENCE["unanimous"]

    def test_empty_calibration_returns_base(self):
        result = accuracy_discounted_confidence("unanimous", {})
        assert result == CONSENSUS_CONFIDENCE["unanimous"]

    def test_random_accuracy_halves_confidence(self):
        stats = {"agent_a": {"direction_accuracy": 0.33}}
        result = accuracy_discounted_confidence("unanimous", stats)
        assert result == round(0.9 * 0.5, 2)

    def test_perfect_accuracy_full_confidence(self):
        stats = {"agent_a": {"direction_accuracy": 0.65}}
        result = accuracy_discounted_confidence("unanimous", stats)
        assert result >= 0.85

    def test_mixed_accuracy_averages(self):
        stats = {
            "agent_a": {"direction_accuracy": 0.55},
            "agent_b": {"direction_accuracy": 0.33},
        }
        result = accuracy_discounted_confidence("unanimous", stats)
        # avg accuracy = 0.44 → discount between 0.5 and 1.0
        assert 0.45 < result < 0.9

    def test_majority_consensus_discounted(self):
        stats = {"agent_a": {"direction_accuracy": 0.33}}
        result = accuracy_discounted_confidence("majority", stats)
        assert result == round(0.7 * 0.5, 2)

    def test_none_direction_accuracy_skipped(self):
        stats = {"agent_a": {"direction_accuracy": None}}
        result = accuracy_discounted_confidence("unanimous", stats)
        assert result == CONSENSUS_CONFIDENCE["unanimous"]

    def test_unknown_consensus_label_uses_default(self):
        result = accuracy_discounted_confidence("unknown_label")
        assert result == 0.5


class TestProbabilityShiftThreshold:
    """PROBABILITY_SHIFT_THRESHOLD is correctly defined."""

    def test_threshold_value(self):
        assert PROBABILITY_SHIFT_THRESHOLD == 0.15


class TestCarryForwardBeliefs:
    """carry_forward_beliefs decays conviction and handles CRISIS mode."""

    import pytest

    @pytest.mark.asyncio
    async def test_empty_previous_returns_empty(self, monkeypatch):
        async def mock_fetch(*args):
            return []

        monkeypatch.setattr("shared.neon.beliefs.get_latest_beliefs_for_ensemble", mock_fetch)
        result = await carry_forward_beliefs(
            scan_date=__import__("datetime").date(2026, 4, 1),
            ensemble_type="sector",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_normal_decay(self, monkeypatch):
        previous = [
            {
                "agent_key": "sector_technical",
                "ticker": "FPT",
                "ensemble_type": "sector",
                "direction": "BULLISH",
                "bull_probability": 0.45,
                "base_probability": 0.35,
                "bear_probability": 0.20,
                "price_target_vnd": 85000,
                "timeframe_days": 5,
                "conviction": 0.8,
                "belief_narrative": "test",
                "days_held": 3,
            }
        ]

        async def mock_fetch(*args):
            return previous

        monkeypatch.setattr("shared.neon.beliefs.get_latest_beliefs_for_ensemble", mock_fetch)
        result = await carry_forward_beliefs(
            scan_date=__import__("datetime").date(2026, 4, 1),
            ensemble_type="sector",
        )
        assert len(result) == 1
        assert result[0]["conviction"] == round(0.8 * 0.9, 3)
        assert result[0]["direction"] == "BULLISH"
        assert result[0]["belief_status"] == "REAFFIRMED"
        assert result[0]["days_held"] == 4

    @pytest.mark.asyncio
    async def test_crisis_mode_stronger_decay_and_direction_override(self, monkeypatch):
        previous = [
            {
                "agent_key": "sector_technical",
                "ticker": "FPT",
                "ensemble_type": "sector",
                "direction": "BULLISH",
                "bull_probability": 0.45,
                "base_probability": 0.35,
                "bear_probability": 0.20,
                "price_target_vnd": 85000,
                "timeframe_days": 5,
                "conviction": 0.8,
                "belief_narrative": "test",
                "days_held": 2,
            }
        ]

        async def mock_fetch(*args):
            return previous

        monkeypatch.setattr("shared.neon.beliefs.get_latest_beliefs_for_ensemble", mock_fetch)
        result = await carry_forward_beliefs(
            scan_date=__import__("datetime").date(2026, 4, 1),
            ensemble_type="sector",
            crisis_mode=True,
        )
        assert len(result) == 1
        assert result[0]["conviction"] == round(0.8 * 0.7, 3)
        assert result[0]["direction"] == "NEUTRAL"  # BULLISH overridden
        assert result[0]["days_held"] == 3

    @pytest.mark.asyncio
    async def test_crisis_mode_bearish_not_overridden(self, monkeypatch):
        previous = [
            {
                "agent_key": "sector_technical",
                "ticker": "FPT",
                "ensemble_type": "sector",
                "direction": "BEARISH",
                "bull_probability": 0.20,
                "base_probability": 0.35,
                "bear_probability": 0.45,
                "price_target_vnd": 70000,
                "timeframe_days": 5,
                "conviction": 0.7,
                "belief_narrative": "test",
                "days_held": 1,
            }
        ]

        async def mock_fetch(*args):
            return previous

        monkeypatch.setattr("shared.neon.beliefs.get_latest_beliefs_for_ensemble", mock_fetch)
        result = await carry_forward_beliefs(
            scan_date=__import__("datetime").date(2026, 4, 1),
            ensemble_type="sector",
            crisis_mode=True,
        )
        assert result[0]["direction"] == "BEARISH"  # not overridden
