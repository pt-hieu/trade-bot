"""Unit tests for pipeline macro trend computation."""

from pipeline.macro_trends import (
    compute_indicator_trends,
    compute_regime_transition,
    detect_cross_asset_narratives,
    format_trend_block,
)

# ── Fixtures ────────────────────────────────────────────────────────────


def _make_macro_history(
    *,
    vix_start: float = 18.0,
    vix_end: float = 28.0,
    dxy_start: float = 104.0,
    dxy_end: float = 103.0,
    oil_start: float = 78.0,
    oil_end: float = 78.2,
    copper_start: float = 4.20,
    copper_end: float = 3.90,
    us_10y_start: float = 4.20,
    us_10y_end: float = 4.40,
    shanghai_start: float = 3300.0,
    shanghai_end: float = 3200.0,
    usd_vnd_start: float = 25300.0,
    usd_vnd_end: float = 25350.0,
) -> list[dict]:
    """Build 5-day macro history (newest first). Linear interpolation."""
    rows = []
    for day_index in range(5):
        fraction = day_index / 4.0  # 0.0 = newest, 1.0 = oldest
        rows.append(
            {
                "date": f"2026-03-{25 - day_index}",
                "vix_value": vix_end + (vix_start - vix_end) * fraction,
                "dxy_value": dxy_end + (dxy_start - dxy_end) * fraction,
                "oil_price": oil_end + (oil_start - oil_end) * fraction,
                "copper_price": copper_end + (copper_start - copper_end) * fraction,
                "us_10y_yield": us_10y_end + (us_10y_start - us_10y_end) * fraction,
                "shanghai_close": shanghai_end + (shanghai_start - shanghai_end) * fraction,
                "usd_vnd_rate": usd_vnd_end + (usd_vnd_start - usd_vnd_end) * fraction,
            }
        )
    return rows


def _make_regime_history(regimes: list[str]) -> list[dict]:
    """Build regime history (newest first) from a list of regime strings."""
    return [
        {"date": f"2026-03-{25 - index}", "regime": regime, "confidence": 0.8}
        for index, regime in enumerate(regimes)
    ]


# ── compute_indicator_trends ────────────────────────────────────────────


class TestComputeIndicatorTrends:
    def test_ascending_vix_is_up(self):
        history = _make_macro_history(vix_start=18.0, vix_end=28.0)
        trends = compute_indicator_trends(history)
        assert trends["vix"]["direction"] == "UP"
        assert trends["vix"]["latest"] == 28.0
        assert trends["vix"]["oldest"] == 18.0

    def test_descending_dxy_is_down(self):
        history = _make_macro_history(dxy_start=106.0, dxy_end=103.0)
        trends = compute_indicator_trends(history)
        assert trends["dxy"]["direction"] == "DOWN"

    def test_flat_oil_within_threshold(self):
        # 0.5% of 78.0 = 0.39 — so 78.0 to 78.2 is within threshold
        history = _make_macro_history(oil_start=78.0, oil_end=78.2)
        trends = compute_indicator_trends(history)
        assert trends["oil"]["direction"] == "FLAT"

    def test_missing_data_skips_indicator(self):
        history = _make_macro_history()
        # Set vix to None in newest and oldest
        history[0]["vix_value"] = None
        trends = compute_indicator_trends(history)
        assert "vix" not in trends
        # Other indicators should still be present
        assert "dxy" in trends

    def test_empty_history_returns_empty(self):
        assert compute_indicator_trends([]) == {}

    def test_single_entry_returns_empty(self):
        history = _make_macro_history()
        assert compute_indicator_trends([history[0]]) == {}

    def test_formatted_string_contains_arrow(self):
        history = _make_macro_history(vix_start=18.0, vix_end=28.0)
        trends = compute_indicator_trends(history)
        assert "\u2191" in trends["vix"]["formatted"]
        assert "28.0" in trends["vix"]["formatted"]

    def test_flat_formatted_has_no_from(self):
        history = _make_macro_history(oil_start=78.0, oil_end=78.2)
        trends = compute_indicator_trends(history)
        assert "from" not in trends["oil"]["formatted"]
        assert "\u2192" in trends["oil"]["formatted"]


# ── compute_regime_transition ───────────────────────────────────────────


class TestComputeRegimeTransition:
    def test_regime_changed_1_day_ago(self):
        history = _make_regime_history(["ELEVATED", "CALM", "CALM", "CALM", "CALM"])
        result = compute_regime_transition(history)
        assert result is not None
        assert "ELEVATED" in result
        assert "CALM" in result
        assert "escalating" in result

    def test_regime_same_for_all_days(self):
        history = _make_regime_history(["CALM", "CALM", "CALM", "CALM", "CALM"])
        result = compute_regime_transition(history)
        assert result is None

    def test_single_entry_returns_none(self):
        history = _make_regime_history(["CALM"])
        result = compute_regime_transition(history)
        assert result is None

    def test_empty_history_returns_none(self):
        result = compute_regime_transition([])
        assert result is None

    def test_de_escalation_detected(self):
        history = _make_regime_history(["CALM", "ELEVATED", "ELEVATED"])
        result = compute_regime_transition(history)
        assert result is not None
        assert "de-escalating" in result

    def test_change_at_entry_3_still_detected(self):
        """Change at position 2 (3rd entry) is still within the 3-entry window."""
        history = _make_regime_history(["CAUTIOUS", "CAUTIOUS", "CALM", "CALM", "CALM"])
        result = compute_regime_transition(history)
        assert result is not None
        assert "2d ago" in result

    def test_change_beyond_window_not_detected(self):
        """Change at position 3+ is outside the 3-entry check window."""
        history = _make_regime_history(["CAUTIOUS", "CAUTIOUS", "CAUTIOUS", "CALM", "CALM"])
        result = compute_regime_transition(history)
        assert result is None


# ── detect_cross_asset_narratives ───────────────────────────────────────


class TestDetectCrossAssetNarratives:
    def test_fed_hawkish_pattern(self):
        trends = {
            "dxy": {"direction": "UP"},
            "us_10y_yield": {"direction": "UP"},
            "copper": {"direction": "DOWN"},
        }
        narratives = detect_cross_asset_narratives(trends)
        assert "Fed hawkish / EM pressure" in narratives

    def test_geopolitical_escalation(self):
        trends = {
            "oil": {"direction": "UP"},
            "vix": {"direction": "UP"},
        }
        narratives = detect_cross_asset_narratives(trends)
        assert "Geopolitical risk escalation" in narratives

    def test_china_slowdown(self):
        trends = {
            "shanghai": {"direction": "DOWN"},
            "copper": {"direction": "DOWN"},
        }
        narratives = detect_cross_asset_narratives(trends)
        assert "China slowdown / EM drag" in narratives

    def test_no_matching_pattern(self):
        trends = {
            "dxy": {"direction": "FLAT"},
            "vix": {"direction": "FLAT"},
            "oil": {"direction": "FLAT"},
        }
        narratives = detect_cross_asset_narratives(trends)
        assert narratives == []

    def test_empty_trends_returns_empty(self):
        assert detect_cross_asset_narratives({}) == []

    def test_steel_margin_expansion(self):
        trends = {"oil": {"direction": "FLAT"}}
        commodity_prices = {
            "steel_hrc": {"price": 1050, "change_5d_pct": 3.5},
            "iron_ore": {"price": 108, "change_5d_pct": 0.5},
        }
        narratives = detect_cross_asset_narratives(trends, commodity_prices=commodity_prices)
        assert "Steel margin expansion" in narratives

    def test_steel_margin_not_triggered_when_iron_ore_also_up(self):
        trends = {"oil": {"direction": "FLAT"}}
        commodity_prices = {
            "steel_hrc": {"price": 1050, "change_5d_pct": 3.5},
            "iron_ore": {"price": 115, "change_5d_pct": 2.0},
        }
        narratives = detect_cross_asset_narratives(trends, commodity_prices=commodity_prices)
        assert "Steel margin expansion" not in narratives

    def test_input_cost_shock(self):
        trends = {"oil": {"direction": "UP"}}
        commodity_prices = {
            "gas_vn": {"price": 22000, "change_5d_pct": 5.0},
        }
        narratives = detect_cross_asset_narratives(trends, commodity_prices=commodity_prices)
        assert "Input cost shock" in narratives

    def test_oversold_valuation_floor(self):
        trends = {"vix": {"direction": "FLAT"}}
        market_valuation = {"pe_percentile": 10}
        narratives = detect_cross_asset_narratives(trends, market_valuation=market_valuation)
        assert "Oversold + valuation floor" in narratives

    def test_oversold_not_triggered_above_threshold(self):
        trends = {"vix": {"direction": "FLAT"}}
        market_valuation = {"pe_percentile": 20}
        narratives = detect_cross_asset_narratives(trends, market_valuation=market_valuation)
        assert "Oversold + valuation floor" not in narratives

    def test_multiple_narratives_can_fire(self):
        trends = {
            "oil": {"direction": "UP"},
            "vix": {"direction": "UP"},
            "shanghai": {"direction": "DOWN"},
            "copper": {"direction": "DOWN"},
        }
        narratives = detect_cross_asset_narratives(trends)
        assert "Geopolitical risk escalation" in narratives
        assert "China slowdown / EM drag" in narratives


# ── format_trend_block ──────────────────────────────────────────────────


class TestFormatTrendBlock:
    def test_with_trends_transition_narrative(self):
        history = _make_macro_history(vix_start=18.0, vix_end=28.0)
        trends = compute_indicator_trends(history)
        transition = "Regime: ELEVATED (was CALM 1d ago \u2014 escalating)"
        narratives = ["Fed hawkish / EM pressure"]

        result = format_trend_block(trends, transition, narratives)
        assert "## TRENDS (5d)" in result
        assert "VIX:" in result
        assert "Regime: ELEVATED" in result
        assert "Signal: Fed hawkish / EM pressure" in result

    def test_empty_trends_returns_empty_string(self):
        result = format_trend_block({}, None, [])
        assert result == ""

    def test_no_transition_no_narrative(self):
        history = _make_macro_history()
        trends = compute_indicator_trends(history)
        result = format_trend_block(trends, None, [])
        assert "## TRENDS (5d)" in result
        assert "Regime:" not in result
        assert "Signal:" not in result

    def test_multiple_narratives_joined(self):
        trends = {"vix": {"direction": "UP", "formatted": "VIX: 28 (\u2191 from 18, 5d)"}}
        narratives = ["Geopolitical risk escalation", "China slowdown / EM drag"]
        result = format_trend_block(trends, None, narratives)
        assert "Geopolitical risk escalation, China slowdown / EM drag" in result
