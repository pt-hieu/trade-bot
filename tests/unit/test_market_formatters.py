"""Unit tests for market prose formatters."""

from agents.tools.market import (
    _format_macro_history_prose,
    _format_macro_prose,
    _format_regime_history_prose,
    _format_regime_prose,
    _format_rotation_prose,
)

# ── _format_regime_prose ──────────────────────────────────────────────────


class TestFormatRegimeProse:
    def test_risk_on(self):
        regime = {
            "regime": "RISK_ON",
            "regime_confidence": 0.85,
            "key_signal": "VN-Index above MA50",
            "recommendation": "Buy the dip.",
        }
        result = _format_regime_prose(regime)
        assert "RISK_ON" in result
        assert "85%" in result
        assert "Buy the dip" in result

    def test_confidence_as_decimal(self):
        regime = {
            "regime": "NEUTRAL",
            "regime_confidence": 0.70,
            "key_signal": "Mixed",
            "recommendation": "",
        }
        result = _format_regime_prose(regime)
        assert "70%" in result

    def test_error(self):
        result = _format_regime_prose({"error": "DB down"})
        assert "DB down" in result


# ── _format_rotation_prose ────────────────────────────────────────────────


class TestFormatRotationProse:
    def test_hot_and_cold(self):
        rotation = {
            "hot_sectors": ["Banking", "Tech"],
            "cold_sectors": ["Real Estate"],
            "rotation_signal": "Risk-on",
        }
        result = _format_rotation_prose(rotation)
        assert "HOT: Banking, Tech" in result
        assert "COLD: Real Estate" in result

    def test_no_hot(self):
        rotation = {"hot_sectors": [], "cold_sectors": ["Banking"], "rotation_signal": "Defensive"}
        result = _format_rotation_prose(rotation)
        assert "HOT: None identified" in result

    def test_no_cold(self):
        rotation = {"hot_sectors": ["Tech"], "cold_sectors": [], "rotation_signal": "Broad"}
        result = _format_rotation_prose(rotation)
        assert "COLD: None identified" in result


# ── _format_macro_prose ───────────────────────────────────────────────────


class TestFormatMacroProse:
    def test_all_fields(self):
        macro = {
            "dxy_value": 104.5,
            "dxy_signal": "STRONG",
            "vix_value": 22.3,
            "vix_signal": "MODERATE",
            "usd_vnd_rate": 25500,
            "usd_vnd_signal": "STABLE",
            "global_risk_regime": "CAUTIOUS",
            "interpretation": "Mixed signals",
            "upcoming_events": ["Fed meeting", "CPI data"],
        }
        result = _format_macro_prose(macro)
        assert "DXY: 104.5" in result
        assert "STRONG" in result
        assert "VIX: 22.3" in result
        assert "MODERATE" in result
        assert "USD/VND: 25,500" in result
        assert "STABLE" in result
        assert "CAUTIOUS" in result
        assert "Fed meeting" in result

    def test_dxy_signal_explanations(self):
        for signal, keyword in [
            ("STRONG", "pressure"),
            ("WEAK", "favorable"),
            ("NEUTRAL", "stable"),
        ]:
            macro = {"dxy_value": 100, "dxy_signal": signal, "global_risk_regime": "CALM"}
            result = _format_macro_prose(macro)
            assert keyword in result

    def test_vix_signal_explanations(self):
        for signal, keyword in [("LOW", "healthy"), ("HIGH", "fear"), ("EXTREME", "panic")]:
            macro = {"vix_value": 20, "vix_signal": signal, "global_risk_regime": "CALM"}
            result = _format_macro_prose(macro)
            assert keyword in result

    def test_risk_actions(self):
        for regime, keyword in [
            ("CALM", "Normal"),
            ("ELEVATED", "Defensive"),
            ("CRISIS", "Cash preservation"),
        ]:
            macro = {"global_risk_regime": regime}
            result = _format_macro_prose(macro)
            assert keyword in result

    def test_error(self):
        result = _format_macro_prose({"error": "timeout"})
        assert "timeout" in result


# ── _format_regime_history_prose ──────────────────────────────────────────


class TestFormatRegimeHistoryProse:
    def test_history_list(self):
        history = [
            {"date": "2026-02-15", "regime": "RISK_ON", "confidence": 0.85},
            {"date": "2026-02-14", "regime": "NEUTRAL", "confidence": 0.70},
        ]
        result = _format_regime_history_prose(history)
        assert "2026-02-15" in result
        assert "RISK_ON" in result
        assert "85%" in result

    def test_empty_history(self):
        result = _format_regime_history_prose([])
        assert "No regime history" in result

    def test_error_in_history(self):
        result = _format_regime_history_prose([{"error": "No data"}])
        assert "No data" in result


# ── _format_macro_history_prose ───────────────────────────────────────────


class TestFormatMacroHistoryProse:
    def test_macro_history(self):
        history = [
            {
                "date": "2026-02-15",
                "global_risk_regime": "CALM",
                "dxy_signal": "NEUTRAL",
                "vix_signal": "LOW",
            },
        ]
        result = _format_macro_history_prose(history)
        assert "CALM" in result
        assert "DXY:NEUTRAL" in result

    def test_empty(self):
        result = _format_macro_history_prose([])
        assert "No macro history" in result
