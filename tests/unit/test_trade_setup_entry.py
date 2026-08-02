"""Trade setup: compute_trade_setup_async + compute_setup_from_levels + no-resistance uptrend."""

from unittest.mock import AsyncMock, patch

import pytest

from agents.tools.technicals import compute_setup_from_levels, compute_trade_setup_async


def _mock_ticker_data(
    close=35900,
    swing_low=33050,
    swing_high=36900,
    nearest_support=35200,
    nearest_resistance=35980,
    range_20d_low=33800,
    range_20d_high=38200,
):
    """Build mock ticker data matching DB format (full VND)."""
    return {
        "ticker": "TCB",
        "close": close,
        "levels": {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "range_20d_high": range_20d_high,
            "range_20d_low": range_20d_low,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
        },
    }


@pytest.fixture
def mock_get_ticker():
    """Patch get_ticker_data_async."""
    with patch(
        "agents.tools.technicals.fetch_async.get_ticker_data_async", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.mark.usefixtures("mock_trading_config")
class TestComputeTradeSetup:
    """Deterministic Entry/Stop/Target/R:R from levels."""

    @pytest.mark.asyncio
    async def test_basic_setup(self, mock_get_ticker):
        mock_get_ticker.return_value = _mock_ticker_data()
        result = await compute_trade_setup_async("TCB")

        assert result["ticker"] == "TCB"
        assert result["entry"] == 35200  # nearest_support (within 3% of close)
        assert result["stop"] == 32389  # swing_low * 0.98 = 33050 * 0.98
        assert result["target"] == 35980  # nearest_resistance
        assert result["risk_per_share"] == 35200 - 32389
        assert result["risk_reward"] > 0
        assert isinstance(result["risk_reward"], float)
        assert "risk_reward_gross" in result
        assert "target_basis" in result
        assert "shares" in result
        assert "position_vnd" in result

    @pytest.mark.asyncio
    async def test_rr_valid(self, mock_get_ticker):
        mock_get_ticker.return_value = _mock_ticker_data()
        result = await compute_trade_setup_async("TCB")
        assert result["valid"] is True
        assert result["risk_reward"] < 3.0

    @pytest.mark.asyncio
    async def test_rr_zero_reward_invalid(self, mock_get_ticker):
        mock_get_ticker.return_value = _mock_ticker_data(
            nearest_resistance=35200,  # same as entry
        )
        result = await compute_trade_setup_async("TCB")
        assert result["valid"] is False
        assert result["risk_reward"] == 0.0

    @pytest.mark.asyncio
    async def test_rr_high_target(self, mock_get_ticker):
        mock_get_ticker.return_value = _mock_ticker_data(
            close=30200,
            nearest_support=30000,
            swing_low=29000,
            nearest_resistance=42000,
        )
        result = await compute_trade_setup_async("TCB")
        assert result["valid"] is True
        assert result["risk_reward"] >= 3.0

    @pytest.mark.asyncio
    async def test_position_sizing(self, mock_get_ticker):
        mock_get_ticker.return_value = _mock_ticker_data(
            close=30200,
            nearest_support=30000,
            swing_low=29000,
            nearest_resistance=42000,
        )
        result = await compute_trade_setup_async("TCB")
        risk = result["risk_per_share"]
        expected_shares = int(200_000 / risk)
        assert result["shares"] == expected_shares
        assert result["position_vnd"] == expected_shares * result["entry"]

    @pytest.mark.asyncio
    async def test_error_no_data(self, mock_get_ticker):
        mock_get_ticker.return_value = {"ticker": "BAD", "error": "No data"}
        result = await compute_trade_setup_async("BAD")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_error_missing_levels(self, mock_get_ticker):
        mock_get_ticker.return_value = {"ticker": "TCB", "close": 35000, "levels": {}}
        result = await compute_trade_setup_async("TCB")
        assert "error" in result
        assert "Insufficient" in result["error"]

    @pytest.mark.asyncio
    async def test_downtrend_support_below_stop_uses_swing_low(self, mock_get_ticker):
        mock_get_ticker.return_value = _mock_ticker_data(
            close=32500,
            nearest_support=30000,
            swing_low=32000,
            nearest_resistance=35000,
        )
        result = await compute_trade_setup_async("TCB")
        assert "error" not in result
        assert result["entry"] == 32000
        assert result["stop"] == 31360

    @pytest.mark.asyncio
    async def test_fallback_to_swing_levels(self, mock_get_ticker):
        """Falls back to swing_low when nearest_support is None."""
        mock_get_ticker.return_value = {
            "ticker": "TCB",
            "close": 30500,
            "levels": {
                "swing_high": 40000,
                "swing_low": 30000,
                "nearest_support": None,
                "nearest_resistance": None,
                "range_20d_high": 38000,
                "range_20d_low": 31000,
            },
        }
        result = await compute_trade_setup_async("TCB")
        assert result["entry"] == 30000
        assert result["target"] == 40000

    @pytest.mark.asyncio
    async def test_levels_used_tracking(self, mock_get_ticker):
        mock_get_ticker.return_value = _mock_ticker_data()
        result = await compute_trade_setup_async("TCB")
        assert "levels_used" in result
        assert result["levels_used"]["nearest_support"] == 35200


@pytest.mark.usefixtures("mock_trading_config")
class TestComputeSetupFromLevels:
    """Pure function tests — no mocks needed."""

    def test_basic(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200, ticker="TCB")
        assert result["entry"] == 30000
        assert result["target"] == 42000
        assert result["valid"] is True
        assert result["risk_reward"] >= 3.0

    def test_missing_levels(self):
        result = compute_setup_from_levels({}, close=35000)
        assert "error" in result

    def test_downtrend_support_below_stop_falls_back(self):
        """When nearest_support < stop, falls back to swing_low as entry."""
        levels = {
            "nearest_support": 28000,
            "swing_low": 30000,
            "nearest_resistance": 35000,
        }
        result = compute_setup_from_levels(levels, close=30500)
        assert "error" not in result
        assert result["entry"] == 30000
        assert result["stop"] == 29400

    def test_shares_calculation(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200)
        risk = result["risk_per_share"]
        assert result["shares"] == int(200_000 / risk)

    def test_market_setup_when_gap_above_threshold(self):
        """market_setup added when close > support + 1.5%."""
        levels = {
            "nearest_support": 83600,
            "swing_low": 83600,
            "nearest_resistance": 92960,
        }
        result = compute_setup_from_levels(levels, close=86900, ticker="PVI")
        assert "market_setup" in result
        ms = result["market_setup"]
        assert ms["entry"] == 86900
        assert ms["stop"] == result["stop"]
        assert ms["target"] == 92960
        assert ms["gap_from_support_pct"] > 1.5
        assert "risk_reward" in ms
        assert "shares" in ms
        assert "valid" in ms

    def test_no_market_setup_when_close_near_support(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200)
        assert "market_setup" not in result

    def test_market_setup_valid_flag(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30600)
        assert "market_setup" in result
        assert result["market_setup"]["valid"] is True

    def test_market_setup_high_rr(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29500,
            "nearest_resistance": 50000,
        }
        result = compute_setup_from_levels(levels, close=31000)
        assert "market_setup" in result
        assert result["market_setup"]["valid"] is True


@pytest.mark.usefixtures("mock_trading_config")
class TestNoResistanceUptrend:
    """VHM-like scenario: price far above all resistance, structural uptrend."""

    def test_uptrend_projects_target_from_volatility(self):
        levels = {
            "nearest_support": 120000,
            "swing_low": 115000,
            "nearest_resistance": None,
            "swing_high": None,
        }
        result = compute_setup_from_levels(
            levels,
            close=143000,
            ticker="VHM",
            structural_uptrend=True,
            atr=3000,
            risk_regime="CALM",
        )
        assert "error" not in result
        assert result["valid"] is True
        assert result["target"] > 143000
        assert result["target_source"] == "volatility_projected"
        assert result["risk_reward"] > 0

    def test_no_resistance_no_uptrend_errors(self):
        levels = {
            "nearest_support": 120000,
            "swing_low": 115000,
            "nearest_resistance": None,
        }
        result = compute_setup_from_levels(
            levels,
            close=143000,
            ticker="VHM",
            structural_uptrend=False,
            atr=3000,
        )
        assert "error" in result
        assert "No resistance" in result["error"]

    def test_no_resistance_no_atr_errors(self):
        levels = {
            "nearest_support": 120000,
            "swing_low": 115000,
            "nearest_resistance": None,
        }
        result = compute_setup_from_levels(
            levels,
            close=143000,
            ticker="VHM",
            structural_uptrend=True,
            atr=None,
        )
        assert "error" in result

    def test_projected_target_uses_max_of_support_and_close_based(self):
        levels = {
            "nearest_support": 100000,
            "swing_low": 95000,
            "nearest_resistance": None,
        }
        result = compute_setup_from_levels(
            levels,
            close=143000,
            ticker="VHM",
            structural_uptrend=True,
            atr=3000,
            risk_regime="NEUTRAL",
        )
        assert result["target"] == 149000

    def test_target_source_structural_when_resistance_exists(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200)
        assert result["target_source"] == "structural"
