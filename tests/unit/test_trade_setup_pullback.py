"""Trade setup: pullback entry tier when support is too far from close."""

import pytest

from agents.tools.technicals import compute_setup_from_levels


@pytest.mark.usefixtures("mock_trading_config")
class TestPullbackSetup:
    """Pullback entry tier when support is too far from close."""

    def test_pullback_promoted_when_gap_exceeds_max(self):
        """Gap > max_entry_gap_pct (default 3.0%) → pullback promoted to primary."""
        levels = {
            "nearest_support": 92000,  # 8% below close
            "swing_low": 90000,
            "nearest_resistance": 110000,
        }
        result = compute_setup_from_levels(levels, close=100000, ticker="TEST")
        assert result.get("pullback_promoted") is True
        assert result["entry"] == 97000  # 100000 * (1 - 3.0/100)
        assert result["risk_reward"] > 0
        assert "support_setup" in result
        assert result["support_setup"]["entry"] == 92000

    def test_no_pullback_when_gap_small(self):
        """Gap <= max_entry_gap_pct → no pullback promotion."""
        levels = {
            "nearest_support": 98000,  # 2% below close
            "swing_low": 97000,
            "nearest_resistance": 105000,
        }
        result = compute_setup_from_levels(levels, close=100000, ticker="TEST")
        assert result.get("pullback_promoted") is not True
        assert result["entry"] == 98000

    def test_pullback_above_stop(self):
        """Pullback entry must be above stop — otherwise no promotion."""
        levels = {
            "nearest_support": 92000,
            "swing_low": 99000,
            "nearest_resistance": 110000,
        }
        result = compute_setup_from_levels(levels, close=100000, ticker="TEST")
        assert result.get("pullback_promoted") is not True
        assert result["entry"] == 99000

    def test_pullback_rr_between_market_and_support(self):
        """Promoted pullback R:R should be between market and support R:R."""
        levels = {
            "nearest_support": 90000,
            "swing_low": 88000,
            "nearest_resistance": 110000,
        }
        result = compute_setup_from_levels(levels, close=100000, ticker="TEST")
        assert "market_setup" in result
        assert result.get("pullback_promoted") is True
        pullback_rr = result["risk_reward"]
        market_rr = result["market_setup"]["risk_reward"]
        support_rr = result["support_setup"]["risk_reward"]
        assert market_rr <= pullback_rr <= support_rr
