"""Tests for compute_calibrated_entry_gap() — regime-aware entry gap adjustment."""

from datetime import date, timedelta

from shared.calibration_overlay import (
    MODERATE_GAP_PCT,
    STALE_DAYS,
    TIGHT_GAP_PCT,
    compute_calibrated_entry_gap,
)

DEFAULT_GAP = 3.0


class TestCalibrationBasedAdjustment:
    """Entry gap tightens when too many entries are unreachable."""

    def test_high_unreachable_tightens_to_tight(self):
        """Above 60% unreachable -> tight gap (1.5%)."""
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=65.0, sample_size=10)
        assert result == TIGHT_GAP_PCT

    def test_moderate_unreachable_tightens_to_moderate(self):
        """40-60% unreachable -> moderate gap (2.0%)."""
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=45.0, sample_size=10)
        assert result == MODERATE_GAP_PCT

    def test_low_unreachable_keeps_default(self):
        """Below 40% unreachable -> keep default."""
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=30.0, sample_size=10)
        assert result == DEFAULT_GAP

    def test_boundary_exactly_at_high_threshold(self):
        """Exactly 60% -> NOT high (needs >60), so moderate."""
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=60.0, sample_size=10)
        assert result == MODERATE_GAP_PCT

    def test_boundary_exactly_at_moderate_threshold(self):
        """Exactly 40% -> NOT moderate (needs >40), so default."""
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=40.0, sample_size=10)
        assert result == DEFAULT_GAP


class TestInsufficientData:
    """Fallback to default when calibration data is insufficient."""

    def test_none_unreachable_uses_default(self):
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=None, sample_size=10)
        assert result == DEFAULT_GAP

    def test_none_sample_size_uses_default(self):
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=70.0, sample_size=None)
        assert result == DEFAULT_GAP

    def test_below_min_sample_uses_default(self):
        """Sample size 3 < min_sample_size 5 -> use default."""
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=70.0, sample_size=3)
        assert result == DEFAULT_GAP

    def test_custom_min_sample_size(self):
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=70.0, sample_size=8, min_sample_size=10
        )
        assert result == DEFAULT_GAP

    def test_exactly_at_min_sample_size(self):
        """Sample size == min -> sufficient data."""
        result = compute_calibrated_entry_gap(DEFAULT_GAP, pct_unreachable=70.0, sample_size=5)
        assert result == TIGHT_GAP_PCT


class TestRegimeCeiling:
    """Regime-aware gap ceiling overrides loose calibration."""

    def test_crisis_ceiling_at_tight(self):
        """CRISIS -> max 1.5% regardless of calibration."""
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=20.0, sample_size=10, regime="CRISIS"
        )
        assert result == TIGHT_GAP_PCT

    def test_risk_off_ceiling_at_moderate(self):
        """RISK_OFF -> max 2.0%."""
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=20.0, sample_size=10, regime="RISK_OFF"
        )
        assert result == MODERATE_GAP_PCT

    def test_elevated_ceiling_at_moderate(self):
        """ELEVATED -> max 2.0%."""
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=20.0, sample_size=10, regime="ELEVATED"
        )
        assert result == MODERATE_GAP_PCT

    def test_calm_regime_no_ceiling(self):
        """CALM -> no ceiling applied."""
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=20.0, sample_size=10, regime="CALM"
        )
        assert result == DEFAULT_GAP

    def test_none_regime_no_ceiling(self):
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=20.0, sample_size=10, regime=None
        )
        assert result == DEFAULT_GAP


class TestRegimeAndCalibrationCombined:
    """Tighter of calibration vs regime wins."""

    def test_calibration_tighter_than_regime(self):
        """High unreachable (1.5%) is tighter than RISK_OFF ceiling (2.0%) -> use 1.5%."""
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=65.0, sample_size=10, regime="RISK_OFF"
        )
        assert result == TIGHT_GAP_PCT

    def test_regime_tighter_than_calibration(self):
        """Low unreachable (default 3.0%) but CRISIS ceiling (1.5%) -> use 1.5%."""
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=20.0, sample_size=10, regime="CRISIS"
        )
        assert result == TIGHT_GAP_PCT

    def test_both_at_moderate(self):
        """Moderate calibration + RISK_OFF both at 2.0% -> 2.0%."""
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP, pct_unreachable=45.0, sample_size=10, regime="RISK_OFF"
        )
        assert result == MODERATE_GAP_PCT


class TestStalenessBypass:
    """When calibration data is stale, bypass to default gap."""

    TODAY = date(2026, 4, 11)

    def test_stale_data_bypasses_to_default(self):
        """Data older than STALE_DAYS -> ignore calibration, use default."""
        stale_date = self.TODAY - timedelta(days=STALE_DAYS + 1)
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP,
            pct_unreachable=80.0,  # would normally force TIGHT
            sample_size=10,
            as_of=stale_date,
            today=self.TODAY,
        )
        assert result == DEFAULT_GAP

    def test_fresh_data_still_applies_calibration(self):
        """Data within STALE_DAYS -> normal calibration applies."""
        fresh_date = self.TODAY - timedelta(days=STALE_DAYS - 1)
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP,
            pct_unreachable=80.0,
            sample_size=10,
            as_of=fresh_date,
            today=self.TODAY,
        )
        assert result == TIGHT_GAP_PCT

    def test_exactly_at_stale_boundary_is_not_stale(self):
        """Data exactly STALE_DAYS old -> NOT stale (needs >STALE_DAYS)."""
        boundary_date = self.TODAY - timedelta(days=STALE_DAYS)
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP,
            pct_unreachable=80.0,
            sample_size=10,
            as_of=boundary_date,
            today=self.TODAY,
        )
        assert result == TIGHT_GAP_PCT

    def test_stale_data_still_respects_regime_ceiling(self):
        """Stale bypass gives default 3.0%, but CRISIS ceiling caps to 1.5%."""
        stale_date = self.TODAY - timedelta(days=STALE_DAYS + 3)
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP,
            pct_unreachable=80.0,
            sample_size=10,
            regime="CRISIS",
            as_of=stale_date,
            today=self.TODAY,
        )
        assert result == TIGHT_GAP_PCT

    def test_no_as_of_skips_staleness_check(self):
        """When as_of is None, staleness check is skipped -> normal calibration."""
        result = compute_calibrated_entry_gap(
            DEFAULT_GAP,
            pct_unreachable=80.0,
            sample_size=10,
            as_of=None,
            today=self.TODAY,
        )
        assert result == TIGHT_GAP_PCT
