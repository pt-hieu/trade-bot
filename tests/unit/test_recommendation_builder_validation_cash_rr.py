"""Unit tests for recommendation_builder/validator — validation_cash_rr."""

import pytest  # noqa: F401

from tests.unit._fixtures.recommendation_builder import (
    SECTION_MY_HOLDINGS,
    SECTION_SKIP_THESE,
    SECTION_TOP_PICKS,
    _default_validator_params,
    validate_structured_recommendations,
)


class TestValidatorLowCash:
    """LOW_CASH mode + zero deployable drops all BUY recs."""

    def test_low_cash_drops_buy_recs(self):
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
            {"ticker": "TCB", "action": "HOLD", "section": SECTION_MY_HOLDINGS},
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(trading_mode={"mode": "LOW_CASH"}, deployable_cash=0),
        )
        actions = [r["action"] for r in validated]
        assert "BUY" not in actions
        assert "HOLD" in actions
        assert any("LOW_CASH" in w for w in warnings)

    def test_normal_mode_keeps_buy_recs(self):
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
            recs,
            **_default_validator_params(
                trading_mode={"mode": "NORMAL"}, deployable_cash=50_000_000
            ),
        )
        assert validated[0]["action"] == "BUY"


class TestValidatorReallocation:
    """REALLOCATION mode requires EXIT in MY_HOLDINGS for BUY to pass."""

    def test_reallocation_without_exit_drops_buy(self):
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
            {"ticker": "TCB", "action": "HOLD", "section": SECTION_MY_HOLDINGS},
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(trading_mode={"mode": "REALLOCATION"}, deployable_cash=0),
        )
        actions = [r["action"] for r in validated]
        assert "BUY" not in actions
        assert any("REALLOCATION" in w for w in warnings)

    def test_reallocation_with_exit_allows_buy(self):
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
            {"ticker": "TCB", "action": "EXIT", "section": SECTION_MY_HOLDINGS},
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(
                trading_mode={"mode": "REALLOCATION"}, deployable_cash=50_000_000
            ),
        )
        actions = [r["action"] for r in validated]
        assert "BUY" in actions


class TestValidatorRRFloor:
    """BUY recs below R:R floor are dropped."""

    def test_rr_below_floor_dropped(self):
        recs = [
            {
                "ticker": "FPT",
                "action": "BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 135000,
                "stop_price": 130000,
                "target_price": 145000,
                "risk_reward": 1.5,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(min_rr=3.0),
        )
        assert len(validated) == 0
        assert any("R:R FLOOR" in w for w in warnings)

    def test_rr_at_floor_passes(self):
        recs = [
            {
                "ticker": "FPT",
                "action": "BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 135000,
                "stop_price": 130000,
                "target_price": 145000,
                "risk_reward": 3.0,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(min_rr=3.0),
        )
        assert len(validated) == 1

    def test_rr_zero_is_dropped(self):
        """rec with risk_reward=0 is dropped — zero R:R means no valid setup."""
        recs = [
            {
                "ticker": "FPT",
                "action": "BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 135000,
                "stop_price": 130000,
                "target_price": 145000,
                "risk_reward": 0,
            },
        ]
        validated, warnings = validate_structured_recommendations(
            recs,
            **_default_validator_params(min_rr=3.0),
        )
        assert len(validated) == 0
        # SWI-340: ZERO R:R rolled into EXIT CONTRACT helper. Same drop, new label.
        assert any("EXIT CONTRACT" in w and "risk_reward=0" in w for w in warnings)


class TestValidatorCrossSectionDedup:
    """BUY + SKIP same ticker → SKIP wins."""

    def test_skip_wins_over_buy(self):
        recs = [
            {
                "ticker": "VCB",
                "action": "BUY",
                "section": SECTION_TOP_PICKS,
                "entry_price": 80000,
                "stop_price": 77000,
                "target_price": 90000,
                "risk_reward": 3.3,
            },
            {"ticker": "VCB", "action": "SKIP", "section": SECTION_SKIP_THESE},
        ]
        validated, warnings = validate_structured_recommendations(
            recs, **_default_validator_params()
        )
        vcb_recs = [r for r in validated if r["ticker"] == "VCB"]
        assert len(vcb_recs) == 1
        assert vcb_recs[0]["action"] == "SKIP"
        assert any("CROSS-SECTION" in w for w in warnings)
