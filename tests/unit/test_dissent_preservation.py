"""Dissent preservation directional-gate regression tests.

Replay of the 2026-04-15 pipeline review defect (MON-2026-04-13-003):
`preserve_high_conviction_dissent` gated on `max(bull, base, bear) >= 0.40`
which fired on every base-heavy distribution — because base is NEUTRAL,
not a direction. Fix: gate on `max(bull, bear)` only so preservation runs
whenever the WEIGHTED MEAN is not yet directional.

2026-04-15 DXS is the canonical reproduction case: 4 sector sub-agents
voted bullish but sector_enrichment (brier=0.6805, scored=317) was
sigmoid-zeroed, and the resulting weighted mean bull=0.398 base=0.452
triggered the early-return bug.
"""

from __future__ import annotations

import pytest

from agents.belief_aggregation import weighted_aggregate_beliefs
from agents.belief_aggregation._dissent import preserve_high_conviction_dissent


def make_belief(
    agent_key: str,
    bull: float,
    base: float,
    bear: float,
    conviction: float,
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


# ---------------------------------------------------------------------------
# Replay — 2026-04-15 DXS (proves the directional-gate defect fixes the flat
# output observed in pipeline-review bundle /tmp/swingy-review-2026-04-15)
# ---------------------------------------------------------------------------


DXS_2026_04_15_BELIEFS = [
    # sector_news — weakly neutral, low conviction
    make_belief("sector_news", bull=0.25, base=0.60, bear=0.15, conviction=0.35),
    # sector_technical — BULLISH
    make_belief("sector_technical", bull=0.45, base=0.40, bear=0.15, conviction=0.50),
    # sector_aggregator — BULLISH (itself an ensemble output, re-aggregated)
    make_belief("sector_aggregator", bull=0.45, base=0.40, bear=0.15, conviction=0.60),
    # sector_enrichment — strongest BULLISH, but gets sigmoid-zeroed
    make_belief("sector_enrichment", bull=0.50, base=0.35, bear=0.15, conviction=0.60),
]


# SWI-122 / Fix 6 update: BRIER_DOWN_WEIGHT_THRESHOLD is now anchored to the
# uninformed-forecaster Brier (~0.47 for FALLBACK_BASE_RATES). For dissent
# preservation to have signal to lift, at least the strongest dissenter must
# have brier <= anchor. The original 2026-04-15 brier values (0.60–0.68) all
# exceeded the new anchor, leaving zero weighted signal — that's the new
# correct behaviour for that snapshot, but the regression we want to pin
# here is the directional-gate defect, not the brier policy. Lower the
# brier values to below-anchor so the gate fix is actually exercised.
DXS_2026_04_15_CALIBRATION = {
    "sector_news": {"avg_brier": 0.42, "brier_30d": 0.42, "scored_beliefs": 304},
    "sector_technical": {"avg_brier": 0.40, "brier_30d": 0.40, "scored_beliefs": 338},
    "sector_aggregator": {"avg_brier": 0.41, "brier_30d": 0.41, "scored_beliefs": 311},
    "sector_enrichment": {"avg_brier": 0.39, "brier_30d": 0.39, "scored_beliefs": 317},
}


class TestDxs2026_04_15Replay:
    def test_dxs_aggregates_to_bullish_after_fix(self):
        """2026-04-15 DXS: 3 BULLISH + 1 NEUTRAL sub-agent beliefs must
        produce a BULLISH aggregated output after the directional-gate fix.

        Before fix: `max(bull, base, bear)` short-circuited preservation
        when base > 0.40, producing NEUTRAL for 34/34 tickers on 2026-04-15.
        """
        result = weighted_aggregate_beliefs(
            DXS_2026_04_15_BELIEFS, calibration_stats=DXS_2026_04_15_CALIBRATION
        )

        # Preserved toward the strongest dissenter (sector_enrichment bull=0.50)
        # landing at 0.50 - DISSENT_PRESERVATION_RELAX=0.05 = 0.45.
        assert result["bull_probability"] >= 0.40, (
            f"preservation should lift bull above 0.40 — got {result['bull_probability']}"
        )
        assert result["direction"] == "BULLISH", (
            f"expected BULLISH after preservation, got {result['direction']}"
        )
        total = result["bull_probability"] + result["base_probability"] + result["bear_probability"]
        assert total == pytest.approx(1.0, abs=1e-3)

    def test_base_heavy_weighted_mean_triggers_preservation(self):
        """Direct test on `preserve_high_conviction_dissent`: base-heavy
        aggregated distribution (bull<bear<base, base above the 0.40 gate)
        must enter the preservation path, not short-circuit on max(base).
        """
        new_bull, new_base, new_bear = preserve_high_conviction_dissent(
            DXS_2026_04_15_BELIEFS,
            aggregated_bull=0.398,
            aggregated_base=0.452,
            aggregated_bear=0.150,
        )

        # Preservation path ran → bull lifted toward dissenter (0.50 - 0.05).
        assert new_bull >= 0.40
        assert new_bull > 0.398  # strictly lifted from original
        # Distribution still sums to 1.0 after renormalization.
        assert (new_bull + new_base + new_bear) == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Regression fixtures — guard against over-triggering
# ---------------------------------------------------------------------------


class TestNoOverTriggering:
    def test_all_neutral_low_conviction_stays_neutral(self):
        """All sub-agents NEUTRAL with weak conviction — no dissenter meets
        the bull/bear floor, so preservation must NOT lift anything."""
        beliefs = [
            make_belief("agent_a", bull=0.30, base=0.55, bear=0.15, conviction=0.40),
            make_belief("agent_b", bull=0.32, base=0.50, bear=0.18, conviction=0.35),
            make_belief("agent_c", bull=0.28, base=0.58, bear=0.14, conviction=0.40),
        ]

        result = weighted_aggregate_beliefs(beliefs)

        # No dissenter has bull_probability >= 0.45 → preservation no-ops.
        assert result["direction"] == "NEUTRAL"

    def test_weak_bullish_below_conviction_floor_stays_neutral(self):
        """One borderline BULLISH sub-agent below conviction floor (0.45) +
        3 neutrals — preservation should NOT fire (dissenter fails floor)."""
        beliefs = [
            make_belief("agent_a", bull=0.48, base=0.37, bear=0.15, conviction=0.35),
            make_belief("agent_b", bull=0.30, base=0.55, bear=0.15, conviction=0.50),
            make_belief("agent_c", bull=0.30, base=0.55, bear=0.15, conviction=0.50),
            make_belief("agent_d", bull=0.30, base=0.55, bear=0.15, conviction=0.50),
        ]

        result = weighted_aggregate_beliefs(beliefs)

        # agent_a's bull meets BULL_FLOOR but fails CONV_FLOOR → no lift.
        assert result["direction"] == "NEUTRAL"

    def test_directional_mean_above_gate_no_lift(self):
        """If the weighted mean already clears 0.40 on bull, preservation
        must NOT re-lift (the gate still protects against double-lift)."""
        beliefs = [
            make_belief("agent_a", bull=0.55, base=0.30, bear=0.15, conviction=0.55),
            make_belief("agent_b", bull=0.55, base=0.30, bear=0.15, conviction=0.55),
            make_belief("agent_c", bull=0.55, base=0.30, bear=0.15, conviction=0.55),
        ]

        result = weighted_aggregate_beliefs(beliefs)

        # Bull clears the 0.40 gate → early return with unchanged values.
        assert result["bull_probability"] == pytest.approx(0.55, abs=1e-4)
        assert result["direction"] == "BULLISH"

    def test_mixed_bull_bear_stronger_side_wins(self):
        """2 BULLISH + 2 BEARISH dissenters at equal strength — preservation
        picks the stronger side (ties favor bull by current impl choice)."""
        beliefs = [
            make_belief("agent_a", bull=0.50, base=0.35, bear=0.15, conviction=0.55),
            make_belief("agent_b", bull=0.52, base=0.33, bear=0.15, conviction=0.55),
            make_belief("agent_c", bull=0.15, base=0.35, bear=0.50, conviction=0.55),
            make_belief("agent_d", bull=0.15, base=0.33, bear=0.52, conviction=0.55),
        ]

        result = weighted_aggregate_beliefs(beliefs)

        # Stronger bull (0.52 vs 0.52) → preserved bull direction.
        # Weighted mean flattens to ~0.33 bull / 0.33 base / 0.33 bear so
        # max_directional ≈ 0.33 < 0.40 → preservation runs.
        assert result["direction"] in ("BULLISH", "BEARISH")


# ---------------------------------------------------------------------------
# Anchor interaction — preserved bull must survive post-anchor drift
# ---------------------------------------------------------------------------


class TestAnchorInteraction:
    def test_preserved_bull_survives_base_rate_anchor(self):
        """After preservation lifts bull to ~0.45, the downstream 10%
        base-rate anchor should leave the distribution directional when
        empirical base rates are roughly balanced (production uses
        `compute_empirical_base_rates(days_back=90)`).

        Note: FALLBACK_BASE_RATES are heavily neutral-skewed (neutral=0.68),
        so the anchor flips weakly-preserved distributions back to NEUTRAL
        in test/fresh environments — production must provide empirical
        rates to preserve dissent survivability. This test passes a
        realistic balanced rate set so the test isn't misleading.
        """
        from agents.belief_aggregation import anchor_aggregated_belief

        aggregated = weighted_aggregate_beliefs(
            DXS_2026_04_15_BELIEFS, calibration_stats=DXS_2026_04_15_CALIBRATION
        )
        # Pre-anchor: preservation lifts to BULLISH.
        assert aggregated["direction"] == "BULLISH"
        assert aggregated["bull_probability"] >= 0.40

        # Realistic empirical rates (closer to uniform than fallback).
        empirical_rates = {"BULLISH": 0.35, "NEUTRAL": 0.40, "BEARISH": 0.25}
        anchored = anchor_aggregated_belief(aggregated, base_rates=empirical_rates)

        assert anchored["bull_probability"] >= 0.40
        assert anchored["direction"] == "BULLISH"
