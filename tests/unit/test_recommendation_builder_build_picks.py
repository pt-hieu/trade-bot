"""Unit tests for recommendation_builder/validator — build_picks."""

import pytest  # noqa: F401

from tests.unit._fixtures.recommendation_builder import (
    SECTION_MY_HOLDINGS,
    SECTION_TOP_PICKS,
    _full_pick,
    _position_alert,
    build_structured_recommendations,
)


class TestBuildFromPicks:
    """BUY recs sourced from pre_computed_picks."""

    def test_all_29_fields_mapped(self):
        pick = _full_pick("FPT")
        recs = build_structured_recommendations(
            pre_computed_picks=[pick],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )

        assert len(recs) == 1
        rec = recs[0]
        assert rec["ticker"] == "FPT"
        assert rec["action"] == "BUY"
        assert rec["section"] == SECTION_TOP_PICKS
        assert rec["source"] == "picks"
        assert rec["entry_price"] == 135000
        assert rec["stop_price"] == 130000
        assert rec["target_price"] == 145000
        assert rec["size_shares"] == 100
        assert rec["risk_reward"] == 3.3
        assert rec["target_basis"] == "conservative"
        assert rec["rr_stretch"] == 4.0
        # Dual rr fields no longer surface on the rec dict
        assert "conservative_target_vnd" not in rec
        assert "conservative_rr" not in rec
        assert "aggressive_target_vnd" not in rec
        assert "aggressive_rr" not in rec
        assert rec["strategy"] == "BOUNCE"
        assert rec["strategy_confidence"] == 0.85
        assert "BUY at 135.0k" in rec["verdict"]
        assert "R:R 3.3:1" in rec["verdict"]
        assert rec["sim_ev"] == 2.3
        assert rec["sim_p_target"] == 0.65
        assert rec["sim_p_stop"] == 0.25
        assert rec["volume_vs_avg"] == 1.5
        assert rec["volume_confirmed"] is True
        assert rec["pattern_name"] == "hammer"
        assert rec["belief_conviction"] == 0.7
        assert (
            rec["counter_thesis"] == "Sector rotation risk"
        )  # key_risk preferred over belief_narrative
        assert rec["rationale"] == "Strong breakout signal"

    def test_ticker_uppercased(self):
        pick = _full_pick("fpt")
        recs = build_structured_recommendations(
            pre_computed_picks=[pick],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["ticker"] == "FPT"

    def test_empty_picks_produces_no_buy_recs(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert all(rec["action"] != "BUY" for rec in recs)


class TestBuildFromPositionAlerts:
    """HOLD/EXIT/TRIM from position_alerts go to MY_HOLDINGS."""

    @pytest.mark.parametrize("action", ["HOLD", "EXIT", "TRIM"])
    def test_action_in_my_holdings(self, action):
        alerts = {"alerts": [_position_alert("TCB", action)]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert len(recs) == 1
        rec = recs[0]
        assert rec["ticker"] == "TCB"
        assert rec["action"] == action
        assert rec["section"] == SECTION_MY_HOLDINGS
        assert rec["source"] == "position_alerts"

    def test_entry_price_from_holdings_over_llm_string(self):
        """Authoritative avg_cost from holdings takes precedence over LLM string."""
        alerts = {"alerts": [_position_alert("TCB", "HOLD")]}
        holdings = [
            {
                "ticker": "TCB",
                "plan_type": "SWING",
                "avg_cost": 51000,
                "pct_from_entry": 2.0,
                "slice_weight_pct": 20.0,
                "ticker_weight_pct": 20.0,
            }
        ]
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=holdings,
            trading_mode=None,
        )
        rec = recs[0]
        assert rec["entry_price"] == 51000  # from holdings, not LLM's "50k"
        assert rec["stop_price"] == 48000
        assert rec["target_price"] == 55000

    def test_entry_price_falls_back_to_llm_when_no_holdings(self):
        """Falls back to LLM-parsed price when ticker not in holdings."""
        alerts = {"alerts": [_position_alert("TCB", "HOLD")]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        rec = recs[0]
        assert rec["entry_price"] == 50000  # from LLM string "50k"

    def test_rationale_from_reason_field(self):
        alerts = {"alerts": [_position_alert("TCB", "HOLD")]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["rationale"] == "Price consolidating near support"

    def test_invalid_action_defaults_to_hold(self):
        alert = {**_position_alert("TCB"), "action": "BOGUS_ACTION"}
        alerts = {"alerts": [alert]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["action"] == "HOLD"
