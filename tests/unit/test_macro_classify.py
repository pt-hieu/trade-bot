"""Tests for deterministic macro classification functions."""

from agents.macro import (
    MISSING_SIGNAL,
    _is_valid_number,
    calculate_global_regime,
    classify_dxy,
    classify_oil,
    classify_usd_vnd,
    classify_vix,
)
from agents.retro.macro import _evaluate_regime_accuracy


class TestClassifyUsdVnd:
    """classify_usd_vnd with source-aware thresholds."""

    # SBV reference rate (default, ~25,000-25,200)
    def test_sbv_stable_below_threshold(self):
        assert classify_usd_vnd(25000) == "STABLE"

    def test_sbv_stable_at_boundary(self):
        assert classify_usd_vnd(25199) == "STABLE"

    def test_sbv_pressure_at_boundary(self):
        assert classify_usd_vnd(25200) == "PRESSURE"

    def test_sbv_pressure_mid(self):
        assert classify_usd_vnd(25350) == "PRESSURE"

    def test_sbv_pressure_at_upper_boundary(self):
        assert classify_usd_vnd(25500) == "PRESSURE"

    def test_sbv_flight_above_threshold(self):
        assert classify_usd_vnd(25501) == "FLIGHT"

    def test_sbv_flight_high(self):
        assert classify_usd_vnd(26000) == "FLIGHT"

    def test_sbv_explicit_source(self):
        assert classify_usd_vnd(25100, source="sbv") == "STABLE"

    # yfinance market rate (~25,800-26,000) — fallback source
    def test_yfinance_stable_below_threshold(self):
        assert classify_usd_vnd(25800, source="yfinance") == "STABLE"

    def test_yfinance_stable_at_boundary(self):
        assert classify_usd_vnd(26199, source="yfinance") == "STABLE"

    def test_yfinance_pressure_at_boundary(self):
        assert classify_usd_vnd(26200, source="yfinance") == "PRESSURE"

    def test_yfinance_pressure_mid(self):
        assert classify_usd_vnd(26350, source="yfinance") == "PRESSURE"

    def test_yfinance_pressure_at_upper_boundary(self):
        assert classify_usd_vnd(26500, source="yfinance") == "PRESSURE"

    def test_yfinance_flight_above_threshold(self):
        assert classify_usd_vnd(26501, source="yfinance") == "FLIGHT"

    def test_yfinance_flight_high(self):
        assert classify_usd_vnd(27000, source="yfinance") == "FLIGHT"

    # --- Dynamic thresholds (rolling median) ---
    def test_yfinance_dynamic_median_stable(self):
        """Rate below median+200 → STABLE."""
        assert classify_usd_vnd(26400, source="yfinance", rolling_median=26300) == "STABLE"

    def test_yfinance_dynamic_median_pressure(self):
        """Rate between median+200 and median+400 → PRESSURE."""
        assert classify_usd_vnd(26600, source="yfinance", rolling_median=26300) == "PRESSURE"

    def test_yfinance_dynamic_median_flight(self):
        """Rate above median+400 → FLIGHT."""
        assert classify_usd_vnd(26800, source="yfinance", rolling_median=26300) == "FLIGHT"

    def test_yfinance_dynamic_median_at_pressure_boundary(self):
        """Rate exactly at median+200 → PRESSURE (not < stable_ceil)."""
        assert classify_usd_vnd(26500, source="yfinance", rolling_median=26300) == "PRESSURE"

    def test_yfinance_dynamic_median_at_flight_boundary(self):
        """Rate exactly at median+400 → PRESSURE (<=)."""
        assert classify_usd_vnd(26700, source="yfinance", rolling_median=26300) == "PRESSURE"

    def test_yfinance_dynamic_median_none_uses_static(self):
        """No rolling_median → static fallback thresholds."""
        assert classify_usd_vnd(26400, source="yfinance", rolling_median=None) == "PRESSURE"

    def test_yfinance_dynamic_median_nan_uses_static(self):
        """NaN rolling_median → static fallback."""
        assert classify_usd_vnd(26400, source="yfinance", rolling_median=float("nan")) == "PRESSURE"

    def test_sbv_ignores_rolling_median(self):
        """SBV thresholds are policy-managed, unaffected by rolling_median."""
        assert classify_usd_vnd(25300, source="sbv", rolling_median=26300) == "PRESSURE"

    # --- April 2026 regression ---
    def test_april_2026_regression_yfinance_26310_not_crisis(self):
        """Reproduce April 2026 bug: yfinance 26310 + oil EXTREME should not be CRISIS."""
        usd_vnd_signal = classify_usd_vnd(26310, source="yfinance")
        assert usd_vnd_signal == "PRESSURE"
        regime = calculate_global_regime(
            "NEUTRAL", "MODERATE", usd_vnd_signal, False, oil_signal="EXTREME"
        )
        assert regime == "ELEVATED"

    # Historical scenario: 25,860 from yfinance is STABLE with new thresholds
    # (< 26,000), which is correct — old code used 25,700 threshold causing
    # yfinance values to falsely classify as PRESSURE/FLIGHT.
    def test_historical_yfinance_25860_is_stable(self):
        """25,860 from yfinance is STABLE (< 26,000 threshold)."""
        assert classify_usd_vnd(25860, source="yfinance") == "STABLE"

    # Sanity: old code used 25,700 threshold for yfinance — verify new behavior differs
    def test_sbv_25050_typical_sbv_rate_is_stable(self):
        """Typical SBV rate ~25,050 should be STABLE."""
        assert classify_usd_vnd(25050) == "STABLE"


class TestEvaluateRegimeAccuracy:
    """Regime accuracy evaluation with asymmetric thresholds."""

    # --- CALM ---
    def test_calm_flat_market_correct(self):
        assert _evaluate_regime_accuracy("CALM", 0.1) is True

    def test_calm_mild_drop_correct(self):
        assert _evaluate_regime_accuracy("CALM", -0.4) is True

    def test_calm_at_boundary_correct(self):
        assert _evaluate_regime_accuracy("CALM", -0.5) is True

    def test_calm_significant_drop_wrong(self):
        assert _evaluate_regime_accuracy("CALM", -0.6) is False

    def test_calm_rally_correct(self):
        assert _evaluate_regime_accuracy("CALM", 2.0) is True

    # --- CAUTIOUS (asymmetric: correct unless strong rally >1%) ---
    def test_cautious_drop_correct(self):
        """Caution was warranted — market dropped."""
        assert _evaluate_regime_accuracy("CAUTIOUS", -2.0) is True

    def test_cautious_flat_correct(self):
        assert _evaluate_regime_accuracy("CAUTIOUS", 0.0) is True

    def test_cautious_mild_rally_correct(self):
        assert _evaluate_regime_accuracy("CAUTIOUS", 0.9) is True

    def test_cautious_at_boundary_correct(self):
        assert _evaluate_regime_accuracy("CAUTIOUS", 0.99) is True

    def test_cautious_strong_rally_wrong(self):
        """Market rallied >1% — caution was unwarranted."""
        assert _evaluate_regime_accuracy("CAUTIOUS", 1.0) is False

    def test_cautious_big_rally_wrong(self):
        assert _evaluate_regime_accuracy("CAUTIOUS", 3.8) is False

    # --- ELEVATED ---
    def test_elevated_drop_correct(self):
        assert _evaluate_regime_accuracy("ELEVATED", -1.0) is True

    def test_elevated_mild_drop_correct(self):
        assert _evaluate_regime_accuracy("ELEVATED", -0.1) is True

    def test_elevated_flat_wrong(self):
        assert _evaluate_regime_accuracy("ELEVATED", 0.0) is False

    def test_elevated_rally_wrong(self):
        assert _evaluate_regime_accuracy("ELEVATED", 1.5) is False

    # --- CRISIS ---
    def test_crisis_crash_correct(self):
        assert _evaluate_regime_accuracy("CRISIS", -2.0) is True

    def test_crisis_at_boundary_wrong(self):
        """Exactly -1.5% is not < -1.5, so CRISIS is wrong at boundary."""
        assert _evaluate_regime_accuracy("CRISIS", -1.5) is False

    def test_crisis_deep_crash_correct(self):
        assert _evaluate_regime_accuracy("CRISIS", -1.51) is True

    def test_crisis_mild_drop_wrong(self):
        assert _evaluate_regime_accuracy("CRISIS", -0.5) is False

    def test_crisis_rally_wrong(self):
        assert _evaluate_regime_accuracy("CRISIS", 1.93) is False

    # --- Edge cases ---
    def test_none_vn_change_returns_none(self):
        assert _evaluate_regime_accuracy("CALM", None) is None

    def test_unknown_regime_returns_none(self):
        assert _evaluate_regime_accuracy("UNKNOWN", 0.5) is None


class TestCalculateGlobalRegime:
    """Global regime classification with compound-signal requirements."""

    # --- CALM ---
    def test_all_neutral_is_calm(self):
        assert calculate_global_regime("NEUTRAL", "LOW", "STABLE", False) == "CALM"

    def test_weak_dxy_low_vix_is_calm(self):
        assert calculate_global_regime("WEAK", "LOW", "STABLE", False) == "CALM"

    # --- CAUTIOUS requires compound signals ---
    def test_vix_moderate_alone_is_calm(self):
        """VIX MODERATE alone no longer triggers CAUTIOUS — needs 1 more signal."""
        assert calculate_global_regime("NEUTRAL", "MODERATE", "STABLE", False) == "CALM"

    def test_vix_moderate_plus_event_is_cautious(self):
        assert calculate_global_regime("NEUTRAL", "MODERATE", "STABLE", True) == "CAUTIOUS"

    def test_vix_moderate_plus_dxy_strong_is_cautious(self):
        assert calculate_global_regime("STRONG", "MODERATE", "STABLE", False) == "CAUTIOUS"

    def test_vix_moderate_plus_usd_vnd_pressure_is_cautious(self):
        assert calculate_global_regime("NEUTRAL", "MODERATE", "PRESSURE", False) == "CAUTIOUS"

    def test_dxy_strong_plus_event_is_cautious(self):
        """Two non-VIX moderate signals still trigger CAUTIOUS."""
        assert calculate_global_regime("STRONG", "LOW", "STABLE", True) == "CAUTIOUS"

    # --- ELEVATED ---
    def test_vix_high_is_elevated(self):
        assert calculate_global_regime("NEUTRAL", "HIGH", "STABLE", False) == "ELEVATED"

    def test_usd_vnd_flight_is_elevated(self):
        assert calculate_global_regime("NEUTRAL", "LOW", "FLIGHT", False) == "ELEVATED"

    def test_usd_vnd_pressure_plus_dxy_strong_is_elevated(self):
        assert calculate_global_regime("STRONG", "LOW", "PRESSURE", False) == "ELEVATED"

    def test_oil_extreme_is_elevated(self):
        assert (
            calculate_global_regime("NEUTRAL", "LOW", "STABLE", False, oil_signal="EXTREME")
            == "ELEVATED"
        )

    # --- CRISIS ---
    def test_vix_extreme_is_crisis(self):
        """VIX EXTREME still triggers CRISIS unconditionally."""
        assert calculate_global_regime("NEUTRAL", "EXTREME", "STABLE", False) == "CRISIS"

    def test_vix_high_plus_flight_without_dxy_strong_is_elevated(self):
        """VIX HIGH + FLIGHT → ELEVATED (not CRISIS) without DXY STRONG."""
        assert calculate_global_regime("NEUTRAL", "HIGH", "FLIGHT", False) == "ELEVATED"

    def test_vix_high_plus_flight_plus_dxy_strong_is_crisis(self):
        """Triple stress: VIX HIGH + FLIGHT + DXY STRONG → CRISIS."""
        assert calculate_global_regime("STRONG", "HIGH", "FLIGHT", False) == "CRISIS"

    def test_oil_extreme_plus_currency_flight_is_crisis(self):
        assert (
            calculate_global_regime("NEUTRAL", "LOW", "FLIGHT", False, oil_signal="EXTREME")
            == "CRISIS"
        )

    def test_oil_extreme_plus_currency_pressure_is_elevated(self):
        """Oil EXTREME + PRESSURE = ELEVATED (not CRISIS). CRISIS requires FLIGHT."""
        assert (
            calculate_global_regime("NEUTRAL", "LOW", "PRESSURE", False, oil_signal="EXTREME")
            == "ELEVATED"
        )

    # --- Geopolitical floor ---
    def test_geopolitical_immediate_shock_floors_to_elevated(self):
        result = calculate_global_regime(
            "NEUTRAL", "LOW", "STABLE", False, active_geopolitical_phase="immediate_shock"
        )
        assert result == "ELEVATED"

    def test_geopolitical_sustained_pressure_floors_to_cautious(self):
        result = calculate_global_regime(
            "NEUTRAL", "LOW", "STABLE", False, active_geopolitical_phase="sustained_pressure"
        )
        assert result == "CAUTIOUS"

    def test_geopolitical_floor_does_not_lower_regime(self):
        """Geo floor only raises, never lowers."""
        result = calculate_global_regime(
            "NEUTRAL", "HIGH", "STABLE", False, active_geopolitical_phase="sustained_pressure"
        )
        assert result == "ELEVATED"  # ELEVATED > CAUTIOUS floor


# ---------------------------------------------------------------------------
# _is_valid_number
# ---------------------------------------------------------------------------


class TestIsValidNumber:
    def test_valid_float(self):
        assert _is_valid_number(25.0) is True

    def test_valid_zero(self):
        assert _is_valid_number(0.0) is True

    def test_valid_int(self):
        assert _is_valid_number(100) is True

    def test_nan_invalid(self):
        assert _is_valid_number(float("nan")) is False

    def test_inf_invalid(self):
        assert _is_valid_number(float("inf")) is False

    def test_neg_inf_invalid(self):
        assert _is_valid_number(float("-inf")) is False

    def test_none_invalid(self):
        assert _is_valid_number(None) is False

    def test_string_invalid(self):
        assert _is_valid_number("abc") is False


# ---------------------------------------------------------------------------
# NaN sentinel — classify_* returns MISSING for NaN/None/inf
# ---------------------------------------------------------------------------


class TestNaNSentinel:
    """Every classify function returns MISSING_SIGNAL for invalid inputs."""

    def test_classify_vix_nan(self):
        assert classify_vix(float("nan")) == MISSING_SIGNAL

    def test_classify_vix_none(self):
        assert classify_vix(None) == MISSING_SIGNAL

    def test_classify_vix_inf(self):
        assert classify_vix(float("inf")) == MISSING_SIGNAL

    def test_classify_oil_nan_price(self):
        assert classify_oil(float("nan"), 0.0) == MISSING_SIGNAL

    def test_classify_oil_valid_price_nan_change(self):
        """Valid price with NaN change_pct: classifies price, skips SPIKE."""
        result = classify_oil(95.0, float("nan"))
        assert result == "ELEVATED"  # 80-100 range, no _SPIKE appended

    def test_classify_usd_vnd_nan(self):
        assert classify_usd_vnd(float("nan")) == MISSING_SIGNAL

    def test_classify_usd_vnd_none(self):
        assert classify_usd_vnd(None) == MISSING_SIGNAL

    def test_classify_dxy_nan_value(self):
        assert classify_dxy(float("nan"), 0.0) == MISSING_SIGNAL

    def test_classify_dxy_nan_change(self):
        assert classify_dxy(103.0, float("nan")) == MISSING_SIGNAL

    # Verify normal behavior unchanged
    def test_classify_vix_normal_low(self):
        assert classify_vix(18.0) == "LOW"

    def test_classify_vix_normal_extreme(self):
        assert classify_vix(40.0) == "EXTREME"

    def test_classify_oil_normal(self):
        assert classify_oil(75.0, 2.0) == "NORMAL"

    def test_classify_oil_spike(self):
        assert classify_oil(95.0, 6.0) == "ELEVATED_SPIKE"


# ---------------------------------------------------------------------------
# NaN regime integration — MISSING triggers CAUTIOUS, not CRISIS
# ---------------------------------------------------------------------------


class TestNaNRegimeIntegration:
    """MISSING signals should not produce CRISIS or ELEVATED via the regime calc.

    The MISSING sentinel is intercepted in fetch_macro_metrics BEFORE
    reaching calculate_global_regime. These tests verify that if MISSING
    somehow leaks through, it doesn't trigger dangerous paths.
    """

    def test_missing_vix_does_not_cause_crisis(self):
        """MISSING is not in any CRISIS trigger condition."""
        result = calculate_global_regime("NEUTRAL", MISSING_SIGNAL, "STABLE", False)
        # MISSING doesn't match "EXTREME" or "HIGH", so no CRISIS/ELEVATED
        assert result != "CRISIS"

    def test_missing_oil_with_flight_does_not_cause_crisis(self):
        """MISSING oil doesn't contain 'EXTREME', so no CRISIS path."""
        result = calculate_global_regime(
            "NEUTRAL", "LOW", "FLIGHT", False, oil_signal=MISSING_SIGNAL
        )
        assert result != "CRISIS"
        assert result == "ELEVATED"  # FLIGHT alone triggers ELEVATED

    def test_march_26_regression(self):
        """Reproduce the exact 03/26 scenario: NaN oil + FLIGHT.

        Before fix: classify_oil(NaN) → EXTREME → CRISIS with FLIGHT.
        After fix: classify_oil(NaN) → MISSING → intercepted → CAUTIOUS.
        """
        oil_signal = classify_oil(float("nan"), float("nan"))
        assert oil_signal == MISSING_SIGNAL
        # Even if MISSING leaks through:
        result = calculate_global_regime("NEUTRAL", "LOW", "FLIGHT", False, oil_signal=oil_signal)
        assert result != "CRISIS"
