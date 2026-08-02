"""Belief calibration: base rate anchoring (apply_base_rate_anchor)."""

from agents.belief_aggregation import FALLBACK_BASE_RATES, apply_base_rate_anchor


class TestBaseRateAnchoring:
    """Verify apply_base_rate_anchor uses correct empirical rates."""

    def _make_belief_dict(
        self,
        bull: float = 0.50,
        base: float = 0.30,
        bear: float = 0.20,
    ) -> dict:
        return {
            "ticker": "FPT",
            "bull_probability": bull,
            "base_probability": base,
            "bear_probability": bear,
            "conviction": 0.6,
        }

    def test_anchoring_with_dynamic_rates(self):
        """Dynamic rates (24/68/8) pull toward correct distribution."""
        dynamic_rates = {"BULLISH": 0.24, "NEUTRAL": 0.68, "BEARISH": 0.08}
        beliefs = [self._make_belief_dict(bull=0.50, base=0.30, bear=0.20)]
        result = apply_base_rate_anchor(beliefs, base_rates=dynamic_rates, anchor_weight=0.1)
        anchored = result[0]
        # Bull: 0.9*0.50 + 0.1*0.24 = 0.474
        assert abs(anchored["bull_probability"] - 0.474) < 0.001
        # Base: 0.9*0.30 + 0.1*0.68 = 0.338
        assert abs(anchored["base_probability"] - 0.338) < 0.001
        # Bear: 0.9*0.20 + 0.1*0.08 = 0.188
        assert abs(anchored["bear_probability"] - 0.188) < 0.001

    def test_anchoring_pulls_toward_neutral(self):
        """Overconfident BEARISH gets pulled toward NEUTRAL by correct rates."""
        dynamic_rates = {"BULLISH": 0.24, "NEUTRAL": 0.68, "BEARISH": 0.08}
        beliefs = [self._make_belief_dict(bull=0.15, base=0.25, bear=0.60)]
        result = apply_base_rate_anchor(beliefs, base_rates=dynamic_rates, anchor_weight=0.1)
        anchored = result[0]
        # Bear: 0.9*0.60 + 0.1*0.08 = 0.548 (reduced from 0.60)
        assert anchored["bear_probability"] < 0.60
        # Base: 0.9*0.25 + 0.1*0.68 = 0.293 (increased from 0.25)
        assert anchored["base_probability"] > 0.25

    def test_fallback_rates_used_when_none(self):
        """When base_rates=None, fallback constants are used."""
        beliefs = [self._make_belief_dict(bull=0.50, base=0.30, bear=0.20)]
        result = apply_base_rate_anchor(beliefs, base_rates=None, anchor_weight=0.1)
        anchored = result[0]
        # Bull: 0.9*0.50 + 0.1*0.24 = 0.474 (fallback is same as empirical now)
        expected_bull = 0.9 * 0.50 + 0.1 * FALLBACK_BASE_RATES["BULLISH"]
        assert abs(anchored["bull_probability"] - expected_bull) < 0.001

    def test_anchor_weight_zero_no_change(self):
        """Zero anchor weight means no change to beliefs."""
        dynamic_rates = {"BULLISH": 0.24, "NEUTRAL": 0.68, "BEARISH": 0.08}
        beliefs = [self._make_belief_dict(bull=0.50, base=0.30, bear=0.20)]
        result = apply_base_rate_anchor(beliefs, base_rates=dynamic_rates, anchor_weight=0.0)
        assert abs(result[0]["bull_probability"] - 0.50) < 0.001

    def test_anchor_weight_one_replaces_with_base(self):
        """Full anchor weight replaces beliefs with base rates."""
        dynamic_rates = {"BULLISH": 0.24, "NEUTRAL": 0.68, "BEARISH": 0.08}
        beliefs = [self._make_belief_dict(bull=0.50, base=0.30, bear=0.20)]
        result = apply_base_rate_anchor(beliefs, base_rates=dynamic_rates, anchor_weight=1.0)
        assert abs(result[0]["bull_probability"] - 0.24) < 0.001
        assert abs(result[0]["base_probability"] - 0.68) < 0.001
        assert abs(result[0]["bear_probability"] - 0.08) < 0.001

    def test_multiple_beliefs_anchored_independently(self):
        """Each belief in list gets anchored separately."""
        dynamic_rates = {"BULLISH": 0.24, "NEUTRAL": 0.68, "BEARISH": 0.08}
        beliefs = [
            self._make_belief_dict(bull=0.70, base=0.20, bear=0.10),
            self._make_belief_dict(bull=0.10, base=0.80, bear=0.10),
        ]
        result = apply_base_rate_anchor(beliefs, base_rates=dynamic_rates, anchor_weight=0.1)
        # First: strongly bullish → bull pulled down
        assert result[0]["bull_probability"] < 0.70
        # Second: strongly neutral → stays relatively similar
        assert result[1]["base_probability"] > 0.70

    def test_anchoring_direction_correctness(self):
        """Verify anchoring ALWAYS pulls toward base rates, never away."""
        dynamic_rates = {"BULLISH": 0.24, "NEUTRAL": 0.68, "BEARISH": 0.08}
        # Agent predicts too much bearish
        beliefs = [self._make_belief_dict(bull=0.20, base=0.20, bear=0.60)]
        result = apply_base_rate_anchor(beliefs, base_rates=dynamic_rates, anchor_weight=0.1)
        # Bear was 0.60, rate is 0.08 → must decrease
        assert result[0]["bear_probability"] < 0.60
        # Base was 0.20, rate is 0.68 → must increase
        assert result[0]["base_probability"] > 0.20
