"""Unit tests for alert registration tool validation guards."""

import os
import sys
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from agents.tools.alerts import _round_condition_value, tool_register_alert

# Common test fixtures
_SOURCE = "morning_brief"
_DATE = date(2026, 3, 6)
_COND_PRICE_BELOW = [{"type": "price_below", "value": 93000}]
_HOLDINGS = [
    {"ticker": "AAA", "plan_type": "SWING", "shares": 300},
    {"ticker": "BBB", "plan_type": "SWING", "shares": 200},
    {"ticker": "CCC", "plan_type": "SWING", "shares": 100},
]


def _mock_active_alerts(alerts=None):
    """Return mock active alerts with conditions."""
    return alerts or []


def _active_alert(ticker, action, cond_type, cond_value, alert_id=1):
    """Build a mock active alert dict."""
    return {
        "id": alert_id,
        "ticker": ticker,
        "recommended_action": action,
        "conditions": [{"condition_type": cond_type, "condition_value": str(cond_value)}],
    }


# ---------------------------------------------------------------------------
# _round_condition_value
# ---------------------------------------------------------------------------


class TestRoundConditionValue:
    def test_price_rounds_to_integer(self):
        assert _round_condition_value("price_below", 106000.0000001) == 106000.0
        assert _round_condition_value("price_above", 93000.999) == 93001.0

    def test_rsi_rounds_to_one_decimal(self):
        assert _round_condition_value("rsi_below", 28.456) == 28.5

    def test_volume_rounds_to_two_decimals(self):
        assert _round_condition_value("volume_spike", 2.5678) == 2.57

    def test_none_returns_none(self):
        assert _round_condition_value("price_below", None) is None

    def test_casts_numpy_like_types(self):
        # Simulates numpy.float64 by using a subclass
        class FakeFloat(float):
            pass

        result = _round_condition_value("price_below", FakeFloat(93000.5))
        assert result == 93000.0
        assert type(result) is float


# ---------------------------------------------------------------------------
# Action validation
# ---------------------------------------------------------------------------


class TestActionValidation:
    @pytest.mark.asyncio
    async def test_invalid_action_rejected(self):
        result = await tool_register_alert(
            "TCB",
            _COND_PRICE_BELOW,
            "SELL",
            "test",
            source=_SOURCE,
            source_date=_DATE,
        )
        assert "not valid" in result
        assert "SELL" in result

    @pytest.mark.asyncio
    async def test_valid_actions_accepted(self):
        """BUY should pass action validation (may fail later on other checks)."""
        with (
            patch(
                "agents.tools.alerts.get_active_alerts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "agents.tools.alerts.db_register_alert",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            result = await tool_register_alert(
                "TCB",
                [{"type": "price_below", "value": 93000}],
                "BUY",
                "test",
                source=_SOURCE,
                source_date=_DATE,
            )
            assert "registered" in result.lower() or "Alert #" in result


# ---------------------------------------------------------------------------
# Holdings check
# ---------------------------------------------------------------------------


class TestHoldingsCheck:
    @pytest.mark.asyncio
    async def test_trim_non_held_ticker_rejected(self):
        with patch(
            "shared.neon.portfolio.get_portfolio_holdings",
            new_callable=AsyncMock,
            return_value=_HOLDINGS,
        ):
            result = await tool_register_alert(
                "GAS",
                _COND_PRICE_BELOW,
                "TRIM",
                "test",
                source=_SOURCE,
                source_date=_DATE,
                stop_price=90000,
            )
            assert "not in portfolio" in result

    @pytest.mark.asyncio
    async def test_trim_held_ticker_passes(self):
        with (
            patch(
                "shared.neon.portfolio.get_portfolio_holdings",
                new_callable=AsyncMock,
                return_value=_HOLDINGS,
            ),
            patch(
                "agents.tools.alerts.get_active_alerts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "agents.tools.alerts.db_register_alert",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            result = await tool_register_alert(
                "AAA",
                [{"type": "price_below", "value": 84000}],
                "TRIM",
                "test",
                source=_SOURCE,
                source_date=_DATE,
                stop_price=80000,
            )
            assert "registered" in result.lower()

    @pytest.mark.asyncio
    async def test_buy_bypasses_holdings_check(self):
        """BUY should not check holdings — you can buy anything."""
        with (
            patch(
                "agents.tools.alerts.get_active_alerts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "agents.tools.alerts.db_register_alert",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            result = await tool_register_alert(
                "GAS",
                [{"type": "price_below", "value": 130000}],
                "BUY",
                "test",
                source=_SOURCE,
                source_date=_DATE,
            )
            assert "registered" in result.lower()


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


class TestDedup:
    @pytest.mark.asyncio
    async def test_duplicate_blocked(self):
        existing = _active_alert("TCB", "EXIT", "price_below", 106000, alert_id=42)
        with (
            patch(
                "shared.neon.portfolio.get_portfolio_holdings",
                new_callable=AsyncMock,
                return_value=[{"ticker": "TCB", "plan_type": "SWING"}],
            ),
            patch(
                "agents.tools.alerts.get_active_alerts",
                new_callable=AsyncMock,
                return_value=[existing],
            ),
        ):
            result = await tool_register_alert(
                "TCB",
                [{"type": "price_below", "value": 106000}],
                "EXIT",
                "test",
                source=_SOURCE,
                source_date=_DATE,
                stop_price=106000,
            )
            assert "duplicate" in result.lower()
            assert "#42" in result

    @pytest.mark.asyncio
    async def test_different_value_passes(self):
        existing = _active_alert("TCB", "EXIT", "price_below", 106000, alert_id=42)
        with (
            patch(
                "shared.neon.portfolio.get_portfolio_holdings",
                new_callable=AsyncMock,
                return_value=[{"ticker": "TCB", "plan_type": "SWING"}],
            ),
            patch(
                "agents.tools.alerts.get_active_alerts",
                new_callable=AsyncMock,
                return_value=[existing],
            ),
            patch(
                "agents.tools.alerts.db_register_alert",
                new_callable=AsyncMock,
                return_value=2,
            ),
        ):
            # 110000 is >1% different from 106000 — should pass dedup
            result = await tool_register_alert(
                "TCB",
                [{"type": "price_below", "value": 110000}],
                "EXIT",
                "test",
                source=_SOURCE,
                source_date=_DATE,
                stop_price=110000,
            )
            assert "registered" in result.lower()


# ---------------------------------------------------------------------------
# Trailing stop ratchet
# ---------------------------------------------------------------------------


class TestTrailingStopRatchet:
    @pytest.mark.asyncio
    async def test_lower_stop_rejected(self):
        existing = _active_alert("VHM", "EXIT", "price_below", 106000, alert_id=10)
        with (
            patch(
                "shared.neon.portfolio.get_portfolio_holdings",
                new_callable=AsyncMock,
                return_value=[{"ticker": "VHM", "plan_type": "SWING"}],
            ),
            patch(
                "agents.tools.alerts.get_active_alerts",
                new_callable=AsyncMock,
                return_value=[existing],
            ),
        ):
            result = await tool_register_alert(
                "VHM",
                [{"type": "price_below", "value": 93000}],
                "EXIT",
                "test",
                source=_SOURCE,
                source_date=_DATE,
                stop_price=93000,
            )
            assert "ratchet" in result.lower()

    @pytest.mark.asyncio
    async def test_higher_stop_passes(self):
        existing = _active_alert("VHM", "EXIT", "price_below", 106000, alert_id=10)
        with (
            patch(
                "shared.neon.portfolio.get_portfolio_holdings",
                new_callable=AsyncMock,
                return_value=[{"ticker": "VHM", "plan_type": "SWING"}],
            ),
            patch(
                "agents.tools.alerts.get_active_alerts",
                new_callable=AsyncMock,
                return_value=[existing],
            ),
            patch(
                "agents.tools.alerts.db_register_alert",
                new_callable=AsyncMock,
                return_value=3,
            ),
        ):
            result = await tool_register_alert(
                "VHM",
                [{"type": "price_below", "value": 110000}],
                "EXIT",
                "test",
                source=_SOURCE,
                source_date=_DATE,
                stop_price=110000,
            )
            assert "registered" in result.lower()

    @pytest.mark.asyncio
    async def test_ratchet_different_ticker_no_interference(self):
        existing = _active_alert("VHM", "EXIT", "price_below", 106000, alert_id=10)
        with (
            patch(
                "shared.neon.portfolio.get_portfolio_holdings",
                new_callable=AsyncMock,
                return_value=[{"ticker": "TCB", "plan_type": "SWING"}],
            ),
            patch(
                "agents.tools.alerts.get_active_alerts",
                new_callable=AsyncMock,
                return_value=[existing],
            ),
            patch(
                "agents.tools.alerts.db_register_alert",
                new_callable=AsyncMock,
                return_value=4,
            ),
        ):
            # TCB at 32000 is below VHM's 106000, but different ticker — should pass
            result = await tool_register_alert(
                "TCB",
                [{"type": "price_below", "value": 32000}],
                "EXIT",
                "test",
                source=_SOURCE,
                source_date=_DATE,
                stop_price=32000,
            )
            assert "registered" in result.lower()
