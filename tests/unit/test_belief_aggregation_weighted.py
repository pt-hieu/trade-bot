"""Belief aggregation: weighted_aggregate_beliefs (pure Python, no I/O)."""

import pytest

from agents.belief_aggregation import (
    anchor_aggregated_belief,
    weighted_aggregate_beliefs,
)
from agents.belief_models import BASE_RATE_BEAR, BASE_RATE_BULL, BASE_RATE_NEUTRAL


def make_belief(
    agent_key: str,
    bull: float,
    base: float,
    bear: float,
    conviction: float = 0.5,
    direction: str = "NEUTRAL",
) -> dict:
    return {
        "agent_key": agent_key,
        "bull_probability": bull,
        "base_probability": base,
        "bear_probability": bear,
        "conviction": conviction,
        "direction": direction,
    }


class TestWeightedAggregateBeliefs:
    def test_empty_beliefs_returns_empty_dict(self):
        result = weighted_aggregate_beliefs([])

        assert result == {}

    def test_single_belief_passthrough(self):
        belief = make_belief("analyst_a", bull=0.60, base=0.30, bear=0.10, conviction=0.8)

        result = weighted_aggregate_beliefs([belief])

        assert result["bull_probability"] == pytest.approx(0.60, abs=1e-4)
        assert result["base_probability"] == pytest.approx(0.30, abs=1e-4)
        assert result["bear_probability"] == pytest.approx(0.10, abs=1e-4)

    def test_two_equal_conviction_beliefs_average(self):
        belief_a = make_belief("analyst_a", bull=0.70, base=0.20, bear=0.10, conviction=0.6)
        belief_b = make_belief("analyst_b", bull=0.30, base=0.50, bear=0.20, conviction=0.6)

        result = weighted_aggregate_beliefs([belief_a, belief_b])

        assert result["bull_probability"] == pytest.approx(0.50, abs=1e-4)
        assert result["base_probability"] == pytest.approx(0.35, abs=1e-4)
        assert result["bear_probability"] == pytest.approx(0.15, abs=1e-4)

    def test_higher_conviction_belief_dominates(self):
        belief_high = make_belief("analyst_a", bull=0.70, base=0.20, bear=0.10, conviction=0.9)
        belief_low = make_belief("analyst_b", bull=0.20, base=0.50, bear=0.30, conviction=0.3)

        result = weighted_aggregate_beliefs([belief_high, belief_low])

        assert result["bull_probability"] > 0.50
        assert result["direction"] == "BULLISH"

    def test_calibration_stats_lower_brier_increases_weight(self):
        belief_a = make_belief("analyst_a", bull=0.80, base=0.15, bear=0.05, conviction=0.5)
        belief_b = make_belief("analyst_b", bull=0.20, base=0.50, bear=0.30, conviction=0.5)
        calibration_stats = {
            "analyst_a": {"avg_brier": 0.10},
            "analyst_b": {"avg_brier": 0.50},
        }

        result = weighted_aggregate_beliefs([belief_a, belief_b], calibration_stats)

        assert result["bull_probability"] > 0.65

    def test_brier_floor_prevents_division_by_zero(self):
        belief = make_belief("analyst_a", bull=0.50, base=0.30, bear=0.20, conviction=0.5)
        calibration_stats = {"analyst_a": {"avg_brier": 0.0}}

        result = weighted_aggregate_beliefs([belief], calibration_stats)

        assert result["bull_probability"] == pytest.approx(0.50, abs=1e-4)

    def test_zero_total_weight_returns_base_rates(self):
        belief_a = make_belief("analyst_a", bull=0.60, base=0.30, bear=0.10, conviction=0.0)
        belief_b = make_belief("analyst_b", bull=0.10, base=0.50, bear=0.40, conviction=0.0)

        result = weighted_aggregate_beliefs([belief_a, belief_b])

        assert result["direction"] == "NEUTRAL"
        assert result["bull_probability"] == BASE_RATE_BULL
        assert result["base_probability"] == BASE_RATE_NEUTRAL
        assert result["bear_probability"] == BASE_RATE_BEAR

    def test_result_direction_reflects_dominant_probability(self):
        belief = make_belief("analyst_a", bull=0.10, base=0.20, bear=0.70, conviction=0.8)

        result = weighted_aggregate_beliefs([belief])

        assert result["direction"] == "BEARISH"

    def test_probabilities_rounded_to_four_decimal_places(self):
        belief_a = make_belief("analyst_a", bull=0.333, base=0.334, bear=0.333, conviction=0.7)
        belief_b = make_belief("analyst_b", bull=0.666, base=0.200, bear=0.134, conviction=0.3)

        result = weighted_aggregate_beliefs([belief_a, belief_b])

        for key in ("bull_probability", "base_probability", "bear_probability"):
            value = result[key]
            assert round(value, 4) == value, f"{key} not rounded to 4 decimal places"

    # ------------------------------------------------------------------
    # Dissent preservation (Fix 1, 2026-04-13 pipeline review)
    # ------------------------------------------------------------------

    def test_weighted_aggregate_preserves_bullish_dissent(self):
        news = make_belief("sector_news", bull=0.55, base=0.25, bear=0.20, conviction=0.55)
        tech = make_belief("sector_technical", bull=0.28, base=0.38, bear=0.34, conviction=0.35)
        enrich = make_belief("sector_enrichment", bull=0.25, base=0.38, bear=0.37, conviction=0.45)

        result = weighted_aggregate_beliefs([news, tech, enrich])

        assert result["bull_probability"] >= 0.40
        assert result["bull_probability"] == pytest.approx(0.50, abs=1e-2)
        assert result["direction"] == "BULLISH"
        total = result["bull_probability"] + result["base_probability"] + result["bear_probability"]
        assert total == pytest.approx(1.0, abs=1e-3)

    def test_weighted_aggregate_preserves_bearish_dissent(self):
        news = make_belief("sector_news", bull=0.20, base=0.25, bear=0.55, conviction=0.55)
        tech = make_belief("sector_technical", bull=0.34, base=0.38, bear=0.28, conviction=0.35)
        enrich = make_belief("sector_enrichment", bull=0.37, base=0.38, bear=0.25, conviction=0.45)

        result = weighted_aggregate_beliefs([news, tech, enrich])

        assert result["bear_probability"] >= 0.40
        assert result["bear_probability"] == pytest.approx(0.50, abs=1e-2)
        assert result["direction"] == "BEARISH"
        total = result["bull_probability"] + result["base_probability"] + result["bear_probability"]
        assert total == pytest.approx(1.0, abs=1e-3)

    def test_dissent_preservation_noop_when_consensus(self):
        news = make_belief("sector_news", bull=0.55, base=0.25, bear=0.20, conviction=0.55)
        tech = make_belief("sector_technical", bull=0.55, base=0.25, bear=0.20, conviction=0.55)
        enrich = make_belief("sector_enrichment", bull=0.55, base=0.25, bear=0.20, conviction=0.55)

        result = weighted_aggregate_beliefs([news, tech, enrich])

        assert result["bull_probability"] == pytest.approx(0.55, abs=1e-4)
        assert result["base_probability"] == pytest.approx(0.25, abs=1e-4)
        assert result["bear_probability"] == pytest.approx(0.20, abs=1e-4)
        assert result["direction"] == "BULLISH"

    # ------------------------------------------------------------------
    # T02: dissent preservation survives the full pipeline (anchor AFTER)
    # ------------------------------------------------------------------

    def test_anchor_after_aggregation_preserves_dissent(self, caplog):
        """Regression test: before T02, base-rate anchoring ran on sub-agent
        INPUTS and pulled bull=0.50 down to 0.474, falling below the
        DISSENT_PRESERVATION_BULL_FLOOR (0.50). Dissent preservation then
        silently no-oped and the aggregated output collapsed to NEUTRAL.

        Simulates the 2026-04-14 VHM shape: 4 NEUTRAL sub-agents + 1 BULLISH
        dissenter at raw bull=0.50, conv=0.55.
        """
        import logging

        bullish_dissenter = make_belief(
            "sector_news", bull=0.50, base=0.30, bear=0.20, conviction=0.55
        )
        neutrals = [
            make_belief(f"analyst_{i}", bull=0.30, base=0.40, bear=0.30, conviction=0.45)
            for i in range(4)
        ]
        all_beliefs = [bullish_dissenter, *neutrals]

        with caplog.at_level(logging.INFO, logger="agents.belief_aggregation"):
            aggregated = weighted_aggregate_beliefs(all_beliefs)

        dissent_log_count = sum(
            1 for r in caplog.records if "dissent_preservation(bull)" in r.getMessage()
        )
        assert dissent_log_count == 1, "dissent_preservation(bull) must fire exactly once"

        assert aggregated["bull_probability"] >= 0.40
        assert aggregated["direction"] == "BULLISH"

        anchored = anchor_aggregated_belief(aggregated)
        assert anchored["bull_probability"] >= 0.40
        assert anchored["direction"] == "BULLISH"

    def test_anchor_aggregated_belief_preserves_other_keys(self):
        aggregated = {
            "direction": "BULLISH",
            "bull_probability": 0.60,
            "base_probability": 0.30,
            "bear_probability": 0.10,
            "extra_key": "preserved",
        }

        result = anchor_aggregated_belief(aggregated)

        assert result["extra_key"] == "preserved"
        assert result["bull_probability"] < 0.60
        assert aggregated["bull_probability"] == 0.60

    def test_anchor_aggregated_belief_rederives_direction(self):
        aggregated = {
            "direction": "BULLISH",
            "bull_probability": 0.405,
            "base_probability": 0.35,
            "bear_probability": 0.245,
        }

        result = anchor_aggregated_belief(aggregated)

        assert "direction" in result
        total = result["bull_probability"] + result["base_probability"] + result["bear_probability"]
        assert total == pytest.approx(1.0, abs=1e-3)

    # ------------------------------------------------------------------
    # T06: graduated weight reduction with cold-start floor
    # ------------------------------------------------------------------

    def _run_poor_and_reference(self, poor_scored: int, poor_brier: float) -> float:
        poor_agent = make_belief("poor_agent", bull=0.80, base=0.15, bear=0.05, conviction=0.5)
        reference_agent = make_belief("reference", bull=0.10, base=0.30, bear=0.60, conviction=0.5)
        calibration_stats = {
            "poor_agent": {
                "avg_brier": poor_brier,
                "brier_30d": poor_brier,
                "scored_beliefs": poor_scored,
            },
            "reference": {
                "avg_brier": 0.25,
                "brier_30d": 0.25,
                "scored_beliefs": 100,
            },
        }
        result = weighted_aggregate_beliefs(
            [poor_agent, reference_agent], calibration_stats=calibration_stats
        )
        return result["bull_probability"]

    def test_cold_start_floor_leaves_weight_untouched(self):
        cold_start_bull = self._run_poor_and_reference(poor_scored=10, poor_brier=0.70)
        reduced_bull = self._run_poor_and_reference(poor_scored=40, poor_brier=0.70)
        assert cold_start_bull > reduced_bull, (
            f"cold-start should retain more poor_agent influence than reduced: "
            f"cold={cold_start_bull} reduced={reduced_bull}"
        )

    def test_graduated_weight_monotonic_reduction(self):
        bulls = [
            self._run_poor_and_reference(poor_scored=scored, poor_brier=0.70)
            for scored in (15, 20, 25, 30, 40)
        ]
        for earlier, later in zip(bulls, bulls[1:], strict=False):
            assert earlier >= later, f"non-monotonic: {bulls}"
        assert bulls[0] - bulls[-1] > 0.03, f"expected meaningful reduction, got {bulls}"

    def test_brier_below_threshold_not_reduced(self):
        low_scored = self._run_poor_and_reference(poor_scored=10, poor_brier=0.45)
        high_scored = self._run_poor_and_reference(poor_scored=100, poor_brier=0.45)
        assert low_scored == pytest.approx(high_scored, abs=1e-4)

    def test_missing_agent_key_uses_default_brier(self):
        belief = make_belief("unknown_agent", bull=0.50, base=0.30, bear=0.20, conviction=0.5)
        calibration_stats = {"some_other_agent": {"avg_brier": 0.20}}

        result = weighted_aggregate_beliefs([belief], calibration_stats)

        assert "bull_probability" in result
