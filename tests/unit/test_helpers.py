"""Tests for pipeline helper functions — regime reconciliation and oil fallback."""

from unittest.mock import patch

from pipeline.helpers import patch_oil_from_commodities, reconcile_regimes

# ---------------------------------------------------------------------------
# reconcile_regimes
# ---------------------------------------------------------------------------


class TestReconcileRegimes:
    """Deterministic regime floor based on global risk."""

    def test_elevated_floors_neutral_to_risk_off(self):
        assert reconcile_regimes("NEUTRAL", "ELEVATED") == "RISK_OFF"

    def test_crisis_floors_neutral_to_risk_off(self):
        assert reconcile_regimes("NEUTRAL", "CRISIS") == "RISK_OFF"

    def test_elevated_floors_risk_on_to_risk_off(self):
        assert reconcile_regimes("RISK_ON", "ELEVATED") == "RISK_OFF"

    def test_cautious_does_not_override(self):
        assert reconcile_regimes("NEUTRAL", "CAUTIOUS") == "NEUTRAL"

    def test_calm_does_not_override(self):
        assert reconcile_regimes("RISK_ON", "CALM") == "RISK_ON"

    def test_already_risk_off_unchanged(self):
        assert reconcile_regimes("RISK_OFF", "ELEVATED") == "RISK_OFF"

    def test_already_risk_off_with_crisis(self):
        assert reconcile_regimes("RISK_OFF", "CRISIS") == "RISK_OFF"

    # --- CAUTIOUS floor (new behavior, Fix 3) ---

    def test_cautious_floors_risk_on_to_neutral(self):
        # CAUTIOUS caps at NEUTRAL — RISK_ON is above the floor, so it lowers.
        assert reconcile_regimes("RISK_ON", "CAUTIOUS") == "NEUTRAL"

    def test_cautious_leaves_neutral_unchanged(self):
        # NEUTRAL is exactly at the CAUTIOUS floor — no-op.
        assert reconcile_regimes("NEUTRAL", "CAUTIOUS") == "NEUTRAL"

    def test_cautious_does_not_loosen_risk_off(self):
        # Latent bug guard: RISK_OFF is stricter than NEUTRAL floor,
        # ordinal comparison must preserve it (never raise).
        assert reconcile_regimes("RISK_OFF", "CAUTIOUS") == "RISK_OFF"

    # --- Ordinal comparison invariants ---

    def test_elevated_preserves_already_strict_risk_off(self):
        # RISK_OFF is already at the ELEVATED floor — no-op, no log spam.
        assert reconcile_regimes("RISK_OFF", "ELEVATED") == "RISK_OFF"

    def test_elevated_floors_risk_on_to_risk_off_ordinal(self):
        # Existing ELEVATED behavior preserved after rewrite.
        assert reconcile_regimes("RISK_ON", "ELEVATED") == "RISK_OFF"

    def test_calm_is_noop_for_any_market_regime(self):
        # CALM has no entry in the floor dict — reconcile is a pure passthrough.
        assert reconcile_regimes("NEUTRAL", "CALM") == "NEUTRAL"
        assert reconcile_regimes("RISK_ON", "CALM") == "RISK_ON"
        assert reconcile_regimes("RISK_OFF", "CALM") == "RISK_OFF"


# ---------------------------------------------------------------------------
# patch_oil_from_commodities
# ---------------------------------------------------------------------------


def _base_macro(oil_price=None, oil_signal="NORMAL", regime="CAUTIOUS"):
    """Build a minimal macro_metrics dict."""
    return {
        "dxy_signal": "WEAK",
        "vix_signal": "LOW",
        "usd_vnd_signal": "STABLE",
        "oil_price": oil_price,
        "oil_change_pct": None,
        "oil_signal": oil_signal,
        "global_risk_regime": regime,
        "geopolitical_shock": {
            "phase_name": "sustained_pressure",
            "catalyst_event": "Hormuz closure",
        },
    }


class TestPatchOilFromCommodities:
    """Oil fallback from commodity pipeline when yfinance fails."""

    def test_patches_when_oil_missing(self):
        macro = _base_macro(oil_price=None)
        commodities = {"oil_crude": {"price": 120.0, "change_5d_pct": 5.0}}

        with (
            patch("agents.macro.classify_oil", return_value="EXTREME_SPIKE"),
            patch("agents.macro.calculate_global_regime", return_value="ELEVATED"),
        ):
            patch_oil_from_commodities(macro, commodities)

        assert macro["oil_price"] == 120.0
        assert macro["oil_signal"] == "EXTREME_SPIKE"
        assert macro["global_risk_regime"] == "ELEVATED"

    def test_patches_when_oil_zero(self):
        macro = _base_macro(oil_price=0.0)
        commodities = {"oil_crude": {"price": 85.0}}

        with (
            patch("agents.macro.classify_oil", return_value="NORMAL"),
            patch("agents.macro.calculate_global_regime", return_value="CAUTIOUS"),
        ):
            patch_oil_from_commodities(macro, commodities)

        assert macro["oil_price"] == 85.0

    def test_skips_when_oil_present(self):
        macro = _base_macro(oil_price=68.5, oil_signal="NORMAL", regime="CAUTIOUS")
        commodities = {"oil_crude": {"price": 120.0}}

        patch_oil_from_commodities(macro, commodities)

        # Should NOT patch — original oil data was valid
        assert macro["oil_price"] == 68.5
        assert macro["global_risk_regime"] == "CAUTIOUS"

    def test_recalculates_regime_after_patch(self):
        macro = _base_macro(oil_price=None, regime="CAUTIOUS")
        commodities = {"oil_crude": {"price": 120.0}}

        with (
            patch("agents.macro.classify_oil", return_value="EXTREME"),
            patch("agents.macro.calculate_global_regime", return_value="CRISIS"),
        ):
            patch_oil_from_commodities(macro, commodities)

        assert macro["global_risk_regime"] == "CRISIS"

    def test_handles_no_commodity_data(self):
        macro = _base_macro(oil_price=None)

        patch_oil_from_commodities(macro, None)

        # Should not crash, oil stays None/0
        assert macro["oil_price"] is None

    def test_handles_empty_commodity_oil(self):
        macro = _base_macro(oil_price=None)
        commodities = {"oil_crude": {}}

        patch_oil_from_commodities(macro, commodities)

        assert macro["oil_price"] is None

    def test_skips_when_macro_has_error(self):
        macro = {"error": "fetch failed"}
        commodities = {"oil_crude": {"price": 120.0}}

        patch_oil_from_commodities(macro, commodities)

        assert "oil_price" not in macro

    def test_no_regime_change_when_same(self):
        macro = _base_macro(oil_price=None, regime="CAUTIOUS")
        commodities = {"oil_crude": {"price": 60.0}}

        with (
            patch("agents.macro.classify_oil", return_value="NORMAL"),
            patch("agents.macro.calculate_global_regime", return_value="CAUTIOUS"),
        ):
            patch_oil_from_commodities(macro, commodities)

        # Regime unchanged — no recalc warning needed
        assert macro["global_risk_regime"] == "CAUTIOUS"
