"""Belief calibration: lazy NEUTRAL detection threshold."""

from agents.belief_models import (
    BASE_RATE_NEUTRAL,
    LAZY_NEUTRAL_BASE_THRESHOLD,
    LAZY_NEUTRAL_CONVICTION_THRESHOLD,
    TickerBelief,
)


class TestLazyNeutralThreshold:
    """Verify the lazy NEUTRAL threshold doesn't punish correct NEUTRAL predictions."""

    def test_threshold_above_empirical_neutral(self):
        """Threshold must be above the empirical NEUTRAL rate (~0.68).
        A base_probability of 0.68 is CORRECT, not lazy."""
        assert LAZY_NEUTRAL_BASE_THRESHOLD > BASE_RATE_NEUTRAL

    def test_threshold_is_075(self):
        """Only flag as lazy when base > 0.75 — genuinely defaulting."""
        assert LAZY_NEUTRAL_BASE_THRESHOLD == 0.75

    def test_conviction_threshold_unchanged(self):
        """Conviction threshold for lazy detection remains 0.5."""
        assert LAZY_NEUTRAL_CONVICTION_THRESHOLD == 0.5

    def test_genuine_neutral_065_not_lazy(self, caplog):
        """base_probability=0.65 + conviction=0.55 is GENUINE (correct prediction)."""
        import logging

        with caplog.at_level(logging.WARNING):
            TickerBelief(
                ticker="FPT",
                belief_narrative="Mixed signals, range-bound expected",
                direction="NEUTRAL",
                bull_probability=0.20,
                base_probability=0.65,
                bear_probability=0.15,
                price_target_vnd=120000,
                timeframe_days=5,
                conviction=0.55,
                belief_status="NEW",
            )
        assert "Lazy NEUTRAL" not in caplog.text

    def test_genuine_neutral_070_not_lazy(self, caplog):
        """base_probability=0.70 is still not lazy with decent conviction."""
        import logging

        with caplog.at_level(logging.WARNING):
            TickerBelief(
                ticker="TCB",
                belief_narrative="No catalyst, stays flat",
                direction="NEUTRAL",
                bull_probability=0.18,
                base_probability=0.70,
                bear_probability=0.12,
                price_target_vnd=30000,
                timeframe_days=5,
                conviction=0.60,
                belief_status="NEW",
            )
        assert "Lazy NEUTRAL" not in caplog.text

    def test_lazy_neutral_078_low_conviction_flagged(self, caplog):
        """base_probability=0.78 + conviction=0.3 IS lazy — defaulting without thought."""
        import logging

        with caplog.at_level(logging.WARNING):
            TickerBelief(
                ticker="VHM",
                belief_narrative="No view",
                direction="NEUTRAL",
                bull_probability=0.11,
                base_probability=0.78,
                bear_probability=0.11,
                price_target_vnd=50000,
                timeframe_days=5,
                conviction=0.3,
                belief_status="NEW",
            )
        assert "Lazy NEUTRAL" in caplog.text

    def test_high_base_high_conviction_not_lazy(self, caplog):
        """base_probability=0.80 but conviction=0.70 is NOT lazy — deliberate view."""
        import logging

        with caplog.at_level(logging.WARNING):
            TickerBelief(
                ticker="MWG",
                belief_narrative="Strong analysis shows range-bound",
                direction="NEUTRAL",
                bull_probability=0.10,
                base_probability=0.80,
                bear_probability=0.10,
                price_target_vnd=45000,
                timeframe_days=5,
                conviction=0.70,
                belief_status="NEW",
            )
        assert "Lazy NEUTRAL" not in caplog.text
