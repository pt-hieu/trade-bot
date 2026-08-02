"""Tests for the deterministic MY HOLDINGS renderer.

Covers two regressions the LLM-authored version was producing:
- A ``GEO_BENEFICIARY`` badge on holdings not in the impacted set.
- ``Trailing stop: <entry_price>`` where the trailing stop was inactive.

The renderer reads everything structural from ``HoldingAction``; the LLM
only contributes qualitative thesis paragraphs.
"""

from __future__ import annotations

from pipeline.rendering import (
    derive_holding_actions,
    render_my_holdings,
)


def _position_alerts_fpt_hold() -> dict:
    return {
        "alerts": [
            {
                "ticker": "FPT",
                "action": "HOLD",
                "urgency": "LOW",
                "reason": "Thesis intact; Q2 backlog in line",
            }
        ]
    }


def _portfolio_rows_fpt(**overrides) -> dict:
    row: dict = {
        "avg_cost_vnd": 80000,
        "current_price_vnd": 81600,
        "pct_from_entry": 2.0,
        "catastrophic_floor_vnd": 78000,
        "breakeven_stop_vnd": 84800,
        "trailing_stop_vnd": None,
    }
    row.update(overrides)
    return {"FPT": row}


class TestGeoBadgeHallucinationProtection:
    def test_no_geo_badge_when_set_empty(self):
        """FPT must not show GEO_VICTIM when the victim set is empty."""
        actions = derive_holding_actions(
            _position_alerts_fpt_hold(),
            holdings_tickers=["FPT"],
            portfolio_rows=_portfolio_rows_fpt(),
            impacted_tickers_victim=set(),
        )
        text = render_my_holdings(actions, {"FPT": "Thesis intact."})
        assert "GEO_VICTIM" not in text
        assert "GEO_BENEFICIARY" not in text

    def test_geo_victim_only_when_in_set(self):
        actions = derive_holding_actions(
            _position_alerts_fpt_hold(),
            holdings_tickers=["FPT"],
            portfolio_rows=_portfolio_rows_fpt(),
            impacted_tickers_victim={"FPT"},
        )
        text = render_my_holdings(actions, {})
        assert "GEO_VICTIM" in text


class TestTrailingStopFabricationProtection:
    def test_no_trailing_stop_line_when_inactive(self):
        """When trailing_stop_vnd is None, the 'Trailing stop: ...' line is omitted."""
        actions = derive_holding_actions(
            _position_alerts_fpt_hold(),
            holdings_tickers=["FPT"],
            portfolio_rows=_portfolio_rows_fpt(trailing_stop_vnd=None),
        )
        text = render_my_holdings(actions, {})
        assert "Trailing stop" not in text

    def test_trailing_stop_rendered_when_active(self):
        actions = derive_holding_actions(
            _position_alerts_fpt_hold(),
            holdings_tickers=["FPT"],
            portfolio_rows=_portfolio_rows_fpt(trailing_stop_vnd=88000),
        )
        text = render_my_holdings(actions, {})
        assert "Trailing stop: 88,000" in text


class TestDeterministicFields:
    def test_catastrophic_floor_from_portfolio_not_llm(self):
        actions = derive_holding_actions(
            _position_alerts_fpt_hold(),
            holdings_tickers=["FPT"],
            portfolio_rows=_portfolio_rows_fpt(),
        )
        text = render_my_holdings(actions, {"FPT": "qualitative thesis"})
        assert "Catastrophic floor: 78,000" in text
        assert "Entry: 80,000" in text
        assert "Current: 86,200" in text
        assert "P/L: +2.0%" in text

    def test_thesis_paragraph_rendered_verbatim(self):
        actions = derive_holding_actions(
            _position_alerts_fpt_hold(),
            holdings_tickers=["FPT"],
            portfolio_rows=_portfolio_rows_fpt(),
        )
        thesis = "Backlog cushion holds; monitoring momentum cooldown."
        text = render_my_holdings(actions, {"FPT": thesis})
        assert thesis in text

    def test_missing_portfolio_row_collapses_gracefully(self):
        actions = derive_holding_actions(
            _position_alerts_fpt_hold(),
            holdings_tickers=["FPT"],
            portfolio_rows=None,
        )
        text = render_my_holdings(actions, {})
        assert "MY HOLDINGS" in text
        assert "HOLD FPT" in text
        # No crash, no fabricated stops.
        assert "Catastrophic floor" not in text
        assert "Trailing stop" not in text


class TestEmptyState:
    def test_empty_actions_produces_header_with_empty_note(self):
        text = render_my_holdings([], {})
        assert "MY HOLDINGS" in text
        assert "No open positions today" in text
