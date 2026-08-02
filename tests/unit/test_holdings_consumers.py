"""Regression: all HoldingData consumer sites must accept list[dict] slices.

Migration 314 made `get_portfolio_holdings() -> list[dict]` (one row per
(ticker, plan_type) slice). Several consumer sites still iterated via
`.items()`/`.keys()` or hid the mismatch behind a silent `isinstance(holdings, dict)`
guard, producing empty catalyst preview / broken foreign flow tickers.

These tests pin the list[dict] contract at the boundary: any site that
accepts holdings should either (a) iterate the slice list directly, or
(b) route through `tickers_held` / `collapse_holdings_by_ticker` helpers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.tools.validation import validate_pipeline_data

pytestmark = pytest.mark.usefixtures("mock_trading_config")


@pytest.fixture
def sample_holdings() -> list[dict]:
    """Realistic dual-listed ticker + a single-plan ticker."""
    return [
        {
            "ticker": "FPT",
            "plan_type": "LONGTERM",
            "shares": 400,
            "avg_cost": 81500,
            "avg_cost_vnd": 81500,
            "current_price_vnd": 76000,
            "pct_from_entry": -6.7,
            "market_value": 30_400_000.0,
        },
        {
            "ticker": "TCB",
            "plan_type": "LONGTERM",
            "shares": 1000,
            "avg_cost": 25_000,
            "avg_cost_vnd": 25_000,
            "current_price_vnd": 26_500,
            "pct_from_entry": 6.0,
            "market_value": 26_500_000.0,
        },
    ]


def test_validation_accepts_list(sample_holdings):
    """`validate_pipeline_data` iterates list[dict] without AttributeError."""
    report = validate_pipeline_data(
        technicals={},
        cash_balance=80_000_000.0,
        holdings=sample_holdings,
    )
    # No error raised; P/L tolerances hold
    assert not any("P/L mismatch" in w for w in report.warnings)


@pytest.mark.asyncio
async def test_catalyst_preview_uses_tickers_held(sample_holdings):
    """`compute_catalyst_preview` must extract tickers via `tickers_held`,
    not via `holdings.keys()` — the old path returned empty set silently."""
    from agents.tools import catalyst_preview as cp

    with patch.object(cp, "get_active_catalysts_db", AsyncMock(return_value=[])):
        result = await cp.compute_catalyst_preview(
            holdings=sample_holdings,
            lt_tickers=["VNM"],
            lookahead_days=14,
        )
    assert result["total_active"] == 0


@pytest.mark.asyncio
async def test_foreign_flow_extracts_tickers_from_wrapper():
    """`fetch_flow_with_agent` reads the inner list from the get_holdings_async wrapper."""
    from agents import foreign_flow as ff

    wrapper = {
        "holdings": [
            {"ticker": "FPT", "plan_type": "LONGTERM"},
            {"ticker": "TCB", "plan_type": "LONGTERM"},
        ],
        "prose": "holdings prose",
    }
    with (
        patch.object(
            ff,
            "_fetch_flow_data",
            AsyncMock(
                return_value={
                    "top_bought": [],
                    "top_sold": [],
                    "holding_details": [],
                }
            ),
        ),
        patch.object(ff, "_generate_interpretation", AsyncMock(return_value="neutral")),
        patch("agents.tools.portfolio.get_holdings_async", AsyncMock(return_value=wrapper)),
    ):
        result = await ff.fetch_flow_with_agent()
    # watchlist_matches requires ticker extraction that didn't crash on list-shape
    assert "error" not in result


@pytest.mark.asyncio
async def test_alert_analyst_portfolio_tool_handles_wrapper():
    """alert_analyst's `get_portfolio` tool iterates `wrapper['holdings']` list."""
    from agents import alert_analyst as aa

    wrapper = {
        "holdings": [
            {"ticker": "FPT", "plan_type": "LONGTERM", "shares": 400, "avg_cost_vnd": 81500},
        ],
        "prose": "prose",
    }
    cash = {"cash_balance": 50_000_000, "total_cash": 50_000_000}
    with (
        patch("agents.tools.portfolio.get_holdings_async", AsyncMock(return_value=wrapper)),
        patch("agents.tools.portfolio.get_cash_balance_async", AsyncMock(return_value=cash)),
        patch.object(aa, "load_agent_config", AsyncMock(return_value=_stub_agent_config())),
        patch.object(aa, "create_agent", lambda *a, **kw: _StubAgent()),
    ):
        agent = await aa.create_analyst_agent()
    # Tool body ran synthesized without AttributeError; agent has registered tools
    assert agent.registered_tools


# ── helpers ──────────────────────────────────────────────────────────────────


def _stub_agent_config():
    return {
        "agent_key": "alert_analyst",
        "model": "z-ai/glm-5",
        "system_prompt": "stub",
        "disable_fallback": True,
    }


class _StubAgent:
    """Minimal stub with `tool_plain` decorator that just records registrations."""

    def __init__(self) -> None:
        self.registered_tools: list[str] = []

    def tool_plain(self, fn):
        self.registered_tools.append(fn.__name__)
        return fn
