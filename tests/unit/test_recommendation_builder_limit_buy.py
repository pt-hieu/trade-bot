"""Unit tests for recommendation_builder/validator — limit_buy."""

import pytest  # noqa: F401

from tests.unit._fixtures.recommendation_builder import (
    SECTION_TOP_PICKS,
    _default_validator_params,
    _full_pick,
    build_structured_recommendations,
    validate_structured_recommendations,
)


class TestLimitBuyPicks:
    """LIMIT_BUY action from picks flows through builder and validator."""

    def _limit_buy_pick(self, ticker="TPB") -> dict:
        pick = _full_pick(ticker)
        pick["action"] = "LIMIT_BUY"
        pick["gap_from_support_pct"] = 6.0
        pick["market_rr"] = 0.3
        return pick

    def test_limit_buy_action_flows_through(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[self._limit_buy_pick()],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert len(recs) == 1
        assert recs[0]["action"] == "LIMIT_BUY"
        assert recs[0]["section"] == SECTION_TOP_PICKS
        assert recs[0]["source"] == "picks"

    def test_limit_buy_rationale_includes_gap(self):
        recs = build_structured_recommendations(
            pre_computed_picks=[self._limit_buy_pick()],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        rationale = recs[0]["rationale"]
        assert "LIMIT ORDER" in rationale
        assert "6.0%" in rationale
        assert "0.3" in rationale

    def test_no_action_defaults_to_buy(self):
        pick = _full_pick("FPT")
        del pick["action"]
        assert "action" not in pick
        recs = build_structured_recommendations(
            pre_computed_picks=[pick],
            position_alerts={},
            sector_signals=[],
            holdings=[],
            trading_mode=None,
        )
        assert recs[0]["action"] == "BUY"

    def test_limit_buy_counts_against_max_picks(self):
        recs = [
            {
                "ticker": "TPB",
                "action": "LIMIT_BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 15100,
                "stop_price": 14798,
                "target_price": 16410,
                "risk_reward": 4.3,
            },
            {
                "ticker": "FPT",
                "action": "BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 135000,
                "stop_price": 130000,
                "target_price": 145000,
                "risk_reward": 3.3,
            },
        ]
        validated, _ = validate_structured_recommendations(
            recs,
            **_default_validator_params(max_picks=1),
        )
        buy_actions = [r for r in validated if r["action"] in ("BUY", "LIMIT_BUY")]
        assert len(buy_actions) == 1

    def test_low_cash_drops_limit_buy(self):
        recs = [
            {
                "ticker": "TPB",
                "action": "LIMIT_BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 15100,
                "stop_price": 14798,
                "target_price": 16410,
                "risk_reward": 4.3,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(trading_mode={"mode": "LOW_CASH"}, deployable_cash=0),
        )
        assert len(validated) == 0
        assert any("LOW_CASH" in w for w in warnings)


# ---------------------------------------------------------------------------
# New enrichment fields — verdict, counter_thesis, strategy_confidence, entry_price
# ---------------------------------------------------------------------------
