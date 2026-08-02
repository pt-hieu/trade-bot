"""Unit tests for recommendation_builder/validator — build_holds_sector."""

import pytest  # noqa: F401

from tests.unit._fixtures.recommendation_builder import (
    SECTION_LONG_TERM,
    SECTION_MY_HOLDINGS,
    SECTION_SKIP_THESE,
    SECTION_TOP_PICKS,
    SECTION_WHAT_TO_DO,
    _full_pick,
    _position_alert,
    _sector_signal,
    build_structured_recommendations,
)


class TestAutoHold:
    """Holdings not in position_alerts get auto-HOLD recs."""

    def test_auto_hold_for_uncovered_holding(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[
                {
                    "ticker": "VNM",
                    "avg_cost": 80000,
                    "pct_from_entry": 3.5,
                    "slice_weight_pct": 15.0,
                    "ticker_weight_pct": 15.0,
                    "plan_type": "SWING",
                }
            ],
            trading_mode=None,
        )
        assert len(recs) == 1
        rec = recs[0]
        assert rec["ticker"] == "VNM"
        assert rec["action"] == "HOLD"
        assert rec["section"] == SECTION_MY_HOLDINGS
        assert rec["source"] == "auto_hold"

    def test_no_auto_hold_when_alert_already_covers_ticker(self):
        alerts = {"alerts": [_position_alert("VNM", "EXIT")]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[
                {
                    "ticker": "VNM",
                    "avg_cost": 80000,
                    "pct_from_entry": 3.5,
                    "slice_weight_pct": 15.0,
                    "ticker_weight_pct": 15.0,
                    "plan_type": "SWING",
                }
            ],
            trading_mode=None,
        )
        vnm_recs = [r for r in recs if r["ticker"] == "VNM"]
        assert len(vnm_recs) == 1
        assert vnm_recs[0]["action"] == "EXIT"  # alert wins; no duplicate auto-hold

    def test_auto_hold_only_for_uncovered_subset(self):
        alerts = {"alerts": [_position_alert("TCB", "HOLD")]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[
                {
                    "ticker": "TCB",
                    "avg_cost": 50000,
                    "pct_from_entry": 2.0,
                    "slice_weight_pct": 20.0,
                    "ticker_weight_pct": 20.0,
                    "plan_type": "SWING",
                },
                {
                    "ticker": "VNM",
                    "avg_cost": 80000,
                    "pct_from_entry": 3.5,
                    "slice_weight_pct": 15.0,
                    "ticker_weight_pct": 15.0,
                    "plan_type": "SWING",
                },
            ],
            trading_mode=None,
        )
        vnm_recs = [r for r in recs if r["ticker"] == "VNM"]
        assert len(vnm_recs) == 1
        assert vnm_recs[0]["source"] == "auto_hold"

    def test_auto_hold_inherits_longterm_plan_type(self):
        """After migration 318 FPT is LONGTERM-only; auto-HOLD rec must carry
        plan_type=LONGTERM, not default to SWING via the watchlist heuristic.
        """
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[
                {
                    "ticker": "FPT",
                    "avg_cost": 81500,
                    "pct_from_entry": -11.6,
                    "slice_weight_pct": 30.0,
                    "ticker_weight_pct": 30.0,
                    "plan_type": "LONGTERM",
                }
            ],
            trading_mode=None,
        )
        fpt = [r for r in recs if r["ticker"] == "FPT"][0]
        assert fpt["plan_type"] == "LONGTERM"
        assert fpt["source"] == "auto_hold"

    def test_position_alert_inherits_longterm_plan_type(self):
        """TCB LONGTERM with a position alert must retain plan_type=LONGTERM."""
        alerts = {"alerts": [_position_alert("TCB", "HOLD")]}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts=alerts,
            sector_signals=[],
            holdings=[
                {
                    "ticker": "TCB",
                    "avg_cost": 25000,
                    "pct_from_entry": 6.0,
                    "slice_weight_pct": 20.0,
                    "ticker_weight_pct": 20.0,
                    "plan_type": "LONGTERM",
                }
            ],
            trading_mode=None,
        )
        tcb = [r for r in recs if r["ticker"] == "TCB"][0]
        assert tcb["plan_type"] == "LONGTERM"
        assert tcb["source"] == "position_alerts"


class TestBuildFromSectorSignals:
    """Non-BUY sector signals map to SKIP_THESE or WHAT_TO_DO."""

    @pytest.mark.parametrize(
        "signal, expected_action, expected_section",
        [
            ("AVOID", "SKIP", SECTION_SKIP_THESE),
            ("SKIP", "SKIP", SECTION_SKIP_THESE),
            ("WATCH", "WATCH", SECTION_WHAT_TO_DO),
            ("WAIT", "WAIT", SECTION_WHAT_TO_DO),
        ],
    )
    def test_signal_mapping(self, signal, expected_action, expected_section):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", signal)],
            holdings=[],
            trading_mode=None,
        )
        assert len(recs) == 1
        rec = recs[0]
        assert rec["ticker"] == "VCB"
        assert rec["action"] == expected_action
        assert rec["section"] == expected_section
        assert rec["source"] == "sector_signals"

    def test_buy_signal_skipped(self):
        """BUY sector signals are ignored — handled only via picks."""
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", "BUY")],
            holdings=[],
            trading_mode=None,
        )
        assert len(recs) == 0

    def test_unknown_signal_defaults_to_watch(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[_sector_signal("VCB", "UNKNOWN_SIGNAL")],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["action"] == "WATCH"
        assert recs[0]["section"] == SECTION_WHAT_TO_DO

    def test_plan_shape_forced_none_when_setup_invalid(self):
        """Regression for 2026-05-07 0-rec wipeout: a sector WATCH/WAIT row
        with a non-NONE plan_shape but no usable setup geometry violates
        daily_recs_plan_shape_action_chk (migration 342) and rolls back
        the whole executemany batch. The builder must coerce plan_shape
        to 'NONE' whenever it cannot also ship a trigger_price.
        """
        signal = _sector_signal("VCB", "WATCH")
        signal["plan_shape"] = "BREAKOUT"  # LLM-emitted shape
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[signal],
            holdings=[],
            trading_mode=None,
            trade_setups_by_ticker={"VCB": {"setup_state": "invalid"}},
        )
        assert len(recs) == 1
        rec = recs[0]
        assert rec["action"] == "WATCH"
        assert rec["plan_shape"] == "NONE"
        assert rec.get("trigger_price") in (None, 0)

    def test_plan_shape_preserved_when_setup_triggered(self):
        """Companion to test_plan_shape_forced_none_when_setup_invalid:
        with a triggered setup, plan_shape must survive and trigger_price
        must be populated so the CHECK constraint passes.
        """
        signal = _sector_signal("VCB", "WATCH")
        signal["plan_shape"] = "BREAKOUT"
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[signal],
            holdings=[],
            trading_mode=None,
            trade_setups_by_ticker={
                "VCB": {
                    "setup_state": "triggered",
                    "trigger_price": 50000,
                    "stop": 48000,
                    "target": 55000,
                    "risk_reward": 2.5,
                }
            },
        )
        assert recs[0]["plan_shape"] == "BREAKOUT"
        assert recs[0]["trigger_price"] == 50000


class TestBuildLongterm:
    """Longterm watchlist tickers map to LONG_TERM section."""

    def test_longterm_ticker_in_long_term_section(self):
        watchlist = {"HPG": {"entry_zone": 28000, "conviction": "High"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
            longterm_watchlist=watchlist,
        )
        assert len(recs) == 1
        rec = recs[0]
        assert rec["ticker"] == "HPG"
        assert rec["action"] == "WATCH"
        assert rec["section"] == SECTION_LONG_TERM
        assert rec["source"] == "longterm"
        assert rec["entry_price"] == 28000

    def test_entry_zone_as_entry_price(self):
        watchlist = {"HPG": {"entry_zone": 30000, "conviction": "Medium"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
            longterm_watchlist=watchlist,
        )
        assert recs[0]["entry_price"] == 30000

    def test_zero_entry_zone_produces_none_entry_price(self):
        watchlist = {"HPG": {"entry_zone": 0, "conviction": "Low"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
            longterm_watchlist=watchlist,
        )
        assert recs[0]["entry_price"] is None

    def test_longterm_ticker_not_duplicated_when_in_picks(self):
        watchlist = {"FPT": {"entry_zone": 130000, "conviction": "High"}}
        recs = build_structured_recommendations(
            pre_computed_picks=[_full_pick("FPT")],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
            longterm_watchlist=watchlist,
        )
        fpt_recs = [r for r in recs if r["ticker"] == "FPT"]
        assert len(fpt_recs) == 1
        assert fpt_recs[0]["section"] == SECTION_TOP_PICKS  # picks wins


class TestBuilderDedup:
    """Same ticker in picks AND sector_signals — picks wins (seen first)."""

    def test_picks_wins_over_sector_signals(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[_full_pick("FPT")],
            position_alerts={},
            sector_signals=[_sector_signal("FPT", "WATCH")],
            holdings=[],
            trading_mode=None,
        )
        fpt_recs = [r for r in recs if r["ticker"] == "FPT"]
        assert len(fpt_recs) == 1
        assert fpt_recs[0]["action"] == "BUY"
        assert fpt_recs[0]["source"] == "picks"


# ---------------------------------------------------------------------------
# validate_structured_recommendations — validator tests
# ---------------------------------------------------------------------------
