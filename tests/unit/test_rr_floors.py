"""Tests for R:R floor computation — regime-based validation gate."""

from shared.rules.rr_floors import (
    RR_FLOOR_CRISIS,
    RR_FLOOR_DEFAULT,
    RR_FLOOR_ELEVATED,
    get_rr_floor,
)


class TestDefaultFloor:
    """Base floor behavior with non-elevated regimes."""

    def test_calm_regime_uses_default(self):
        assert get_rr_floor("CALM", min_rr=0.0) == RR_FLOOR_DEFAULT

    def test_cautious_regime_uses_default(self):
        assert get_rr_floor("CAUTIOUS", min_rr=0.0) == RR_FLOOR_DEFAULT

    def test_unknown_regime_uses_default(self):
        assert get_rr_floor("UNKNOWN", min_rr=0.0) == RR_FLOOR_DEFAULT

    def test_min_rr_above_default_wins(self):
        """Urgency min_rr of 3.0 > default 2.0 -> use 3.0."""
        assert get_rr_floor("CALM", min_rr=3.0) == 3.0

    def test_min_rr_below_default_uses_default(self):
        """Urgency min_rr of 1.0 < default 2.0 -> use 2.0."""
        assert get_rr_floor("CALM", min_rr=1.0) == RR_FLOOR_DEFAULT


class TestElevatedFloor:
    """ELEVATED and RISK_OFF regimes raise the floor."""

    def test_elevated_regime_floor(self):
        assert get_rr_floor("ELEVATED", min_rr=0.0) == RR_FLOOR_ELEVATED

    def test_risk_off_regime_floor(self):
        assert get_rr_floor("RISK_OFF", min_rr=0.0) == RR_FLOOR_ELEVATED

    def test_elevated_with_higher_min_rr(self):
        """Urgency min_rr of 4.0 > ELEVATED floor 3.0 -> use 4.0."""
        assert get_rr_floor("ELEVATED", min_rr=4.0) == 4.0

    def test_elevated_with_lower_min_rr(self):
        """Urgency min_rr of 2.5 < ELEVATED floor 3.0 -> use 3.0."""
        assert get_rr_floor("ELEVATED", min_rr=2.5) == RR_FLOOR_ELEVATED


class TestCrisisFloor:
    """CRISIS regime demands highest R:R."""

    def test_crisis_regime_floor(self):
        assert get_rr_floor("CRISIS", min_rr=0.0) == RR_FLOOR_CRISIS

    def test_crisis_with_higher_min_rr(self):
        """Urgency min_rr of 5.0 > CRISIS floor 4.5 -> use 5.0."""
        assert get_rr_floor("CRISIS", min_rr=5.0) == 5.0

    def test_crisis_with_lower_min_rr(self):
        """Urgency min_rr of 3.0 < CRISIS floor 4.5 -> use 4.5."""
        assert get_rr_floor("CRISIS", min_rr=3.0) == RR_FLOOR_CRISIS


class TestConstantValues:
    """Verify constant values match expected thresholds."""

    def test_default_is_2(self):
        assert RR_FLOOR_DEFAULT == 2.0

    def test_elevated_is_3(self):
        assert RR_FLOOR_ELEVATED == 3.0

    def test_crisis_is_4_5(self):
        assert RR_FLOOR_CRISIS == 4.5

    def test_ordering(self):
        assert RR_FLOOR_DEFAULT < RR_FLOOR_ELEVATED < RR_FLOOR_CRISIS
