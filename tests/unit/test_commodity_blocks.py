"""Unit tests for commodity block formatters and per-ticker transmission."""

from pipeline.context_blocks_commodity import format_commodity_block
from pipeline.context_blocks_ticker import format_ticker_briefing

# ── Fixtures ────────────────────────────────────────────────────────────


def _make_commodity_prices() -> dict:
    return {
        "gold_global": {
            "price": 2345.6,
            "change_5d_pct": -0.8,
            "change_20d_pct": 2.1,
            "unit": "USD/oz",
        },
        "steel_hrc": {
            "price": 1045.0,
            "change_5d_pct": 3.5,
            "change_20d_pct": -1.2,
            "unit": "USD/t",
        },
        "iron_ore": {
            "price": 108.0,
            "change_5d_pct": -2.1,
            "change_20d_pct": 5.0,
            "unit": "USD/t",
        },
    }


# ── Commodity Block ─────────────────────────────────────────────────────


class TestCommodityBlock:
    def test_basic_format(self):
        result = format_commodity_block(_make_commodity_prices())
        assert "## COMMODITIES" in result
        assert "Gold:" in result
        assert "Steel HRC:" in result
        assert "Iron Ore:" in result

    def test_change_shown(self):
        result = format_commodity_block(_make_commodity_prices())
        assert "+3.5% 5d" in result
        assert "-2.1% 5d" in result

    def test_empty_returns_empty(self):
        assert format_commodity_block({}) == ""

    def test_gold_capitulation_signal(self):
        prices = {"gold_global": {"price": 2100, "change_5d_pct": -8.0, "unit": "USD/oz"}}
        result = format_commodity_block(prices)
        assert "GOLD CAPITULATION" in result
        assert "-8.0%" in result

    def test_no_capitulation_when_gold_normal(self):
        result = format_commodity_block(_make_commodity_prices())
        assert "CAPITULATION" not in result

    def test_skips_error_entries(self):
        prices = {
            "gold_global": {"error": "fetch failed"},
            "steel_hrc": _make_commodity_prices()["steel_hrc"],
        }
        result = format_commodity_block(prices)
        assert "Steel HRC:" in result
        assert "error" not in result.lower()


# ── Per-Ticker Commodity Transmission ────────────────────────────────────


class TestCommodityTransmission:
    """Test TAILWIND/HEADWIND transmission from commodity prices to ticker briefings."""

    def _make_profile_with_sensitivity(self, factor: str, direction: str) -> dict:
        return {
            "macro_sensitivities": [{"factor": factor, "direction": direction}],
        }

    def test_positive_sensitivity_price_up_is_tailwind(self):
        profile = self._make_profile_with_sensitivity("steel_price", "POSITIVE")
        commodities = {"steel_hrc": {"price": 1045, "change_5d_pct": 3.5, "unit": "USD/t"}}
        result = format_ticker_briefing(
            ticker="HPG",
            technicals=None,
            company_profile=profile,
            commodity_prices=commodities,
        )
        assert "TAILWIND" in result
        assert "Steel HRC" in result

    def test_positive_sensitivity_price_down_is_headwind(self):
        profile = self._make_profile_with_sensitivity("steel_price", "POSITIVE")
        commodities = {"steel_hrc": {"price": 1045, "change_5d_pct": -3.5, "unit": "USD/t"}}
        result = format_ticker_briefing(
            ticker="HPG",
            technicals=None,
            company_profile=profile,
            commodity_prices=commodities,
        )
        assert "HEADWIND" in result

    def test_negative_sensitivity_price_up_is_headwind(self):
        profile = self._make_profile_with_sensitivity("oil_price", "NEGATIVE")
        commodities = {"oil_crude": {"price": 78, "change_5d_pct": 5.0, "unit": "USD/bbl"}}
        result = format_ticker_briefing(
            ticker="VJC",
            technicals=None,
            company_profile=profile,
            commodity_prices=commodities,
        )
        assert "HEADWIND" in result
        assert "Oil" in result

    def test_small_change_skipped(self):
        """Changes <1% are not material — should not show transmission."""
        profile = self._make_profile_with_sensitivity("steel_price", "POSITIVE")
        commodities = {"steel_hrc": {"price": 1045, "change_5d_pct": 0.5, "unit": "USD/t"}}
        result = format_ticker_briefing(
            ticker="HPG",
            technicals=None,
            company_profile=profile,
            commodity_prices=commodities,
        )
        assert "TAILWIND" not in result
        assert "HEADWIND" not in result

    def test_no_commodity_prices(self):
        profile = self._make_profile_with_sensitivity("steel_price", "POSITIVE")
        result = format_ticker_briefing(
            ticker="HPG",
            technicals=None,
            company_profile=profile,
            commodity_prices=None,
        )
        assert "Commodity:" not in result
