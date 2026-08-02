"""Unit tests for compound alert evaluation logic."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from alert_evaluation import evaluate_alert, evaluate_single_condition, format_alert_message

# ---------------------------------------------------------------------------
# evaluate_single_condition
# ---------------------------------------------------------------------------


class TestEvaluateSingleCondition:
    def test_price_below_triggered(self):
        hit, val = evaluate_single_condition("price_below", 93000, {"low": 92500}, {})
        assert hit is True
        assert val == 92500.0

    def test_price_below_not_triggered(self):
        hit, val = evaluate_single_condition("price_below", 93000, {"low": 94000}, {})
        assert hit is False
        assert val is None

    def test_price_below_exact_boundary(self):
        hit, val = evaluate_single_condition("price_below", 93000, {"low": 93000}, {})
        assert hit is True

    def test_price_above_triggered(self):
        hit, val = evaluate_single_condition("price_above", 105000, {"high": 105500}, {})
        assert hit is True
        assert val == 105500.0

    def test_price_above_not_triggered(self):
        hit, val = evaluate_single_condition("price_above", 105000, {"high": 104000}, {})
        assert hit is False

    def test_rsi_below_triggered(self):
        hit, val = evaluate_single_condition("rsi_below", 30, {}, {"rsi": 28.4})
        assert hit is True
        assert val == 28.4

    def test_rsi_below_not_triggered(self):
        hit, val = evaluate_single_condition("rsi_below", 30, {}, {"rsi": 32.1})
        assert hit is False

    def test_rsi_above_triggered(self):
        hit, val = evaluate_single_condition("rsi_above", 70, {}, {"rsi": 72.3})
        assert hit is True

    def test_volume_spike_triggered(self):
        hit, val = evaluate_single_condition(
            "volume_spike", 2.0, {"volume": 5_000_000}, {"volume_sma20": 2_000_000}
        )
        assert hit is True
        assert val == pytest.approx(2.5)

    def test_volume_spike_not_triggered(self):
        hit, val = evaluate_single_condition(
            "volume_spike", 2.0, {"volume": 1_000_000}, {"volume_sma20": 2_000_000}
        )
        assert hit is False

    def test_none_value_returns_false(self):
        hit, val = evaluate_single_condition("price_below", None, {"low": 90000}, {})
        assert hit is False

    def test_missing_price_data(self):
        hit, val = evaluate_single_condition("price_below", 93000, {}, {})
        assert hit is False

    def test_unknown_condition_type(self):
        hit, val = evaluate_single_condition("unknown_type", 100, {"close": 90}, {})
        assert hit is False


# ---------------------------------------------------------------------------
# evaluate_alert — ALL logic
# ---------------------------------------------------------------------------


class TestEvaluateAlertAll:
    def _alert(self, conditions, logic="ALL"):
        return {
            "ticker": "TCB",
            "conditions": conditions,
            "condition_logic": logic,
        }

    def _prices(self, **kwargs):
        return {
            "TCB": {
                "open": 33000,
                "high": 33500,
                "low": 32500,
                "close": 33200,
                "volume": 1_000_000,
                **kwargs,
            }
        }

    def _tech(self, **kwargs):
        return {"TCB": {"rsi": 45.0, "volume_sma20": 500_000, **kwargs}}

    def test_single_condition_hit(self):
        alert = self._alert([{"condition_type": "price_below", "condition_value": 33000}])
        triggered, values = evaluate_alert(alert, self._prices(low=32500), {})
        assert triggered is True
        assert values["price_below"] == 32500.0

    def test_all_conditions_must_be_met(self):
        alert = self._alert(
            [
                {"condition_type": "price_below", "condition_value": 33000},
                {"condition_type": "rsi_below", "condition_value": 30},
            ]
        )
        # Price hit but RSI not
        triggered, values = evaluate_alert(alert, self._prices(low=32500), self._tech(rsi=35))
        assert triggered is False
        assert values == {}

    def test_all_conditions_met(self):
        alert = self._alert(
            [
                {"condition_type": "price_below", "condition_value": 33000},
                {"condition_type": "rsi_below", "condition_value": 30},
            ]
        )
        triggered, values = evaluate_alert(alert, self._prices(low=32500), self._tech(rsi=28))
        assert triggered is True
        assert "price_below" in values
        assert "rsi_below" in values

    def test_no_conditions_returns_false(self):
        alert = self._alert([])
        triggered, values = evaluate_alert(alert, self._prices(), {})
        assert triggered is False
        assert values == {}

    def test_missing_ticker_returns_false(self):
        alert = {
            "ticker": "MISSING",
            "conditions": [{"condition_type": "price_below", "condition_value": 93000}],
            "condition_logic": "ALL",
        }
        triggered, values = evaluate_alert(alert, {}, {})
        assert triggered is False


# ---------------------------------------------------------------------------
# evaluate_alert — ANY logic
# ---------------------------------------------------------------------------


class TestEvaluateAlertAny:
    def _alert(self, conditions):
        return {
            "ticker": "FPT",
            "conditions": conditions,
            "condition_logic": "ANY",
        }

    def test_any_one_hit_triggers(self):
        alert = self._alert(
            [
                {"condition_type": "price_below", "condition_value": 90000},
                {"condition_type": "rsi_below", "condition_value": 30},
            ]
        )
        prices = {"FPT": {"low": 89000, "high": 95000}}
        tech = {"FPT": {"rsi": 35}}  # RSI not hit, price hit
        triggered, values = evaluate_alert(alert, prices, tech)
        assert triggered is True
        assert "price_below" in values

    def test_none_hit_returns_false(self):
        alert = self._alert(
            [
                {"condition_type": "price_below", "condition_value": 90000},
                {"condition_type": "rsi_below", "condition_value": 30},
            ]
        )
        prices = {"FPT": {"low": 92000, "high": 95000}}
        tech = {"FPT": {"rsi": 35}}
        triggered, values = evaluate_alert(alert, prices, tech)
        assert triggered is False


# ---------------------------------------------------------------------------
# format_alert_message
# ---------------------------------------------------------------------------


class TestFormatAlertMessage:
    def _alert(self, conditions, logic="ALL", **extra):
        return {
            "ticker": "VHM",
            "conditions": conditions,
            "condition_logic": logic,
            "recommended_action": "BUY",
            "priority": "normal",
            "rationale": "Strong support bounce.",
            "source": "morning_brief",
            "source_date": "2026-02-19",
            **extra,
        }

    def test_single_condition_format(self):
        alert = self._alert([{"condition_type": "price_below", "condition_value": 93000}])
        msg = format_alert_message(alert, {"price_below": 92500.0})
        assert "VHM" in msg
        assert "BUY" in msg
        assert "price below" in msg.lower() or "price_below" in msg
        assert "92500" in msg

    def test_compound_condition_format(self):
        alert = self._alert(
            [
                {"condition_type": "price_below", "condition_value": 93000},
                {"condition_type": "rsi_below", "condition_value": 30},
            ]
        )
        msg = format_alert_message(alert, {"price_below": 92500.0, "rsi_below": 28.4})
        assert "ALL" in msg or "all" in msg.lower()
        assert "93000" in msg or "92500" in msg

    def test_high_priority_emoji(self):
        alert = self._alert(
            [{"condition_type": "price_below", "condition_value": 29000}],
            priority="high",
        )
        msg = format_alert_message(alert, {"price_below": 28900.0})
        assert "🔴" in msg

    def test_rationale_included(self):
        alert = self._alert([{"condition_type": "price_above", "condition_value": 100000}])
        msg = format_alert_message(alert, {"price_above": 100500.0})
        assert "Strong support bounce" in msg
