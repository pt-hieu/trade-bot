"""Tests for pipeline.context_blocks regime block (format_regime_block + neighbours)."""

from agents.belief_models import decay_belief_conviction
from pipeline.context_blocks import format_regime_block
from pipeline.context_blocks_ticker import format_ticker_briefing
from tests.unit._fixtures.context_blocks import _make_macro_metrics, _make_market_level


class TestRegimeBlockKeyFix:
    """Verify the key mismatch bug is fixed — correct keys produce real values."""

    def test_risk_regime_not_unknown(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "Risk: CAUTIOUS" in result
        assert "Risk: UNKNOWN" not in result

    def test_vix_value_appears(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "VIX: 28.5" in result

    def test_dxy_value_appears(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "DXY: 104.2" in result

    def test_usd_vnd_value_appears(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "USD/VND: 25,350" in result

    def test_change_percentages_shown(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "(+2.1%)" in result  # VIX change
        assert "(+0.3%)" in result  # DXY change


class TestRegimeBlockExpanded:
    """Verify oil, copper, 10Y, Shanghai, breadth, S&P are in the block."""

    def test_oil_in_block(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "Oil: $78" in result
        assert "(+1.1%)" in result

    def test_copper_in_block(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "Cu: $4.12" in result

    def test_us_10y_in_block(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "10Y: 4.28%" in result

    def test_shanghai_in_block(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "SSEC: 3,200" in result

    def test_breadth_in_block(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "Breadth: 245A/180D" in result
        assert "(1.36)" in result

    def test_sp500_in_block(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "S&P: 5,500" in result

    def test_regime_history_shown(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "History:" in result
        assert "BEARISH" in result


class TestRegimeBlockEdgeCases:
    """Handle None/missing data gracefully."""

    def test_none_macro_metrics(self):
        result = format_regime_block(_make_market_level(), None)
        assert "Risk: UNKNOWN" in result
        assert "VIX" not in result

    def test_none_market_level(self):
        result = format_regime_block(None, _make_macro_metrics())
        assert "MARKET REGIME: UNKNOWN" in result
        assert "VIX: 28.5" in result

    def test_both_none(self):
        result = format_regime_block(None, None)
        assert "MARKET REGIME: UNKNOWN | Risk: UNKNOWN" in result

    def test_partial_macro_metrics(self):
        """Only VIX present, others None."""
        partial = {"global_risk_regime": "CALM", "vix_value": 15.0}
        result = format_regime_block(_make_market_level(), partial)
        assert "Risk: CALM" in result
        assert "VIX: 15.0" in result
        assert "DXY" not in result
        assert "Oil" not in result

    def test_null_risk_regime_falls_back(self):
        """global_risk_regime key exists but is None."""
        metrics = _make_macro_metrics(global_risk_regime=None)
        result = format_regime_block(_make_market_level(), metrics)
        assert "Risk: UNKNOWN" in result

    def test_vnindex_line_format(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "VN-Index: 1,180" in result
        assert "RSI: 42.3" in result
        assert "S: 1,150" in result
        assert "R: 1,220" in result


class TestRegimeBlockValuation:
    """Verify PE/PB percentile line appears when market_valuation is provided."""

    def test_pe_pb_line_appears(self):
        valuation = {"pe": 13.7, "pe_percentile": 25, "pb": 1.98, "pb_percentile": 40}
        result = format_regime_block(
            _make_market_level(), _make_macro_metrics(), market_valuation=valuation
        )
        assert "VN-Index PE: 13.7" in result
        assert "25th pctl 5Y" in result
        assert "PB: 1.98" in result
        assert "40th pctl 5Y" in result

    def test_no_valuation_param(self):
        result = format_regime_block(_make_market_level(), _make_macro_metrics())
        assert "PE:" not in result
        assert "PB:" not in result

    def test_partial_valuation(self):
        valuation = {"pe": 14.0}
        result = format_regime_block(
            _make_market_level(), _make_macro_metrics(), market_valuation=valuation
        )
        assert "VN-Index PE: 14.0" in result
        assert "pctl" not in result  # no percentile provided


class TestRegimeBlockConfidenceAndQuality:
    """format_regime_block shows regime_confidence and data_quality in header."""

    def test_confidence_shown_in_header(self):
        market_level = _make_market_level(regime_confidence=0.85)
        result = format_regime_block(market_level, _make_macro_metrics())
        assert "(conf: 85%)" in result

    def test_low_confidence_shown(self):
        market_level = _make_market_level(regime_confidence=0.30)
        result = format_regime_block(market_level, _make_macro_metrics())
        assert "(conf: 30%)" in result

    def test_no_confidence_no_parentheses(self):
        market_level = _make_market_level()
        market_level.pop("regime_confidence", None)
        result = format_regime_block(market_level, _make_macro_metrics())
        assert "conf:" not in result

    def test_stale_data_quality_shown(self):
        macro = _make_macro_metrics(data_quality="STALE")
        result = format_regime_block(_make_market_level(), macro)
        assert "Macro Data: STALE" in result

    def test_degraded_data_quality_shown(self):
        macro = _make_macro_metrics(data_quality="DEGRADED")
        result = format_regime_block(_make_market_level(), macro)
        assert "Macro Data: DEGRADED" in result

    def test_ok_data_quality_not_shown(self):
        macro = _make_macro_metrics(data_quality="OK")
        result = format_regime_block(_make_market_level(), macro)
        assert "Macro Data:" not in result

    def test_no_data_quality_key_no_label(self):
        macro = _make_macro_metrics()
        macro.pop("data_quality", None)
        result = format_regime_block(_make_market_level(), macro)
        assert "Macro Data:" not in result


class TestFormatMetricNaN:
    """_format_metric handles NaN/inf gracefully."""

    def test_nan_value_returns_none(self):
        from pipeline.context_blocks import _format_metric

        metrics = {"oil_price": float("nan"), "oil_change_pct": 1.0}
        assert _format_metric(metrics, "oil_price", "oil_change_pct", "Oil", ".0f", "$") is None

    def test_nan_change_pct_omitted(self):
        from pipeline.context_blocks import _format_metric

        metrics = {"vix_value": 28.5, "vix_change_pct": float("nan")}
        result = _format_metric(metrics, "vix_value", "vix_change_pct", "VIX", ".1f")
        assert result == "VIX: 28.5"  # No change % appended
        assert "nan" not in result

    def test_normal_values_unchanged(self):
        from pipeline.context_blocks import _format_metric

        metrics = {"vix_value": 28.5, "vix_change_pct": 2.1}
        result = _format_metric(metrics, "vix_value", "vix_change_pct", "VIX", ".1f")
        assert result == "VIX: 28.5 (+2.1%)"


class TestBeliefStalenessDecay:
    """Tests for conviction decay in prior belief display."""

    def test_fresh_belief_full_conviction(self):
        """Beliefs held ≤2 days get full conviction."""
        assert decay_belief_conviction(0.85, days_held=1) == 0.85
        assert decay_belief_conviction(0.85, days_held=2) == 0.85

    def test_stale_belief_decayed(self):
        """Beliefs held 5 days: 0.85 × 0.85^3 ≈ 0.52."""
        result = decay_belief_conviction(0.85, days_held=5)
        assert abs(result - 0.85 * 0.85**3) < 0.01

    def test_long_stale_belief_still_shown(self):
        """Beliefs held 9 days still get a value (no omission floor)."""
        result = decay_belief_conviction(0.85, days_held=9)
        assert result > 0
        assert abs(result - 0.85 * 0.85**7) < 0.01

    def test_decay_appears_in_your_prior(self):
        beliefs = [
            {
                "agent_key": "test_agent",
                "direction": "BULLISH",
                "bull_probability": 0.45,
                "base_probability": 0.35,
                "bear_probability": 0.20,
                "days_held": 5,
                "conviction": 0.85,
                "belief_status": "REAFFIRMED",
            }
        ]
        result = format_ticker_briefing("FPT", beliefs=beliefs, agent_key="test_agent")
        assert "conv=52%" in result

    def test_other_beliefs_sorted_by_conviction(self):
        beliefs = [
            {"agent_key": "other_a", "direction": "NEUTRAL", "conviction": 0.3},
            {"agent_key": "other_b", "direction": "BULLISH", "conviction": 0.7},
            {"agent_key": "other_c", "direction": "BEARISH", "conviction": 0.5},
        ]
        result = format_ticker_briefing("FPT", beliefs=beliefs, agent_key="my_agent")
        position_b = result.find("other_b")
        position_c = result.find("other_c")
        assert position_b < position_c


class TestNoStaleToolReferences:
    """Prevent stale tool_ names from being injected into agent prompts.

    Defect class: Configuration Drift — old tool names in injected context
    cause agents to call non-existent tools (search_tools loops).
    Fixed 5+ times in migrations 276/280/281/282/285. This test prevents recurrence.
    """

    def test_no_old_tool_names_in_headers(self):
        from pipeline.context_blocks import CATALYST_HEADER, PORTFOLIO_HEADER
        from pipeline.context_blocks_calibration import (
            CALIBRATION_HEADER,
            EXECUTED_TRADES_HEADER,
            LEARNINGS_HEADER,
            MEMORY_HEADER,
            MIDDAY_PRICES_HEADER,
            ROTATION_HEADER,
            SECTOR_DATA_HEADER,
            TRADES_HEADER,
        )
        from pipeline.context_blocks_ticker import TICKER_DATA_HEADER

        all_headers = [
            PORTFOLIO_HEADER,
            CATALYST_HEADER,
            CALIBRATION_HEADER,
            TRADES_HEADER,
            LEARNINGS_HEADER,
            MEMORY_HEADER,
            ROTATION_HEADER,
            SECTOR_DATA_HEADER,
            EXECUTED_TRADES_HEADER,
            MIDDAY_PRICES_HEADER,
            TICKER_DATA_HEADER,
        ]

        for header in all_headers:
            assert "tool_" not in header, f"Stale tool_ reference in header: {header}"
            assert "do NOT call" not in header.lower(), f"Negative instruction in header: {header}"

    def test_articles_truncation_uses_broker_syntax(self):
        from pipeline.context_blocks import format_articles_block

        articles = [{"title": f"Article {i}", "source": "test"} for i in range(20)]
        result = format_articles_block(articles)

        assert "tool_search_articles" not in result, "Stale tool_search_articles ref"
        assert "call_tools" in result, "Should use call_tools broker syntax"
        assert "article.search" in result, "Should reference article.search domain"
