"""Rule 5a (catalyst_belief_relief) regression tests.

Targets DEF-2026-04-24-003:
  - Placeholder-aware cap excludes ``FAIL_CLOSED_FLOOR`` from expectancy/
    family signals so cold-start 4.0 defaults don't mask the relief.
  - Observed (non-placeholder) expectancy/family floors still survive.
  - Combined catalyst + ≥2 bullish sector beliefs required.
  - Fail-closed under missing signals.
  - Does not fire below RR_FLOOR_ELEVATED nor under CRISIS / shock-only.
"""

from __future__ import annotations

from shared.rules.expectancy import FAIL_CLOSED_FLOOR, FamilyExpectancyFloors
from shared.rules.recommendation_gate import (
    _DIGEST_KEYS,
    MIN_BULLISH_BELIEFS_FOR_RELIEF,
    RR_FLOOR_SHOCK_ONLY,
    RecommendationGateDecision,
    compose_recommendation_gate,
    recompose_for_strategy_failure,
)
from shared.rules.rr_floors import RR_FLOOR_ELEVATED


def _base_kwargs(**overrides) -> dict[str, object]:
    """Stressed-regime baseline where Rule 5a is eligible to fire."""
    kwargs: dict[str, object] = {
        "trading_mode": "NORMAL",
        "market_regime": "RISK_OFF",
        "global_risk_regime": "ELEVATED",
        "urgency_tier": "DETERMINED",
        "urgency_min_rr": 3.5,
        "urgency_max_picks": 3,
        "underlying_stress": True,
        "has_high_positive_macro_catalyst": True,
        "bullish_sector_belief_count": MIN_BULLISH_BELIEFS_FOR_RELIEF,
    }
    kwargs.update(overrides)
    return kwargs


def _compose(**overrides) -> RecommendationGateDecision:
    return compose_recommendation_gate(**_base_kwargs(**overrides))  # type: ignore[arg-type]


class TestPlaceholderAwareCap:
    def test_relief_caps_to_elevated_when_expectancy_is_fail_closed_placeholder(self) -> None:
        # Cold-start / no closes: expectancy_floor returns FAIL_CLOSED_FLOOR
        # (4.0). Rule 5a must EXCLUDE this from its cap so the relief drops
        # to RR_FLOOR_ELEVATED (3.0). Headline failure-mode scenario.
        decision = _compose(expectancy_floor=FAIL_CLOSED_FLOOR)
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED
        assert "catalyst_belief_relief" in decision.applied_rules

    def test_relief_respects_observed_expectancy_below_fail_closed(self) -> None:
        # 3.5 is a real observed floor from live win-rate math. Base floor
        # resolves to 3.5 already; Rule 5a's cap is max(3.0, 3.5) = 3.5 so
        # no additional relief fires, but the observed signal is preserved.
        decision = _compose(expectancy_floor=3.5)
        assert decision.effective_rr_floor == 3.5

    def test_relief_respects_observed_family_floor(self) -> None:
        # Observed family floor 3.8 survives relief — cap computes to 3.8
        # so floor > cap is False; no relief fires, but the signal is
        # honored.
        family: FamilyExpectancyFloors = {"FIXED_TARGET": 3.8, "ATR_TRAIL": 2.5}
        decision = _compose(
            expectancy_floor=None,
            family_floors=family,
            strategy="MEAN_REVERSION",  # → FIXED_TARGET family
        )
        assert decision.effective_rr_floor == 3.8

    def test_relief_excludes_fail_closed_family_floor(self) -> None:
        # Family floor carrying FAIL_CLOSED_FLOOR placeholder must be
        # excluded → cap falls to RR_FLOOR_ELEVATED (3.0).
        family: FamilyExpectancyFloors = {
            "FIXED_TARGET": FAIL_CLOSED_FLOOR,
            "ATR_TRAIL": FAIL_CLOSED_FLOOR,
        }
        decision = _compose(
            expectancy_floor=None,
            family_floors=family,
            strategy="TREND",  # → ATR_TRAIL family
        )
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED
        assert "catalyst_belief_relief" in decision.applied_rules


class TestReliefGuards:
    def test_no_relief_below_two_bullish(self) -> None:
        decision = _compose(bullish_sector_belief_count=1, expectancy_floor=FAIL_CLOSED_FLOOR)
        assert "catalyst_belief_relief" not in decision.applied_rules

    def test_no_relief_without_catalyst(self) -> None:
        decision = _compose(
            has_high_positive_macro_catalyst=False,
            has_candidate_positive_catalyst=False,
            expectancy_floor=FAIL_CLOSED_FLOOR,
        )
        assert "catalyst_belief_relief" not in decision.applied_rules

    def test_no_relief_when_sector_beliefs_empty(self) -> None:
        decision = _compose(bullish_sector_belief_count=0, expectancy_floor=FAIL_CLOSED_FLOOR)
        assert "catalyst_belief_relief" not in decision.applied_rules

    def test_no_relief_shock_only_path(self) -> None:
        # underlying_stress=False → shock-only regime boost; Rule 5a doesn't
        # fire. Using a no-expectancy scenario so the shock floor binds.
        decision = _compose(
            underlying_stress=False,
            expectancy_floor=None,
            urgency_min_rr=2.5,
        )
        assert "catalyst_belief_relief" not in decision.applied_rules
        assert decision.effective_rr_floor == RR_FLOOR_SHOCK_ONLY

    def test_bearish_majority_with_one_bullish_no_relief(self) -> None:
        # 12 BEARISH + 1 BULLISH → count=1 → below threshold → fail-closed.
        decision = _compose(bullish_sector_belief_count=1)
        assert "catalyst_belief_relief" not in decision.applied_rules

    def test_relief_never_lowers_below_elevated_floor(self) -> None:
        # Max-strength signals: observed expectancy near floor, empty family.
        decision = _compose(expectancy_floor=0.1)
        assert decision.effective_rr_floor >= RR_FLOOR_ELEVATED


class TestRuleOrdering:
    def test_relief_after_retro_override(self) -> None:
        # retro_min_rr_override=2.8 → floor drops to 2.8 before Rule 5a;
        # relief sees floor < cap and doesn't raise it.
        decision = _compose(
            retro_min_rr_override=2.8,
            expectancy_floor=FAIL_CLOSED_FLOOR,
        )
        assert decision.effective_rr_floor == 2.8
        # Rule 5a no-op because floor already <= cap.
        assert "catalyst_belief_relief" not in decision.applied_rules

    def test_relief_after_streak_relaxation(self) -> None:
        # streak alert on rr_floor profile (3d) drops floor; Rule 5a no-op.
        streak = {"length": 3, "gate_profile": "rr_floor"}
        decision = _compose(streak_alert=streak, expectancy_floor=FAIL_CLOSED_FLOOR)
        # Streak relaxation fires first; floor already <= RR_FLOOR_ELEVATED.
        assert "streak_relax_rr_floor" in decision.applied_rules

    def test_recompose_for_strategy_failure_preserves_relief_signals(self) -> None:
        # recompose reads new digest keys so relief rule fires identically.
        decision = _compose(
            global_risk_regime="ELEVATED",
            strategy_director_failed=False,
            expectancy_floor=FAIL_CLOSED_FLOOR,
        )
        # Digest keys contract: new keys must be present.
        assert "has_high_positive_macro_catalyst" in _DIGEST_KEYS
        assert "bullish_sector_belief_count" in _DIGEST_KEYS
        assert "has_candidate_positive_catalyst" in _DIGEST_KEYS
        # Recompose under strategy_director_failed=True blocks entries
        # (structural block on stressed regime), but the digest survives.
        recomposed = recompose_for_strategy_failure(decision)
        assert recomposed.inputs_digest["has_high_positive_macro_catalyst"] is True
        assert recomposed.inputs_digest["bullish_sector_belief_count"] == (
            MIN_BULLISH_BELIEFS_FOR_RELIEF
        )


class TestShockActiveGuard:
    """L3 (2026-04-27): Rule 5a's underlying_stress guard widens to
    `(underlying_stress OR shock_active)`. Shock-pinned-regime + calm-VIX
    days no longer silently silence the relief."""

    def test_shock_active_alone_fires_relief(self) -> None:
        # Calm VIX (underlying_stress=False) + shock-pinned regime
        # (shock_active=True) + catalyst + 2 bullish beliefs → relief fires.
        decision = _compose(
            underlying_stress=False,
            shock_active=True,
            expectancy_floor=FAIL_CLOSED_FLOOR,
        )
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED
        assert "catalyst_belief_relief" in decision.applied_rules

    def test_underlying_stress_alone_still_fires_backward_compat(self) -> None:
        # Pre-L3 path: underlying_stress=True, shock_active default False
        # → relief still fires (OR-guard preserves backward compat).
        decision = _compose(
            underlying_stress=True,
            expectancy_floor=FAIL_CLOSED_FLOOR,
        )
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED
        assert "catalyst_belief_relief" in decision.applied_rules

    def test_neither_signal_active_no_relief(self) -> None:
        # underlying_stress=False AND shock_active=False → relief does NOT
        # fire. Note: when underlying_stress=False with stressed regime,
        # the regime boost lands on RR_FLOOR_SHOCK_ONLY (2.5), so the
        # base floor stays at the urgency 3.5 (no relief needed).
        decision = _compose(
            underlying_stress=False,
            shock_active=False,
            expectancy_floor=FAIL_CLOSED_FLOOR,
        )
        assert "catalyst_belief_relief" not in decision.applied_rules

    def test_shock_active_in_digest(self) -> None:
        decision = _compose(shock_active=True, underlying_stress=True)
        assert decision.inputs_digest["shock_active"] is True
        assert "shock_active" in _DIGEST_KEYS

    def test_recompose_round_trips_shock_active(self) -> None:
        decision = _compose(
            shock_active=True,
            underlying_stress=False,
            expectancy_floor=FAIL_CLOSED_FLOOR,
        )
        # Catalyst relief fires; recompose under strategy_director_failed=True
        # blocks entries via the structural block but preserves shock_active
        # in the surviving digest.
        recomposed = recompose_for_strategy_failure(decision)
        assert recomposed.inputs_digest["shock_active"] is True


class TestStreakBeliefFlatteningCashHealthyRelief:
    """SWI-93 — belief_flattening + length>=7 + cash_healthy must trigger
    soft-tier streak relief (delta=0.5, NOT escalation delta=1.0)."""

    def _base(self, **overrides) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "trading_mode": "NORMAL",
            "market_regime": "NEUTRAL",
            "global_risk_regime": "NEUTRAL",
            "urgency_tier": "NORMAL",
            "urgency_min_rr": 3.5,
            "urgency_max_picks": 3,
            "underlying_stress": False,
            "has_high_positive_macro_catalyst": False,
            "bullish_sector_belief_count": 0,
            "cash_healthy": True,
            "streak_alert": {"length": 7, "gate_profile": "belief_flattening"},
        }
        kwargs.update(overrides)
        return kwargs

    def test_length_7_normal_mode_soft_relax_fires(self) -> None:
        decision = compose_recommendation_gate(**self._base())  # type: ignore[arg-type]
        assert "streak_relax_rr_floor" in decision.applied_rules
        # Soft-tier (delta=0.5), NOT double-strength escalation.
        assert "streak_escalation" not in decision.applied_rules
        # 3.5 base - 0.5 delta = 3.0
        assert decision.effective_rr_floor == 3.0

    def test_length_6_does_not_relax(self) -> None:
        decision = compose_recommendation_gate(
            **self._base(streak_alert={"length": 6, "gate_profile": "belief_flattening"})  # type: ignore[arg-type]
        )
        assert "streak_relax_rr_floor" not in decision.applied_rules

    def test_low_cash_blocks_relief(self) -> None:
        # LOW_CASH mode short-circuits with a block decision; cash_healthy
        # must be False so the new branch never fires.
        decision = compose_recommendation_gate(
            **self._base(trading_mode="LOW_CASH", cash_healthy=False)  # type: ignore[arg-type]
        )
        assert decision.entries_allowed is False

    def test_macro_catalyst_path_still_escalates_at_length_8(self) -> None:
        decision = compose_recommendation_gate(
            **self._base(
                streak_alert={"length": 8, "gate_profile": "rr_floor"},
                has_high_positive_macro_catalyst=True,
            )  # type: ignore[arg-type]
        )
        # Existing macro-catalyst path: length>=7 with rr_floor profile
        # and no flip → escalation multiplier=2.0 still fires.
        assert "streak_escalation" in decision.applied_rules

    def test_derive_caller_passes_cash_healthy_as_str_mode(self) -> None:
        # F1 regression: trading_mode arrives at the composer as str (not
        # dict) per derive.py:151. cash_healthy=True must propagate into
        # the digest without raising.
        decision = compose_recommendation_gate(**self._base(cash_healthy=True))  # type: ignore[arg-type]
        assert decision.inputs_digest["cash_healthy"] is True
