"""Brief/validator R:R consistency — single derivation path via the composer.

Before 2026-04-20 the brief renderer interpolated `min_rr_floor=2.0` while
the validator simultaneously enforced `rr_floor=3.0` (ELEVATED regime
boost). Today both reads flow from the same
`RecommendationGateDecision.effective_rr_floor`, so drift is structurally
impossible. This test pins the invariant.
"""

from __future__ import annotations

from pipeline.recommendation_validator import validate_structured_recommendations
from pipeline.rendering.models import HoldingAction
from pipeline.rendering.what_to_do_today import render_what_to_do_today
from shared.rules.recommendation_gate import compose_recommendation_gate


def _decision(**overrides):
    base: dict = {
        "trading_mode": "NORMAL",
        "market_regime": "NEUTRAL",
        "global_risk_regime": "ELEVATED",
        "urgency_tier": "NORMAL",
        "urgency_min_rr": 2.5,
        "urgency_max_picks": 3,
        "underlying_stress": False,
    }
    base.update(overrides)
    return compose_recommendation_gate(**base)


class TestFloorFlowsFromSingleSource:
    """Renderer and validator read the same float from gate_decision."""

    def test_elevated_shock_only_matches(self):
        decision = _decision(underlying_stress=False)
        assert decision.effective_rr_floor == 2.5

        # Validator honors decision.effective_rr_floor on R:R check.
        below_floor = [
            {
                "ticker": "HPG",
                "action": "BUY",
                "section": "TOP_PICKS",
                "entry_price": 21000,
                "stop_price": 20000,
                "target_price": 22300,
                "risk_reward": 2.3,
            }
        ]
        validated, warnings = validate_structured_recommendations(
            recs=below_floor,
            trading_mode={"mode": "NORMAL"},
            deployable_cash=50_000_000,
            gate_decision=decision,
        )
        assert all(r["action"] != "BUY" for r in validated)
        assert any("2.5" in w for w in warnings)

        # Renderer interpolates the same float.
        brief = render_what_to_do_today(
            holdings_actions=[],
            top_picks=[],
            min_rr_floor=decision.effective_rr_floor,
        )
        assert "R:R >= 2.5" in brief

    def test_elevated_stressed_full_floor_matches(self):
        decision = _decision(underlying_stress=True)
        assert decision.effective_rr_floor == 3.0

        brief = render_what_to_do_today(
            holdings_actions=[], top_picks=[], min_rr_floor=decision.effective_rr_floor
        )
        assert "R:R >= 3.0" in brief

        at_two_five = [
            {
                "ticker": "VPB",
                "action": "BUY",
                "section": "TOP_PICKS",
                "entry_price": 19000,
                "stop_price": 18000,
                "target_price": 21500,
                "risk_reward": 2.5,
            }
        ]
        validated, warnings = validate_structured_recommendations(
            recs=at_two_five,
            trading_mode={"mode": "NORMAL"},
            deployable_cash=50_000_000,
            gate_decision=decision,
        )
        assert all(r["action"] != "BUY" for r in validated)
        assert any("3.0" in w for w in warnings)

    def test_calm_default_floor_matches(self):
        decision = _decision(global_risk_regime="CALM")
        assert decision.effective_rr_floor == 2.5

        brief = render_what_to_do_today(
            holdings_actions=[HoldingAction(ticker="FPT", verb="HOLD")],
            top_picks=[],
            min_rr_floor=decision.effective_rr_floor,
        )
        assert "R:R >= 2.5" in brief
