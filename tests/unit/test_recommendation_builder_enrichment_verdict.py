"""Unit tests for recommendation_builder/validator — enrichment_verdict."""

import pytest  # noqa: F401

from tests.unit._fixtures.recommendation_builder import (
    _full_pick,
    _position_alert,
    _sector_signal,
    build_structured_recommendations,
)


class TestVerdictSentences:
    """Verdict is a deterministic actionable sentence per section."""

    def test_top_picks_verdict_format(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[_full_pick("FPT")],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        verdict = recs[0]["verdict"]
        assert "BUY at 135.0k" in verdict
        assert "target 145.0k" in verdict
        assert "stop 130.0k" in verdict
        assert "R:R 3.3:1" in verdict

    def test_limit_buy_verdict_format(self):
        pick = _full_pick("TPB")
        pick["action"] = "LIMIT_BUY"
        recs = build_structured_recommendations(
            pre_computed_picks=[pick],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert "LIMIT BUY at" in recs[0]["verdict"]

    def test_my_holdings_hold_verdict(self):
        alerts = {"alerts": [_position_alert("TCB", "HOLD")]}
        holdings = [
            {
                "ticker": "TCB",
                "plan_type": "SWING",
                "avg_cost": 50000,
                "pct_from_entry": 4.3,
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
        assert "HOLD" in recs[0]["verdict"]
        assert "4.3%" in recs[0]["verdict"]

    def test_auto_hold_verdict(self):
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
        verdict = recs[0]["verdict"]
        assert "HOLD" in verdict
        assert "no alert triggered" in verdict
        assert "3.5%" in verdict

    def test_sector_signal_verdict(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", "WATCH")],
            holdings=[],
            trading_mode=None,
        )
        verdict = recs[0]["verdict"]
        assert "WATCH" in verdict
        assert "Near resistance" in verdict

    def test_longterm_verdict(self):
        watchlist = {"HPG": {"entry_zone": 28000, "conviction": "High"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
            longterm_watchlist=watchlist,
        )
        verdict = recs[0]["verdict"]
        assert "WATCH" in verdict
        assert "28.0k" in verdict
        assert "High" in verdict


class TestStrategyConfidence:
    """strategy_confidence is set for all sections."""

    def test_top_picks_keeps_classifier_confidence(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[_full_pick("FPT")],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["strategy_confidence"] == 0.85

    def test_position_alert_maps_consensus(self):
        alerts = {"alerts": [_position_alert("TCB", "HOLD")]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["strategy_confidence"] == 0.7  # majority → 0.7

    def test_auto_hold_default_confidence(self):
        """Auto-hold uses accuracy_discounted_confidence('no_data', None) = 0.3."""
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
        assert recs[0]["strategy_confidence"] == 0.3  # CONSENSUS_CONFIDENCE["no_data"]

    def test_auto_hold_confidence_discounted_by_calibration(self):
        """With poor calibration stats, auto-hold confidence drops below 0.3."""
        calibration_stats = {
            "positions_technical": {"direction_accuracy": 0.33},  # random chance
            "positions_value": {"direction_accuracy": 0.33},
        }
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
            calibration_stats=calibration_stats,
        )
        # no_data base=0.3, random-chance discount=0.5 → 0.15
        assert recs[0]["strategy_confidence"] == 0.15

    def test_sector_signal_maps_confidence(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", "WATCH")],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["strategy_confidence"] == 0.5  # MEDIUM → 0.5 (from belief_mapping)

    def test_longterm_maps_conviction(self):
        watchlist = {"HPG": {"entry_zone": 28000, "conviction": "High"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
            longterm_watchlist=watchlist,
        )
        assert recs[0]["strategy_confidence"] == 0.8  # high → 0.8 (from belief_mapping)
