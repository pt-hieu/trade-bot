"""Tests for geo-exposure classification + regime-aware calibration overlay."""

from pipeline.context_blocks_ticker import format_ticker_briefing
from shared.rules.catalyst_override import classify_geo_label
from tests.unit._fixtures.context_blocks import _make_geo_shock, _make_sensitivities


class TestGeoExposureClassification:
    """Verify per-ticker geo-exposure labeling."""

    def test_beneficiary_oil_positive(self):
        sensitivities = _make_sensitivities(("oil_price", "POSITIVE", "HIGH"))
        result = classify_geo_label("GVR", sensitivities, _make_geo_shock(), {})
        assert result == "GEO_BENEFICIARY"

    def test_victim_oil_negative(self):
        sensitivities = _make_sensitivities(("oil_price", "NEGATIVE", "HIGH"))
        result = classify_geo_label("VJC", sensitivities, _make_geo_shock(), {})
        assert result == "GEO_VICTIM"

    def test_mixed_sensitivities_uses_magnitude(self):
        sensitivities = _make_sensitivities(
            ("oil_price", "POSITIVE", "HIGH"),
            ("usd_vnd", "NEGATIVE", "LOW"),
        )
        result = classify_geo_label("GAS", sensitivities, _make_geo_shock(), {})
        assert result == "GEO_BENEFICIARY"

    def test_no_shock_returns_none(self):
        sensitivities = _make_sensitivities(("oil_price", "NEGATIVE", "HIGH"))
        result = classify_geo_label("VJC", sensitivities, None, {})
        assert result is None

    def test_recovery_phase_returns_none(self):
        sensitivities = _make_sensitivities(("oil_price", "NEGATIVE", "HIGH"))
        shock = _make_geo_shock(phase_name="recovery")
        result = classify_geo_label("VJC", sensitivities, shock, {})
        assert result is None

    def test_in_affected_list_no_sensitivity_returns_exposed(self):
        sensitivities = _make_sensitivities(("steel_price", "POSITIVE", "HIGH"))
        result = classify_geo_label("HVN", sensitivities, _make_geo_shock(), {})
        assert result == "GEO_EXPOSED"

    def test_not_in_affected_no_sensitivity_returns_none(self):
        sensitivities = _make_sensitivities(("steel_price", "POSITIVE", "HIGH"))
        result = classify_geo_label("FPT", sensitivities, _make_geo_shock(), {})
        assert result is None

    def test_no_sensitivities_in_affected_returns_exposed(self):
        result = classify_geo_label("HVN", [], _make_geo_shock(), {})
        assert result == "GEO_EXPOSED"

    def test_geo_line_in_ticker_briefing(self):
        profile = {
            "sector": "airline",
            "macro_sensitivities": _make_sensitivities(("oil_price", "NEGATIVE", "HIGH")),
        }
        result = format_ticker_briefing(
            "VJC",
            company_profile=profile,
            geopolitical_shock=_make_geo_shock(),
            geo_label="GEO_VICTIM",
        )
        assert "GEO: GEO_VICTIM" in result
        assert "sustained_pressure" in result


class TestCalibrationRegimeAware:
    """Verify regime-aware entry gap calibration."""

    def test_risk_off_caps_at_moderate(self):
        from shared.calibration_overlay import compute_calibrated_entry_gap

        result = compute_calibrated_entry_gap(
            default_gap_pct=3.0,
            pct_unreachable=None,
            sample_size=None,
            regime="RISK_OFF",
        )
        assert result == 2.0  # MODERATE_GAP_PCT

    def test_crisis_caps_at_tight(self):
        from shared.calibration_overlay import compute_calibrated_entry_gap

        result = compute_calibrated_entry_gap(
            default_gap_pct=3.0,
            pct_unreachable=None,
            sample_size=None,
            regime="CRISIS",
        )
        assert result == 1.5  # TIGHT_GAP_PCT

    def test_calm_no_ceiling(self):
        from shared.calibration_overlay import compute_calibrated_entry_gap

        result = compute_calibrated_entry_gap(
            default_gap_pct=3.0,
            pct_unreachable=None,
            sample_size=None,
            regime="CALM",
        )
        assert result == 3.0  # default unchanged

    def test_calibration_tighter_than_regime_wins(self):
        from shared.calibration_overlay import compute_calibrated_entry_gap

        result = compute_calibrated_entry_gap(
            default_gap_pct=3.0,
            pct_unreachable=65.0,
            sample_size=10,
            regime="RISK_OFF",
        )
        assert result == 1.5

    def test_regime_tighter_than_calibration_wins(self):
        from shared.calibration_overlay import compute_calibrated_entry_gap

        result = compute_calibrated_entry_gap(
            default_gap_pct=3.0,
            pct_unreachable=20.0,
            sample_size=10,
            regime="RISK_OFF",
        )
        assert result == 2.0

    def test_no_regime_uses_calibration_only(self):
        from shared.calibration_overlay import compute_calibrated_entry_gap

        result = compute_calibrated_entry_gap(
            default_gap_pct=3.0,
            pct_unreachable=50.0,
            sample_size=10,
            regime=None,
        )
        assert result == 2.0

    def test_elevated_same_as_risk_off(self):
        from shared.calibration_overlay import compute_calibrated_entry_gap

        result = compute_calibrated_entry_gap(
            default_gap_pct=3.0,
            pct_unreachable=None,
            sample_size=None,
            regime="ELEVATED",
        )
        assert result == 2.0
