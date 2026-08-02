"""Extended golden test: macro-relief flips belief_flattening into rr_floor relax.

Covers AUDIT-2026-04-24-001 / ISSUE-2026-04-24-002. The streak-relax rule
previously only fired for ``gate_profile='rr_floor'`` / ``'mixed'`` — a
3+ day zero-BUY streak with ``belief_flattening`` (today's dominant
profile under our settings) was left untreated. The fix extends the
surface classifier: when a HIGH-confidence POSITIVE macro-blanket catalyst
is active AND the streak profile is ``belief_flattening`` or
``regime_gated``, the relax branch fires with the existing 3/7/10-day
staircase governing magnitude.
"""

from __future__ import annotations

import pytest

from shared.rules.recommendation_gate import compose_recommendation_gate


def _streak_alert(length: int, profile: str) -> dict:
    return {
        "length": length,
        "start_date": "2026-04-17",
        "gate_profile": profile,
    }


@pytest.mark.usefixtures("mock_trading_config")
class TestMacroReliefStreakRelax:
    def test_belief_flattening_with_macro_flag_relaxes_floor(self) -> None:
        """3-day belief_flattening streak + HIGH POSITIVE macro catalyst → relax."""
        baseline = compose_recommendation_gate(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_risk_regime="MODERATE",
            urgency_tier="NORMAL",
            urgency_min_rr=3.0,
            urgency_max_picks=3,
            underlying_stress=False,
            streak_alert=_streak_alert(length=3, profile="belief_flattening"),
            has_high_positive_macro_catalyst=False,
        )
        relaxed = compose_recommendation_gate(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_risk_regime="MODERATE",
            urgency_tier="NORMAL",
            urgency_min_rr=3.0,
            urgency_max_picks=3,
            underlying_stress=False,
            streak_alert=_streak_alert(length=3, profile="belief_flattening"),
            has_high_positive_macro_catalyst=True,
        )
        assert relaxed.effective_rr_floor < baseline.effective_rr_floor
        assert any(rule.startswith("streak_relax_") for rule in relaxed.applied_rules), (
            f"expected a streak_relax_* rule in {list(relaxed.applied_rules)}"
        )

    def test_regime_gated_with_macro_flag_also_relaxes(self) -> None:
        relaxed = compose_recommendation_gate(
            trading_mode="NORMAL",
            market_regime="CAUTIOUS",
            global_risk_regime="MODERATE",
            urgency_tier="NORMAL",
            urgency_min_rr=3.0,
            urgency_max_picks=3,
            underlying_stress=False,
            streak_alert=_streak_alert(length=3, profile="regime_gated"),
            has_high_positive_macro_catalyst=True,
        )
        assert any(rule.startswith("streak_relax_") for rule in relaxed.applied_rules)

    def test_no_macro_flag_leaves_belief_flattening_untreated(self) -> None:
        no_relief = compose_recommendation_gate(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_risk_regime="MODERATE",
            urgency_tier="NORMAL",
            urgency_min_rr=3.0,
            urgency_max_picks=3,
            underlying_stress=False,
            streak_alert=_streak_alert(length=3, profile="belief_flattening"),
            has_high_positive_macro_catalyst=False,
        )
        assert not any(rule.startswith("streak_relax_") for rule in no_relief.applied_rules)

    def test_macro_flag_on_rr_floor_profile_is_noop_override(self) -> None:
        """rr_floor profile already fires the relax — macro flag changes nothing."""
        with_flag = compose_recommendation_gate(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_risk_regime="MODERATE",
            urgency_tier="NORMAL",
            urgency_min_rr=3.0,
            urgency_max_picks=3,
            underlying_stress=False,
            streak_alert=_streak_alert(length=3, profile="rr_floor"),
            has_high_positive_macro_catalyst=True,
        )
        without_flag = compose_recommendation_gate(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_risk_regime="MODERATE",
            urgency_tier="NORMAL",
            urgency_min_rr=3.0,
            urgency_max_picks=3,
            underlying_stress=False,
            streak_alert=_streak_alert(length=3, profile="rr_floor"),
            has_high_positive_macro_catalyst=False,
        )
        assert with_flag.effective_rr_floor == without_flag.effective_rr_floor
