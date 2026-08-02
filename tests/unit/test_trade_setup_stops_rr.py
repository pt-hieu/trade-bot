"""Trade setup: ATR-aware stops, net-of-cost R:R, target chooser, regime-scaled, position sizing."""

import pytest

from agents.alert_analyst import compute_position_size
from agents.tools.technicals import compute_setup_from_levels


@pytest.mark.usefixtures("mock_trading_config")
class TestAtrAwareStops:
    """ATR-aware stop minimum — stop distance >= ATR_STOP_MULT × ATR."""

    def test_atr_widens_stop(self):
        """When 2× ATR is wider than fixed buffer, stop moves further out."""
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result_no_atr = compute_setup_from_levels(levels, close=30200)
        assert result_no_atr["stop"] == 28420

        result_with_atr = compute_setup_from_levels(levels, close=30200, atr=2000)
        assert result_with_atr["stop"] == 26000
        assert result_with_atr["stop"] < result_no_atr["stop"]

    def test_atr_none_fallback(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200, atr=None)
        assert result["stop"] == 28420

    def test_atr_zero_fallback(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200, atr=0)
        assert result["stop"] == 28420

    def test_atr_small_no_effect(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200, atr=500)
        assert result["stop"] == 28420


@pytest.mark.usefixtures("mock_trading_config")
class TestNetOfCostRR:
    """risk_reward is the net-of-cost raw float gates compare against."""

    def test_risk_reward_is_raw_float(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200)
        assert isinstance(result["risk_reward"], float)
        assert 7.0 < result["risk_reward"] < 7.2
        assert result["risk_reward_gross"] > result["risk_reward"]

    def test_risk_per_share_uses_gross_risk(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
        }
        result = compute_setup_from_levels(levels, close=30200)
        assert result["risk_per_share"] == 30000 - 28420

    def test_borderline_rr_passes_when_unrounded(self):
        """A R:R of 3.49 should fail a 3.5 floor — no rounding before gate."""
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000 / 0.98,
            "nearest_resistance": 33490,
        }
        result = compute_setup_from_levels(levels, close=30100)
        assert result["risk_reward"] < 3.5

    def test_rr_zero_for_zero_reward(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 30000,
        }
        result = compute_setup_from_levels(levels, close=30200)
        assert result["risk_reward"] == 0.0
        assert result["valid"] is False


@pytest.mark.usefixtures("mock_trading_config")
class TestDeterministicTargetChooser:
    """Single deterministic target — no dual rr fields surfaced."""

    def test_default_to_conservative_target(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
            "swing_high": 50000,
        }
        result = compute_setup_from_levels(levels, close=30200, structural_uptrend=False)
        assert result["target_basis"] == "conservative"
        assert result["target"] == 42000
        assert result["rr_stretch"] is not None and result["rr_stretch"] > result["risk_reward"]

    def test_aggressive_picked_when_uptrend_and_stretch_meets_threshold(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 33000,
            "swing_high": 50000,
        }
        result = compute_setup_from_levels(levels, close=30200, structural_uptrend=True)
        assert result["target_basis"] == "aggressive"
        assert result["target"] == 50000
        assert result["rr_stretch"] is None or result["rr_stretch"] <= result["risk_reward"]

    def test_no_dual_rr_fields_in_output(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 42000,
            "swing_high": 50000,
        }
        result = compute_setup_from_levels(levels, close=30200)
        for dead_field in (
            "conservative_rr",
            "aggressive_rr",
            "conservative_target",
            "aggressive_target",
        ):
            assert dead_field not in result, f"dead field {dead_field} still in output"


@pytest.mark.usefixtures("mock_trading_config")
class TestRegimeScaledTarget:
    """REGIME_TARGET_MULT scales aggressive target in structural uptrend."""

    def test_calm_regime_extends_aggressive_target(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 33000,
            "swing_high": 50000,
        }
        result_big = compute_setup_from_levels(
            dict(levels),
            close=30200,
            structural_uptrend=True,
            atr=8000,
            risk_regime="CALM",
        )
        assert result_big["target"] >= 50000

    def test_risk_off_shrinks_aggressive_target(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 33000,
            "swing_high": 50000,
        }
        result = compute_setup_from_levels(
            levels, close=30200, structural_uptrend=True, atr=2000, risk_regime="RISK_OFF"
        )
        assert result["target"] <= 50000
        assert result["target"] >= 33000

    def test_no_regime_no_uptrend_unchanged(self):
        levels = {
            "nearest_support": 30000,
            "swing_low": 29000,
            "nearest_resistance": 33000,
            "swing_high": 50000,
        }
        result = compute_setup_from_levels(levels, close=30200, structural_uptrend=False, atr=2000)
        assert result["target"] == 33000


@pytest.mark.usefixtures("mock_trading_config")
class TestComputePositionSize:
    """Alert analyst position sizing."""

    def test_basic(self):
        assert compute_position_size(entry=30000, stop=28000) == int(200_000 / 2000)

    def test_none_entry(self):
        assert compute_position_size(entry=None, stop=28000) is None

    def test_none_stop(self):
        assert compute_position_size(entry=30000, stop=None) is None

    def test_zero_risk(self):
        assert compute_position_size(entry=30000, stop=30000) is None

    def test_entry_below_stop(self):
        assert compute_position_size(entry=28000, stop=30000) is None
