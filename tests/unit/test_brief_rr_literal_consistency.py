"""R:R floor consistency — every literal the brief can cite binds to the gate.

Before Fix 3 (2026-04-21), `entry_strategist.yaml:137` hardcoded
`R:R >= 4.0` for the geopolitical-shock clause. MARKET MOOD, KEY RISK,
and ENTRY CRITERIA TODAY could emit different R:R floors on the same
day because each section read from a different source. The composed
`RecommendationGateDecision` now exposes both `effective_rr_floor`
(general) and `shock_rr_floor` (shock-phase non-beneficiary). Every
R:R literal reaching the reader must equal one of those two numbers.
"""

from __future__ import annotations

from shared.rules.recommendation_gate import (
    RR_FLOOR_ELEVATED,
    RR_FLOOR_SHOCK_ONLY,
    compose_recommendation_gate,
)


def _decision(**overrides):
    base: dict = {
        "trading_mode": "NORMAL",
        "market_regime": "NEUTRAL",
        "global_risk_regime": "NEUTRAL",
        "urgency_tier": "NORMAL",
        "urgency_min_rr": 2.0,
        "urgency_max_picks": 3,
        "underlying_stress": False,
    }
    base.update(overrides)
    return compose_recommendation_gate(**base)


class TestShockFloorExposed:
    def test_neutral_regime_shock_matches_effective(self):
        decision = _decision()
        assert decision.effective_rr_floor == 2.0
        assert decision.shock_rr_floor == 2.0

    def test_elevated_shock_only_shock_raises_to_elevated(self):
        decision = _decision(global_risk_regime="ELEVATED", underlying_stress=False)
        assert decision.effective_rr_floor == RR_FLOOR_SHOCK_ONLY
        assert decision.shock_rr_floor == RR_FLOOR_ELEVATED

    def test_elevated_stressed_both_at_stressed_floor(self):
        decision = _decision(global_risk_regime="ELEVATED", underlying_stress=True)
        assert decision.effective_rr_floor == RR_FLOOR_ELEVATED
        assert decision.shock_rr_floor == RR_FLOOR_ELEVATED


class TestGateSerialization:
    def test_jsonb_includes_shock_floor(self):
        decision = _decision(global_risk_regime="ELEVATED", underlying_stress=False)
        payload = decision.to_jsonb()
        assert payload["effective_rr_floor"] == RR_FLOOR_SHOCK_ONLY
        assert payload["shock_rr_floor"] == RR_FLOOR_ELEVATED


class TestConsistencyInvariant:
    """Any R:R literal the brief emits must equal one of these two numbers."""

    def test_pair_always_present(self):
        decision = _decision()
        pair = {decision.effective_rr_floor, decision.shock_rr_floor}
        # Invariant: no more than two canonical floor numbers per day.
        assert 1 <= len(pair) <= 2

    def test_shock_never_below_effective(self):
        """Shock floor is always at least as tight as the general floor.

        Rationale: shock entries face higher uncertainty; the floor can only
        go up during shock, never down.
        """
        for overrides in (
            {"global_risk_regime": "NEUTRAL"},
            {"global_risk_regime": "ELEVATED", "underlying_stress": False},
            {"global_risk_regime": "ELEVATED", "underlying_stress": True},
        ):
            decision = _decision(**overrides)
            assert decision.shock_rr_floor >= decision.effective_rr_floor
