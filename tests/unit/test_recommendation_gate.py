"""Property tests for shared.rules.recommendation_gate.compose_recommendation_gate.

Invariants (from research/rr-floor-audit-2026-04-20.md):
  * CRISIS → entries_allowed=False
  * LOW_CASH / REALLOCATION → entries_allowed=False
  * entries_allowed=False ⇒ max_new_entries == 0
  * streak rr_floor relaxation bounded by [RR_FLOOR_DEFAULT, RR_FLOOR_ELEVATED]
  * streak belief_flattening / regime_gated → no floor change
  * strategy_director_failed under ELEVATED/RISK_OFF/CRISIS → entries blocked
"""

from __future__ import annotations

import pytest

from shared.rules.recommendation_gate import (
    RR_FLOOR_SHOCK_ONLY,
    RecommendationGateDecision,
    compose_recommendation_gate,
)
from shared.rules.rr_floors import RR_FLOOR_CRISIS, RR_FLOOR_DEFAULT, RR_FLOOR_ELEVATED


def _compose(**overrides) -> RecommendationGateDecision:
    """Baseline: CALM, NORMAL, no retro, no streak, no failure."""
    base: dict[str, object] = {
        "trading_mode": "NORMAL",
        "market_regime": "NEUTRAL",
        "global_risk_regime": "CALM",
        "urgency_tier": "NORMAL",
        "urgency_min_rr": 2.5,
        "urgency_max_picks": 3,
        "underlying_stress": False,
    }
    base.update(overrides)
    return compose_recommendation_gate(**base)  # type: ignore[arg-type]


class TestHappyPath:
    def test_calm_returns_default_floor(self) -> None:
        decision = _compose()
        assert decision.entries_allowed is True
        assert decision.effective_rr_floor == 2.5
        assert decision.max_new_entries == 3
        assert "base_floor" in decision.applied_rules
        assert "circuit_breaker_max_entries" in decision.applied_rules

    def test_audit_trail_is_tuple(self) -> None:
        decision = _compose()
        assert isinstance(decision.applied_rules, tuple)

    def test_inputs_digest_preserves_keys(self) -> None:
        decision = _compose(strategy="TREND")
        assert decision.inputs_digest["trading_mode"] == "NORMAL"
        assert decision.inputs_digest["strategy"] == "TREND"


class TestTradingModeBlock:
    @pytest.mark.parametrize("mode", ["LOW_CASH", "REALLOCATION"])
    def test_blocks_entries(self, mode: str) -> None:
        decision = _compose(trading_mode=mode)
        assert decision.entries_allowed is False
        assert decision.max_new_entries == 0
        assert decision.entries_blocked_reason is not None
        assert mode in decision.entries_blocked_reason

    def test_normal_mode_allows(self) -> None:
        decision = _compose(trading_mode="NORMAL")
        assert decision.entries_allowed is True


class TestRegimeBlock:
    def test_crisis_blocks(self) -> None:
        decision = _compose(global_risk_regime="CRISIS")
        assert decision.entries_allowed is False
        assert decision.max_new_entries == 0
        assert "CRISIS" in (decision.entries_blocked_reason or "")

    def test_elevated_does_not_block(self) -> None:
        decision = _compose(global_risk_regime="ELEVATED", underlying_stress=True)
        assert decision.entries_allowed is True
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED


class TestStrategyDirectorStructuralBlock:
    """Replaces the `min_rr=99.0` fallback in phase_strategy.py."""

    @pytest.mark.parametrize("regime", ["ELEVATED", "RISK_OFF"])
    def test_failed_under_stressed_regime_blocks(self, regime: str) -> None:
        decision = _compose(
            strategy_director_failed=True, global_risk_regime=regime, underlying_stress=True
        )
        assert decision.entries_allowed is False
        assert decision.max_new_entries == 0
        assert "strategy_director_failed" in (decision.entries_blocked_reason or "")

    def test_crisis_block_takes_precedence(self) -> None:
        """CRISIS block fires before structural — CRISIS is the harder block."""
        decision = _compose(
            strategy_director_failed=True, global_risk_regime="CRISIS", underlying_stress=True
        )
        assert decision.entries_allowed is False
        assert "regime_block_crisis" in decision.applied_rules
        assert "CRISIS" in (decision.entries_blocked_reason or "")

    def test_failed_under_calm_does_not_block(self) -> None:
        decision = _compose(strategy_director_failed=True, global_risk_regime="CALM")
        assert decision.entries_allowed is True


class TestRegimeBoost:
    def test_elevated_stressed_uses_full_floor(self) -> None:
        decision = _compose(global_risk_regime="ELEVATED", underlying_stress=True)
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED

    def test_elevated_shock_only_uses_relaxed_floor(self) -> None:
        decision = _compose(global_risk_regime="ELEVATED", underlying_stress=False)
        assert decision.effective_rr_floor == RR_FLOOR_SHOCK_ONLY
        assert "regime_boost_elevated_shock_only" in decision.applied_rules

    def test_risk_off_honors_underlying_stress(self) -> None:
        stressed = _compose(global_risk_regime="RISK_OFF", underlying_stress=True)
        shock_only = _compose(global_risk_regime="RISK_OFF", underlying_stress=False)
        assert stressed.effective_rr_floor == RR_FLOOR_ELEVATED
        assert shock_only.effective_rr_floor == RR_FLOOR_SHOCK_ONLY


class TestRetroOverride:
    def test_retro_lowers_floor(self) -> None:
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            retro_min_rr_override=2.0,
        )
        assert decision.effective_rr_floor == 2.0
        assert "retro_min_rr_override" in decision.applied_rules

    def test_retro_does_not_raise_when_floor_already_lower(self) -> None:
        decision = _compose(retro_min_rr_override=4.0)
        assert decision.effective_rr_floor == 2.5

    def test_retro_max_entries_takes_max(self) -> None:
        decision = _compose(urgency_max_picks=2, retro_max_entries=5)
        assert decision.max_new_entries == 5


class TestStreakRelaxation:
    """Streak-aware floor adjustment — bounded relaxation only."""

    @pytest.mark.parametrize("length", [3, 4, 5, 6])
    def test_rr_floor_profile_relaxes_by_half(self, length: int) -> None:
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={"length": length, "gate_profile": "rr_floor", "start_date": "x"},
        )
        assert decision.effective_rr_floor == pytest.approx(RR_FLOOR_ELEVATED - 0.5)
        assert "streak_relax_rr_floor" in decision.applied_rules

    def test_mixed_profile_relaxes_by_quarter(self) -> None:
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={"length": 3, "gate_profile": "mixed", "start_date": "x"},
        )
        assert decision.effective_rr_floor == pytest.approx(RR_FLOOR_ELEVATED - 0.25)
        assert "streak_relax_mixed" in decision.applied_rules

    def test_belief_flattening_profile_does_not_change_floor(self) -> None:
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={
                "length": 5,
                "gate_profile": "belief_flattening",
                "start_date": "x",
            },
        )
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED
        assert not any("streak" in rule for rule in decision.applied_rules)

    def test_regime_gated_profile_does_not_change_floor(self) -> None:
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={"length": 4, "gate_profile": "regime_gated", "start_date": "x"},
        )
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED

    def test_below_threshold_no_relax(self) -> None:
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={"length": 2, "gate_profile": "rr_floor", "start_date": "x"},
        )
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED

    @pytest.mark.parametrize("length", [7, 8, 9])
    def test_seven_to_nine_day_streak_applies_double_relax(self, length: int) -> None:
        """Graduated cap: 7-9 days doubles the base relax and logs `streak_escalation`.

        Replaces the prior hard-stop at 7 days which turned the streak itself
        into a zero-BUY kill-switch. Fix 0, 2026-04-21.
        """
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={"length": length, "gate_profile": "rr_floor", "start_date": "x"},
        )
        assert decision.effective_rr_floor == pytest.approx(RR_FLOOR_ELEVATED - 1.0)
        assert "streak_relax_rr_floor" in decision.applied_rules
        assert "streak_escalation" in decision.applied_rules

    def test_seven_day_mixed_profile_doubles_to_half(self) -> None:
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={"length": 7, "gate_profile": "mixed", "start_date": "x"},
        )
        assert decision.effective_rr_floor == pytest.approx(RR_FLOOR_ELEVATED - 0.5)
        assert "streak_relax_mixed" in decision.applied_rules
        assert "streak_escalation" in decision.applied_rules

    @pytest.mark.parametrize("length", [10, 14, 30])
    def test_ten_plus_day_streak_is_structural_review(self, length: int) -> None:
        """10+ days = structural. No auto-relax; rule logs escalation for triage."""
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={"length": length, "gate_profile": "rr_floor", "start_date": "x"},
        )
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED
        assert "streak_structural_review" in decision.applied_rules
        assert "streak_relax_rr_floor" not in decision.applied_rules

    def test_ten_plus_day_regime_gated_profile_no_escalation_rule(self) -> None:
        """Non-rr_floor/mixed profile: structural_review rule does NOT fire either."""
        decision = _compose(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            streak_alert={
                "length": 12,
                "gate_profile": "regime_gated",
                "start_date": "x",
            },
        )
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED
        assert not any("streak" in rule for rule in decision.applied_rules)

    def test_relaxation_bounded_by_default_floor(self) -> None:
        """Even multiple relax rules cannot push below RR_FLOOR_DEFAULT."""
        decision = _compose(
            urgency_min_rr=2.0,
            global_risk_regime="CALM",  # no boost, base 2.0
            streak_alert={"length": 3, "gate_profile": "rr_floor", "start_date": "x"},
        )
        assert decision.effective_rr_floor >= RR_FLOOR_DEFAULT

    def test_seven_day_relax_bounded_by_default_floor(self) -> None:
        """Double relax at 7d still clamped to RR_FLOOR_DEFAULT (2.0)."""
        decision = _compose(
            urgency_min_rr=2.0,
            global_risk_regime="CALM",
            streak_alert={"length": 8, "gate_profile": "rr_floor", "start_date": "x"},
        )
        assert decision.effective_rr_floor >= RR_FLOOR_DEFAULT


class TestCircuitBreakerMaxEntries:
    """Feb 28 invariant — max_entries ≥ 1 when entries allowed."""

    def test_zero_picks_bumps_to_one(self) -> None:
        decision = _compose(urgency_max_picks=0)
        assert decision.max_new_entries == 1

    def test_blocked_preserves_zero(self) -> None:
        decision = _compose(trading_mode="LOW_CASH")
        assert decision.max_new_entries == 0


class TestToJsonb:
    """Persistence contract — blob keys stable."""

    def test_to_jsonb_shape(self) -> None:
        decision = _compose()
        blob = decision.to_jsonb()
        assert set(blob.keys()) == {
            "effective_rr_floor",
            "max_new_entries",
            "entries_allowed",
            "entries_blocked_reason",
            "applied_rules",
            "inputs_digest",
            "shock_rr_floor",
        }
        assert isinstance(blob["applied_rules"], list)

    def test_blocked_floor_defaults_to_crisis(self) -> None:
        """Blocked decisions surface a safe (high) floor for any consumer
        that reads effective_rr_floor without first checking entries_allowed."""
        decision = _compose(trading_mode="LOW_CASH")
        assert decision.effective_rr_floor == RR_FLOOR_CRISIS


class TestAprilTwentyScenario:
    """Regression: Apr 20 snapshot that caused the 5-day 0-BUY streak.

    ELEVATED pinned by Hormuz shock floor; VIX LOW / DXY WEAK / USD-VND STABLE
    → underlying_stress False. With the pre-composer stack the floor was 3.0,
    filtering HPG ~2.3, VPB ~2.5, BID 2.41. With the composer the floor drops
    to RR_FLOOR_SHOCK_ONLY so VPB/BID (~2.5) clear and HPG (~2.3) downgrades
    to WATCH instead of dropping silently.
    """

    def test_elevated_shock_only_allows_two_point_five_picks(self) -> None:
        decision = _compose(
            trading_mode="NORMAL",
            market_regime="NEUTRAL",
            global_risk_regime="ELEVATED",
            underlying_stress=False,
            urgency_tier="NORMAL",
            urgency_min_rr=2.5,
            urgency_max_picks=3,
        )
        assert decision.entries_allowed is True
        assert decision.effective_rr_floor == RR_FLOOR_SHOCK_ONLY
        assert decision.max_new_entries == 3
