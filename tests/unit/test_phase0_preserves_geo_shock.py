"""Phase 0 geo_shock preservation — RC0 regression guard.

Covers the three fail-closed branches in ``fetch_macro_metrics``:

1. STALE — zero-data guard fires when DXY=0 and VIX=0.
2. DEGRADED — a MISSING sentinel is surfaced by any classifier.
3. ERROR — the outer try/except catches an unexpected exception.

Before RC0, each of these branches hardcoded ``geopolitical_shock=None``
and ``global_risk_regime="CAUTIOUS"``. After RC0, all three receive the
pre-fetched ``geo_shock`` as a parameter and thread it through the
output AND respect the regime floor (``sustained_pressure`` floors to
``CAUTIOUS``; ``immediate_shock`` floors to ``ELEVATED``).
"""

from __future__ import annotations

from datetime import date
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from agents.macro import fetch_macro_metrics
from pipeline.types import GeopoliticalShockDict


@pytest.fixture
def sustained_shock() -> GeopoliticalShockDict:
    return cast(
        GeopoliticalShockDict,
        {
            "phase_name": "sustained_pressure",
            "catalyst_event": "TEST Hormuz closure",
            "behavior": "rotate to exporters",
            "impact": "NEGATIVE",
            "affected_tickers": ["GAS", "PLX"],
            "notes": "",
            "catalyst_key": "test_hormuz",
            "days_active": 7,
            "phase_stale": False,
        },
    )


@pytest.fixture
def immediate_shock() -> GeopoliticalShockDict:
    return cast(
        GeopoliticalShockDict,
        {
            "phase_name": "immediate_shock",
            "catalyst_event": "TEST war outbreak",
            "behavior": "full defensive",
            "impact": "NEGATIVE",
            "affected_tickers": ["VN-INDEX"],
            "notes": "",
            "catalyst_key": "test_war",
            "days_active": 1,
            "phase_stale": False,
        },
    )


@pytest.mark.asyncio
async def test_stale_branch_preserves_geo_shock(sustained_shock):
    """Zero DXY + zero VIX branch — still keeps geo_shock + CAUTIOUS floor."""
    stale_payload = {
        "dxy_value": 0.0,
        "dxy_change_pct": 0.0,
        "vix_value": 0.0,
        "vix_change_pct": 0.0,
        "usd_vnd_rate": 25300.0,
        "usd_vnd_source": "sbv",
        "usd_vnd_spread": None,
        "oil_price": 75.0,
        "oil_change_pct": 0.0,
        "oil_source": "vnstock",
        "copper_price": None,
        "copper_change_pct": None,
        "us_10y_yield": None,
        "us_10y_change_pct": None,
        "shanghai_close": None,
        "shanghai_change_pct": None,
        "sp500_close": None,
        "sp500_change_pct": None,
        "nasdaq_close": None,
        "nasdaq_change_pct": None,
        "dow_close": None,
        "dow_change_pct": None,
        "breadth_advance": None,
        "breadth_decline": None,
        "breadth_ratio": None,
    }
    with patch(
        "agents.macro.build._fetch_macro_data",
        new=AsyncMock(return_value=stale_payload),
    ):
        output = await fetch_macro_metrics(date(2099, 1, 1), geo_shock=sustained_shock)

    assert output["data_quality"] == "STALE"
    assert output["geopolitical_shock"] == sustained_shock
    assert output["global_risk_regime"] == "CAUTIOUS"


@pytest.mark.asyncio
async def test_stale_branch_immediate_shock_floors_elevated(immediate_shock):
    """On an immediate_shock morning, STALE must floor to ELEVATED, not CAUTIOUS."""
    stale_payload = {
        "dxy_value": 0.0,
        "dxy_change_pct": 0.0,
        "vix_value": 0.0,
        "vix_change_pct": 0.0,
        "usd_vnd_rate": 25300.0,
        "usd_vnd_source": "sbv",
        "usd_vnd_spread": None,
        "oil_price": 75.0,
        "oil_change_pct": 0.0,
        "oil_source": "vnstock",
        "copper_price": None,
        "copper_change_pct": None,
        "us_10y_yield": None,
        "us_10y_change_pct": None,
        "shanghai_close": None,
        "shanghai_change_pct": None,
        "sp500_close": None,
        "sp500_change_pct": None,
        "nasdaq_close": None,
        "nasdaq_change_pct": None,
        "dow_close": None,
        "dow_change_pct": None,
        "breadth_advance": None,
        "breadth_decline": None,
        "breadth_ratio": None,
    }
    with patch(
        "agents.macro.build._fetch_macro_data",
        new=AsyncMock(return_value=stale_payload),
    ):
        output = await fetch_macro_metrics(date(2099, 1, 1), geo_shock=immediate_shock)

    assert output["geopolitical_shock"] == immediate_shock
    assert output["global_risk_regime"] == "ELEVATED"


@pytest.mark.asyncio
async def test_degraded_branch_preserves_geo_shock_and_floor(immediate_shock):
    """MISSING sentinel (NaN DXY) — still keeps geo_shock + ELEVATED floor."""
    nan_payload = {
        "dxy_value": float("nan"),
        "dxy_change_pct": float("nan"),
        "vix_value": 20.0,
        "vix_change_pct": 0.5,
        "usd_vnd_rate": 25300.0,
        "usd_vnd_source": "sbv",
        "usd_vnd_spread": None,
        "oil_price": 75.0,
        "oil_change_pct": 0.0,
        "oil_source": "vnstock",
        "copper_price": None,
        "copper_change_pct": None,
        "us_10y_yield": None,
        "us_10y_change_pct": None,
        "shanghai_close": None,
        "shanghai_change_pct": None,
        "sp500_close": None,
        "sp500_change_pct": None,
        "nasdaq_close": None,
        "nasdaq_change_pct": None,
        "dow_close": None,
        "dow_change_pct": None,
        "breadth_advance": None,
        "breadth_decline": None,
        "breadth_ratio": None,
    }
    with (
        patch("agents.macro.build._fetch_macro_data", new=AsyncMock(return_value=nan_payload)),
        patch("shared.neon.market.get_macro_history", new=AsyncMock(return_value=[])),
        patch("shared.neon.market.has_upcoming_macro_events", new=AsyncMock(return_value=False)),
    ):
        output = await fetch_macro_metrics(date(2099, 1, 1), geo_shock=immediate_shock)

    assert output["data_quality"] == "DEGRADED"
    assert output["geopolitical_shock"] == immediate_shock
    assert output["global_risk_regime"] == "ELEVATED"


@pytest.mark.asyncio
async def test_exception_branch_preserves_geo_shock(sustained_shock):
    """Outer try/except — unexpected error still preserves geo_shock + floor."""
    with patch(
        "agents.macro.build._fetch_macro_data",
        new=AsyncMock(side_effect=RuntimeError("API meltdown")),
    ):
        output = await fetch_macro_metrics(date(2099, 1, 1), geo_shock=sustained_shock)

    assert output["data_quality"] == "ERROR"
    assert output["geopolitical_shock"] == sustained_shock
    assert output["global_risk_regime"] == "CAUTIOUS"
    assert "API meltdown" in output.get("error", "")


@pytest.mark.asyncio
async def test_exception_branch_no_shock_defaults_cautious():
    """Without a shock, exception branch still defaults to CAUTIOUS (unchanged)."""
    with patch(
        "agents.macro.build._fetch_macro_data",
        new=AsyncMock(side_effect=RuntimeError("API meltdown")),
    ):
        output = await fetch_macro_metrics(date(2099, 1, 1), geo_shock=None)

    assert output["data_quality"] == "ERROR"
    assert output["geopolitical_shock"] is None
    assert output["global_risk_regime"] == "CAUTIOUS"
