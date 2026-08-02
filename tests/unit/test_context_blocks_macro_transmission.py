"""Tests for pipeline.context_blocks_macro: format_macro_signal_transmission."""

from pipeline.context_blocks_macro import format_macro_signal_transmission
from pipeline.context_blocks_ticker import format_ticker_briefing
from tests.unit._fixtures.context_blocks import _make_sensitivities


class TestMacroSignalTransmission:
    """Verify non-commodity factor TAILWIND/HEADWIND transmission."""

    def test_usd_vnd_negative_pressure_headwind(self):
        """NEGATIVE usd_vnd sensitivity + PRESSURE signal = TAILWIND (inverse)."""
        sensitivities = _make_sensitivities(("usd_vnd", "NEGATIVE", "HIGH"))
        macro = {"usd_vnd_signal": "PRESSURE"}
        parts = format_macro_signal_transmission(sensitivities, macro)
        assert len(parts) == 1
        assert "TAILWIND" in parts[0]
        assert "USD/VND" in parts[0]

    def test_usd_vnd_positive_pressure_headwind(self):
        """POSITIVE usd_vnd sensitivity + PRESSURE signal = HEADWIND."""
        sensitivities = _make_sensitivities(("usd_vnd", "POSITIVE", "MEDIUM"))
        macro = {"usd_vnd_signal": "PRESSURE"}
        parts = format_macro_signal_transmission(sensitivities, macro)
        assert len(parts) == 1
        assert "HEADWIND" in parts[0]

    def test_vix_low_positive_tailwind(self):
        sensitivities = _make_sensitivities(("vix", "POSITIVE", "MEDIUM"))
        macro = {"vix_signal": "LOW"}
        parts = format_macro_signal_transmission(sensitivities, macro)
        assert len(parts) == 1
        assert "TAILWIND" in parts[0]

    def test_vix_high_negative_tailwind(self):
        sensitivities = _make_sensitivities(("vix", "NEGATIVE", "HIGH"))
        macro = {"vix_signal": "HIGH"}
        parts = format_macro_signal_transmission(sensitivities, macro)
        assert len(parts) == 1
        assert "TAILWIND" in parts[0]

    def test_neutral_signal_skipped(self):
        sensitivities = _make_sensitivities(("vix", "POSITIVE", "MEDIUM"))
        macro = {"vix_signal": "MODERATE"}
        parts = format_macro_signal_transmission(sensitivities, macro)
        assert len(parts) == 0

    def test_unknown_factor_skipped(self):
        sensitivities = _make_sensitivities(("china_demand", "POSITIVE", "HIGH"))
        macro = {"vix_signal": "LOW"}
        parts = format_macro_signal_transmission(sensitivities, macro)
        assert len(parts) == 0

    def test_multiple_factors(self):
        sensitivities = _make_sensitivities(
            ("usd_vnd", "POSITIVE", "HIGH"),
            ("dxy", "NEGATIVE", "MEDIUM"),
        )
        macro = {"usd_vnd_signal": "FLIGHT", "dxy_signal": "STRONG"}
        parts = format_macro_signal_transmission(sensitivities, macro)
        assert len(parts) == 2

    def test_missing_macro_key_skipped(self):
        sensitivities = _make_sensitivities(("usd_vnd", "NEGATIVE", "HIGH"))
        macro = {}
        parts = format_macro_signal_transmission(sensitivities, macro)
        assert len(parts) == 0

    def test_appears_in_ticker_briefing(self):
        """Macro signal line appears in full ticker briefing output."""
        profile = {
            "sector": "banking",
            "macro_sensitivities": _make_sensitivities(("usd_vnd", "POSITIVE", "HIGH")),
        }
        macro = {"usd_vnd_signal": "FLIGHT"}
        result = format_ticker_briefing(
            "MWG",
            company_profile=profile,
            macro_metrics=macro,
        )
        assert "Macro signal:" in result
        assert "HEADWIND" in result
