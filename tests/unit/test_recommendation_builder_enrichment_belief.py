"""Unit tests for recommendation_builder/validator — enrichment_belief."""

import pytest  # noqa: F401

from tests.unit._fixtures.recommendation_builder import (
    SECTION_MY_HOLDINGS,
    SECTION_TOP_PICKS,
    _default_validator_params,
    _full_pick,
    _position_alert,
    _sector_signal,
    build_structured_recommendations,
    validate_structured_recommendations,
)


class TestCounterThesis:
    """counter_thesis populated from best available source."""

    def test_top_picks_prefers_key_risk(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[_full_pick("FPT")],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["counter_thesis"] == "Sector rotation risk"

    def test_top_picks_falls_back_to_belief_narrative(self):
        pick = _full_pick("FPT")
        pick["key_risk"] = None
        recs = build_structured_recommendations(
            pre_computed_picks=[pick],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["counter_thesis"] == "Strong momentum with volume confirmation"

    def test_position_alert_counter_thesis(self):
        alerts = {"alerts": [_position_alert("TCB", "HOLD")]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["counter_thesis"] == "Banking sector headwinds"

    def test_position_alert_falls_back_to_dissent(self):
        alert = _position_alert("TCB", "HOLD")
        alert["counter_thesis"] = None
        alerts = {"alerts": [alert]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["counter_thesis"] == "Technical: EXIT (weak momentum)"

    def test_sector_signal_counter_thesis_from_key_risk(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", "WATCH")],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["counter_thesis"] == "Rate hike pressure"


class TestAutoHoldEntryPrice:
    """Auto-hold recs get entry_price from holdings dict."""

    def test_auto_hold_gets_avg_cost(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[
                {
                    "ticker": "VNM",
                    "plan_type": "SWING",
                    "avg_cost": 80000,
                    "pct_from_entry": 3.5,
                    "slice_weight_pct": 15.0,
                    "ticker_weight_pct": 15.0,
                }
            ],
            trading_mode=None,
        )
        assert recs[0]["entry_price"] == 80000

    def test_auto_hold_no_holdings_data(self):
        """Edge case: ticker in holdings_tickers but no avg_cost."""
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[{"ticker": "VNM", "plan_type": "SWING"}],
            trading_mode=None,
        )
        assert recs[0]["entry_price"] is None


# ---------------------------------------------------------------------------
# Belief conviction wiring
# ---------------------------------------------------------------------------


class TestBeliefConvictionWiring:
    """belief_conviction populated for all sections when beliefs provided."""

    def test_position_alert_gets_belief_conviction(self):
        beliefs = {"TCB": {"conviction": 0.75, "direction": "BULLISH"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={"alerts": [_position_alert("TCB", "HOLD")]},
            sector_signals=[],
            holdings=[{"ticker": "TCB", "plan_type": "SWING", "avg_cost": 50000}],
            trading_mode=None,
            beliefs_by_ticker=beliefs,
        )
        tcb_rec = next(r for r in recs if r["ticker"] == "TCB")
        assert tcb_rec["belief_conviction"] == 0.75

    def test_sector_signal_gets_belief_conviction(self):
        beliefs = {"VCB": {"conviction": 0.6, "direction": "NEUTRAL"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", "WATCH")],
            holdings=[],
            trading_mode=None,
            beliefs_by_ticker=beliefs,
        )
        assert recs[0]["belief_conviction"] == 0.6

    def test_auto_hold_gets_belief_conviction(self):
        beliefs = {"VNM": {"conviction": 0.55, "direction": "BEARISH"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[{"ticker": "VNM", "plan_type": "SWING", "avg_cost": 80000}],
            trading_mode=None,
            beliefs_by_ticker=beliefs,
        )
        assert recs[0]["belief_conviction"] == 0.55

    def test_no_beliefs_gives_none(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", "WATCH")],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0].get("belief_conviction") is None

    def test_ticker_not_in_beliefs_gives_none(self):
        beliefs = {"FPT": {"conviction": 0.8, "direction": "BULLISH"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", "WATCH")],
            holdings=[],
            trading_mode=None,
            beliefs_by_ticker=beliefs,
        )
        assert recs[0].get("belief_conviction") is None


# ---------------------------------------------------------------------------
# Holdings downgrade: dropped BUY from MY_HOLDINGS → HOLD
# ---------------------------------------------------------------------------


class TestHoldingsDowngrade:
    """When validator drops a BUY_ACTIONS rec from MY_HOLDINGS, downgrade to HOLD."""

    def test_add_missing_stop_downgrades_to_hold(self):
        """ADD from MY_HOLDINGS with no stop → HOLD (not dropped)."""
        recs = [
            {
                "ticker": "FPT",
                "action": "ADD",
                "section": SECTION_MY_HOLDINGS,
                "source": "position_alerts",
                "entry_price": 78000,
                "stop_price": None,
                "target_price": 90000,
                "risk_reward": None,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(),
        )
        fpt_recs = [r for r in validated if r["ticker"] == "FPT"]
        assert len(fpt_recs) == 1
        assert fpt_recs[0]["action"] == "HOLD"
        assert fpt_recs[0]["source"] == "auto_hold"
        assert any("HOLDINGS_DOWNGRADE" in w for w in warnings)

    def test_add_missing_target_downgrades_to_hold(self):
        """ADD from MY_HOLDINGS with no target → HOLD (not dropped)."""
        recs = [
            {
                "ticker": "FPT",
                "action": "ADD",
                "section": SECTION_MY_HOLDINGS,
                "source": "position_alerts",
                "entry_price": 78000,
                "stop_price": 67000,
                "target_price": None,
                "risk_reward": None,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(),
        )
        fpt_recs = [r for r in validated if r["ticker"] == "FPT"]
        assert len(fpt_recs) == 1
        assert fpt_recs[0]["action"] == "HOLD"

    def test_add_missing_entry_downgrades_to_hold(self):
        """ADD from MY_HOLDINGS with no entry → HOLD."""
        recs = [
            {
                "ticker": "FPT",
                "action": "ADD",
                "section": SECTION_MY_HOLDINGS,
                "source": "position_alerts",
                "entry_price": None,
                "stop_price": 67000,
                "target_price": 90000,
                "risk_reward": None,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(),
        )
        fpt_recs = [r for r in validated if r["ticker"] == "FPT"]
        assert len(fpt_recs) == 1
        assert fpt_recs[0]["action"] == "HOLD"

    def test_add_bad_geometry_downgrades_to_hold(self):
        """ADD from MY_HOLDINGS with entry >= target → HOLD."""
        recs = [
            {
                "ticker": "FPT",
                "action": "ADD",
                "section": SECTION_MY_HOLDINGS,
                "source": "position_alerts",
                "entry_price": 90000,
                "stop_price": 80000,
                "target_price": 85000,
                "risk_reward": None,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(),
        )
        fpt_recs = [r for r in validated if r["ticker"] == "FPT"]
        assert len(fpt_recs) == 1
        assert fpt_recs[0]["action"] == "HOLD"

    def test_non_holdings_add_still_dropped(self):
        """ADD from TOP_PICKS with missing stop is dropped normally."""
        recs = [
            {
                "ticker": "VCB",
                "action": "ADD",
                "section": SECTION_TOP_PICKS,
                "entry_price": 60000,
                "stop_price": None,
                "target_price": 70000,
                "risk_reward": None,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(),
        )
        assert len(validated) == 0
        assert any("NO STOP PRICE" in w for w in warnings)

    def test_zero_rr_holdings_add_downgrades(self):
        """ADD from MY_HOLDINGS with R:R=0 → HOLD."""
        recs = [
            {
                "ticker": "TCB",
                "action": "ADD",
                "section": SECTION_MY_HOLDINGS,
                "source": "position_alerts",
                "entry_price": 32000,
                "stop_price": 30000,
                "target_price": 35000,
                "risk_reward": 0,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(),
        )
        tcb_recs = [r for r in validated if r["ticker"] == "TCB"]
        assert len(tcb_recs) == 1
        assert tcb_recs[0]["action"] == "HOLD"
