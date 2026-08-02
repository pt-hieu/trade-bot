"""Unit tests for belief models + belief aggregation."""

import logging

import pytest
from pydantic import ValidationError

from agents.belief_aggregation import apply_base_rate_anchor, weighted_aggregate_beliefs
from agents.belief_models import (
    BASE_RATE_BEAR,
    BASE_RATE_BULL,
    BASE_RATE_NEUTRAL,
    LAZY_NEUTRAL_BASE_THRESHOLD,
    LAZY_NEUTRAL_CONVICTION_THRESHOLD,
    MIN_DIRECTIONAL_PROBABILITY,
    UNREALISTIC_PRICE_TARGET_THRESHOLD,
    AggregatedBelief,
    TickerBelief,
)


def _make_belief(**overrides) -> TickerBelief:
    defaults = {
        "ticker": "FPT",
        "belief_narrative": "Test belief",
        "direction": "BULLISH",
        "bull_probability": 0.55,
        "base_probability": 0.30,
        "bear_probability": 0.15,
        "price_target_vnd": 120000,
        "timeframe_days": 5,
        "conviction": 0.65,
        "belief_status": "NEW",
    }
    defaults.update(overrides)
    return TickerBelief(**defaults)


class TestProbabilityNormalization:
    def test_already_normalized(self):
        belief = _make_belief(bull_probability=0.55, base_probability=0.30, bear_probability=0.15)
        total = belief.bull_probability + belief.base_probability + belief.bear_probability
        assert abs(total - 1.0) < 0.001

    def test_slight_overshoot_renormalized(self):
        belief = _make_belief(bull_probability=0.60, base_probability=0.35, bear_probability=0.20)
        total = belief.bull_probability + belief.base_probability + belief.bear_probability
        assert abs(total - 1.0) < 0.001

    def test_slight_undershoot_renormalized(self):
        belief = _make_belief(bull_probability=0.40, base_probability=0.25, bear_probability=0.15)
        total = belief.bull_probability + belief.base_probability + belief.bear_probability
        assert abs(total - 1.0) < 0.001

    def test_wildly_off_falls_back_to_base_rates(self):
        belief = _make_belief(bull_probability=0.1, base_probability=0.1, bear_probability=0.1)
        # Sum = 0.3, below 0.5 threshold
        assert belief.bull_probability == BASE_RATE_BULL
        assert belief.base_probability == BASE_RATE_NEUTRAL
        assert belief.bear_probability == BASE_RATE_BEAR

    def test_extremely_high_falls_back(self):
        belief = _make_belief(bull_probability=0.8, base_probability=0.8, bear_probability=0.8)
        # Sum = 2.4, above 1.5 threshold
        assert belief.bull_probability == BASE_RATE_BULL
        assert belief.base_probability == BASE_RATE_NEUTRAL
        assert belief.bear_probability == BASE_RATE_BEAR

    def test_zero_probabilities_fall_back(self):
        belief = _make_belief(bull_probability=0.0, base_probability=0.0, bear_probability=0.0)
        assert belief.bull_probability == BASE_RATE_BULL

    def test_percentage_scale_rescued(self):
        """LLM outputs 45/35/20 (percentages) → rescued to 0.45/0.35/0.20."""
        belief = _make_belief(bull_probability=45, base_probability=35, bear_probability=20)
        total = belief.bull_probability + belief.base_probability + belief.bear_probability
        assert abs(total - 1.0) < 0.001
        assert abs(belief.bull_probability - 0.45) < 0.01
        assert abs(belief.base_probability - 0.35) < 0.01
        assert abs(belief.bear_probability - 0.20) < 0.01

    def test_percentage_scale_uneven_rescued(self):
        """LLM outputs 50/30/10 (sum=90, percentages) → rescued and renormalized."""
        belief = _make_belief(bull_probability=50, base_probability=30, bear_probability=10)
        total = belief.bull_probability + belief.base_probability + belief.bear_probability
        assert abs(total - 1.0) < 0.001
        # After /100: 0.50/0.30/0.10 = 0.90, then renormalized to 1.0
        assert belief.bull_probability > 0.5

    def test_sum_2_4_still_falls_back(self):
        """Sum=2.4 is NOT in [50,150] range → still falls back to base rates."""
        belief = _make_belief(bull_probability=0.8, base_probability=0.8, bear_probability=0.8)
        assert belief.bull_probability == BASE_RATE_BULL
        assert belief.base_probability == BASE_RATE_NEUTRAL
        assert belief.bear_probability == BASE_RATE_BEAR


class TestConvictionClamping:
    def test_conviction_clamped_to_one(self):
        belief = _make_belief(conviction=1.5)
        assert belief.conviction == 1.0

    def test_conviction_clamped_to_zero(self):
        belief = _make_belief(conviction=-0.3)
        assert belief.conviction == 0.0

    def test_conviction_normal_range(self):
        belief = _make_belief(conviction=0.65)
        assert belief.conviction == 0.65


class TestBeliefStatus:
    def test_valid_statuses(self):
        for status in ["NEW", "REAFFIRMED", "UPDATED", "REVERSED"]:
            belief = _make_belief(belief_status=status)
            assert belief.belief_status == status

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            _make_belief(belief_status="INVALID")


class TestAggregatedBelief:
    def test_aggregated_belief_normalization(self):
        belief = AggregatedBelief(
            ticker="FPT",
            belief_narrative="Committee view",
            direction="BULLISH",
            bull_probability=0.60,
            base_probability=0.35,
            bear_probability=0.20,
            price_target_vnd=120000,
            conviction=0.7,
        )
        total = belief.bull_probability + belief.base_probability + belief.bear_probability
        assert abs(total - 1.0) < 0.001

    def test_aggregated_belief_with_disagreement(self):
        belief = AggregatedBelief(
            ticker="VHM",
            belief_narrative="Split view",
            direction="NEUTRAL",
            bull_probability=0.33,
            base_probability=0.34,
            bear_probability=0.33,
            price_target_vnd=50000,
            conviction=0.3,
            disagreement_note="Technical says BULLISH, Value says BEARISH",
        )
        assert belief.disagreement_note is not None

    def test_aggregated_belief_percentage_rescued(self):
        """Aggregator outputs percentages → rescued to decimals."""
        belief = AggregatedBelief(
            ticker="TCB",
            belief_narrative="Committee view",
            direction="BULLISH",
            bull_probability=45,
            base_probability=35,
            bear_probability=20,
            price_target_vnd=31000,
            conviction=0.7,
        )
        total = belief.bull_probability + belief.base_probability + belief.bear_probability
        assert abs(total - 1.0) < 0.001
        assert abs(belief.bull_probability - 0.45) < 0.01


class TestPriceTargetValidation:
    def test_zero_price_target_rejected(self):
        """price_target_vnd=0 should be rejected by ge=1 validation."""
        with pytest.raises(ValidationError):
            _make_belief(price_target_vnd=0)

    def test_negative_price_target_rejected(self):
        """Negative price target should be rejected."""
        with pytest.raises(ValidationError):
            _make_belief(price_target_vnd=-1000)

    def test_valid_price_target_accepted(self):
        belief = _make_belief(price_target_vnd=120000)
        assert belief.price_target_vnd == 120000

    def test_small_valid_price_target_accepted(self):
        """Penny stocks can have low prices (e.g., 1000 VND)."""
        belief = _make_belief(price_target_vnd=1000)
        assert belief.price_target_vnd == 1000

    def test_aggregated_belief_zero_target_rejected(self):
        """AggregatedBelief also rejects price_target_vnd=0."""
        with pytest.raises(ValidationError):
            AggregatedBelief(
                ticker="FPT",
                belief_narrative="Test",
                direction="BULLISH",
                bull_probability=0.55,
                base_probability=0.30,
                bear_probability=0.15,
                price_target_vnd=0,
                conviction=0.7,
            )


class TestLazyNeutralWarning:
    def test_lazy_neutral_logged(self, caplog):
        """base_probability > 0.75 + conviction < 0.5 triggers lazy NEUTRAL warning."""

        with caplog.at_level(logging.WARNING):
            _make_belief(
                bull_probability=0.12,
                base_probability=0.78,
                bear_probability=0.10,
                conviction=0.3,
            )
        assert "Lazy NEUTRAL" in caplog.text

    def test_genuine_neutral_no_warning(self, caplog):
        """High conviction NEUTRAL is not lazy — no warning even at high base."""

        with caplog.at_level(logging.WARNING):
            _make_belief(
                bull_probability=0.10,
                base_probability=0.80,
                bear_probability=0.10,
                conviction=0.7,
            )
        assert "Lazy NEUTRAL" not in caplog.text

    def test_moderate_neutral_no_warning(self, caplog):
        """base_probability=0.65 is the correct prediction — never flag as lazy."""

        with caplog.at_level(logging.WARNING):
            _make_belief(
                bull_probability=0.20,
                base_probability=0.65,
                bear_probability=0.15,
                conviction=0.4,
            )
        assert "Lazy NEUTRAL" not in caplog.text

    def test_directional_belief_no_warning(self, caplog):
        """Strong directional belief with low base — no warning."""

        with caplog.at_level(logging.WARNING):
            _make_belief(
                bull_probability=0.55,
                base_probability=0.30,
                bear_probability=0.15,
                conviction=0.3,
            )
        assert "Lazy NEUTRAL" not in caplog.text


class TestMinDirectionalProbability:
    """Tests for MIN_DIRECTIONAL_PROBABILITY gate in direction derivation.

    BULLISH/BEARISH require top_prob >= 0.40. Near-uniform distributions
    (common after base rate anchoring) resolve to NEUTRAL.
    """

    def _make_beliefs(self, bull, base, bear, conviction=0.6):
        return [
            {
                "agent_key": "test_agent",
                "conviction": conviction,
                "bull_probability": bull,
                "base_probability": base,
                "bear_probability": bear,
                "direction": "BULLISH"
                if bull > base and bull > bear
                else ("BEARISH" if bear > base and bear > bull else "NEUTRAL"),
            }
        ]

    def test_bullish_above_min_prob(self):
        """BULLISH at 0.45 >= 0.40 → keeps BULLISH."""
        result = weighted_aggregate_beliefs(self._make_beliefs(bull=0.45, base=0.30, bear=0.25))
        assert result["direction"] == "BULLISH"

    def test_bullish_below_min_prob_becomes_neutral(self):
        """BULLISH at 0.38 < 0.40 → gated to NEUTRAL."""
        result = weighted_aggregate_beliefs(self._make_beliefs(bull=0.38, base=0.32, bear=0.30))
        assert result["direction"] == "NEUTRAL"

    def test_neutral_top_stays_neutral(self):
        """NEUTRAL is top → no gate needed, stays NEUTRAL."""
        result = weighted_aggregate_beliefs(self._make_beliefs(bull=0.30, base=0.45, bear=0.25))
        assert result["direction"] == "NEUTRAL"

    def test_uniform_distribution_neutral(self):
        """Near-uniform (0.34/0.36/0.30) → NEUTRAL (top is NEUTRAL at 0.36 < 0.40, but NEUTRAL stays)."""
        result = weighted_aggregate_beliefs(self._make_beliefs(bull=0.34, base=0.36, bear=0.30))
        assert result["direction"] == "NEUTRAL"

    def test_bearish_above_min_prob(self):
        """BEARISH at 0.50 >= 0.40 → keeps BEARISH."""
        result = weighted_aggregate_beliefs(self._make_beliefs(bull=0.20, base=0.30, bear=0.50))
        assert result["direction"] == "BEARISH"

    def test_bearish_below_min_prob_becomes_neutral(self):
        """BEARISH at 0.38 < 0.40 → gated to NEUTRAL."""
        result = weighted_aggregate_beliefs(self._make_beliefs(bull=0.30, base=0.32, bear=0.38))
        assert result["direction"] == "NEUTRAL"

    def test_exactly_at_min_prob_keeps_direction(self):
        """BULLISH at exactly 0.40 → keeps BULLISH (>= gate, not >)."""
        from agents.belief_models import derive_direction_from_probabilities

        direction = derive_direction_from_probabilities(0.40, 0.35, 0.25)
        assert direction == "BULLISH"

    def test_just_below_min_prob_neutral(self):
        """BULLISH at 0.399 < 0.40 → NEUTRAL."""
        from agents.belief_models import derive_direction_from_probabilities

        direction = derive_direction_from_probabilities(0.399, 0.351, 0.25)
        assert direction == "NEUTRAL"

    def test_threshold_constants_exported(self):
        assert MIN_DIRECTIONAL_PROBABILITY == 0.40
        assert LAZY_NEUTRAL_BASE_THRESHOLD == 0.75
        assert LAZY_NEUTRAL_CONVICTION_THRESHOLD == 0.5
        assert UNREALISTIC_PRICE_TARGET_THRESHOLD == 1000


class TestBaseRateAnchoring:
    """Base rate anchor uses 10% weight to pull toward empirical distribution."""

    def test_default_anchor_weight_is_0_1(self):
        import inspect

        signature = inspect.signature(apply_base_rate_anchor)
        assert signature.parameters["anchor_weight"].default == 0.1

    def test_strong_bullish_stays_bullish_after_anchor(self):
        beliefs = [{"bull_probability": 0.70, "base_probability": 0.20, "bear_probability": 0.10}]
        result = apply_base_rate_anchor(beliefs)
        # 0.9 * 0.70 + 0.1 * 0.24 = 0.654 — still bullish
        assert result[0]["bull_probability"] > 0.60

    def test_neutral_pulled_toward_empirical(self):
        """With NEUTRAL base rate at 0.68, anchoring pulls base_probability UP."""
        beliefs = [{"bull_probability": 0.30, "base_probability": 0.40, "bear_probability": 0.30}]
        result = apply_base_rate_anchor(beliefs)
        # 0.9 * 0.40 + 0.1 * 0.68 = 0.428 — pulled toward correct rate
        assert result[0]["base_probability"] > 0.40

    def test_overconfident_bearish_reduced(self):
        """Anchoring reduces overconfident BEARISH (rate is only 8%)."""
        beliefs = [{"bull_probability": 0.20, "base_probability": 0.20, "bear_probability": 0.60}]
        result = apply_base_rate_anchor(beliefs)
        # 0.9 * 0.60 + 0.1 * 0.08 = 0.548 — pulled down
        assert result[0]["bear_probability"] < 0.60

    def test_probabilities_still_sum_to_one(self):
        beliefs = [{"bull_probability": 0.50, "base_probability": 0.30, "bear_probability": 0.20}]
        result = apply_base_rate_anchor(beliefs)
        total = (
            result[0]["bull_probability"]
            + result[0]["base_probability"]
            + result[0]["bear_probability"]
        )
        assert abs(total - 1.0) < 0.01
