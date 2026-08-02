"""Unit tests for recommendation_builder/validator — validation_geometry."""

import pytest  # noqa: F401

from tests.unit._fixtures.recommendation_builder import (
    SECTION_MY_HOLDINGS,
    SECTION_TOP_PICKS,
    _default_validator_params,
    validate_structured_recommendations,
)


class TestValidatorGeometry:
    """stop >= entry drops the rec with a warning."""

    def test_stop_above_entry_dropped(self):
        recs = [
            {
                "ticker": "FPT",
                "action": "BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 130000,
                "stop_price": 135000,
                "target_price": 145000,
                "risk_reward": 3.3,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs, **_default_validator_params()
        )
        assert len(validated) == 0
        assert any("GEOMETRY" in w for w in warnings)

    def test_stop_equal_entry_dropped(self):
        recs = [
            {
                "ticker": "FPT",
                "action": "BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 135000,
                "stop_price": 135000,
                "target_price": 145000,
                "risk_reward": 3.3,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs, **_default_validator_params()
        )
        assert len(validated) == 0
        assert any("GEOMETRY" in w for w in warnings)

    def test_valid_geometry_passes(self):
        recs = [
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
        validated, warnings = validate_structured_recommendations(
            recs, **_default_validator_params()
        )
        assert len(validated) == 1


class TestValidatorNonBuyGeometry:
    """Non-BUY recs with inverted target get warning but are NOT dropped."""

    def test_hold_inverted_target_warns_but_keeps(self):
        recs = [
            {
                "ticker": "TCB",
                "action": "HOLD",
                "section": SECTION_MY_HOLDINGS,
                "entry_price": 32500,
                "stop_price": 26000,
                "target_price": 32000,
                "risk_reward": 0,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs, **_default_validator_params()
        )
        assert len(validated) == 1, "HOLD rec must NOT be dropped"
        assert any("GEOMETRY" in w and "TCB" in w and "HOLD" in w for w in warnings)

    def test_hold_valid_geometry_no_warning(self):
        recs = [
            {
                "ticker": "TCB",
                "action": "HOLD",
                "section": SECTION_MY_HOLDINGS,
                "entry_price": 32500,
                "stop_price": 26000,
                "target_price": 38000,
                "risk_reward": 0,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs, **_default_validator_params()
        )
        assert len(validated) == 1
        assert not any("GEOMETRY" in w and "TCB" in w for w in warnings)


class TestValidatorMaxPicks:
    """More BUY recs than max_picks → excess dropped."""

    def _make_buy(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "action": "BUY",
            "section": SECTION_TOP_PICKS,
            "entry_price": 100000,
            "stop_price": 95000,
            "target_price": 120000,
            "risk_reward": 4.0,
        }

    def test_excess_buys_dropped(self):
        tickers = ["FPT", "VCB", "TCB", "HPG", "MWG"]
        recs = [self._make_buy(t) for t in tickers]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(max_picks=3),
        )
        buy_recs = [r for r in validated if r["action"] == "BUY"]
        assert len(buy_recs) == 3
        assert any("MAX PICKS" in w for w in warnings)

    def test_exactly_max_picks_all_pass(self):
        tickers = ["FPT", "VCB", "TCB"]
        recs = [self._make_buy(t) for t in tickers]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(max_picks=3),
        )
        buy_recs = [r for r in validated if r["action"] == "BUY"]
        assert len(buy_recs) == 3
        assert not any("MAX PICKS" in w for w in warnings)

    def test_non_buy_recs_unaffected_by_max_picks(self):
        tickers = ["FPT", "VCB", "TCB", "HPG", "MWG"]
        recs = [self._make_buy(t) for t in tickers]
        hold_rec = {"ticker": "VNM", "action": "HOLD", "section": SECTION_MY_HOLDINGS}
        recs.append(hold_rec)
        validated, _ = validate_structured_recommendations(
            recs,
            **_default_validator_params(max_picks=2),
        )
        assert any(r["ticker"] == "VNM" and r["action"] == "HOLD" for r in validated)


# ---------------------------------------------------------------------------
# LIMIT_BUY action flow — builder + validator
# ---------------------------------------------------------------------------
