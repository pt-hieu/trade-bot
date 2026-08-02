"""Shared fixtures for pipeline.context_blocks test splits."""

from __future__ import annotations


def _make_market_level(**overrides) -> dict:
    defaults = {
        "regime": "BEARISH",
        "vnindex_close": 1180.5,
        "rsi": 42.3,
        "support": 1150.0,
        "resistance": 1220.0,
        "history": [
            {"date": "2026-03-25", "regime": "BEARISH"},
            {"date": "2026-03-24", "regime": "NEUTRAL"},
        ],
    }
    defaults.update(overrides)
    return defaults


def _make_macro_metrics(**overrides) -> dict:
    defaults = {
        "global_risk_regime": "CAUTIOUS",
        "vix_value": 28.5,
        "vix_change_pct": 2.1,
        "dxy_value": 104.2,
        "dxy_change_pct": 0.3,
        "usd_vnd_rate": 25350,
        "oil_price": 78.5,
        "oil_change_pct": 1.1,
        "copper_price": 4.12,
        "copper_change_pct": -0.5,
        "us_10y_yield": 4.28,
        "us_10y_change_pct": 0.02,
        "shanghai_close": 3200.0,
        "shanghai_change_pct": -0.5,
        "sp500_close": 5500.0,
        "sp500_change_pct": -0.3,
        "breadth_advance": 245,
        "breadth_decline": 180,
        "breadth_ratio": 1.36,
        "interpretation": "Markets showing caution amid rising VIX.",
    }
    defaults.update(overrides)
    return defaults


def _make_sensitivities(*factors):
    """Build macro_sensitivities list from (factor, direction, magnitude) tuples."""
    return [
        {"factor": factor, "direction": direction, "magnitude": magnitude}
        for factor, direction, magnitude in factors
    ]


def _make_geo_shock(**overrides):
    defaults = {
        "phase_name": "sustained_pressure",
        "catalyst_event": "Iran closes Strait of Hormuz",
        "catalyst_key": "hormuz_closure_2026",
        "affected_tickers": ["HVN", "VJC", "PLX", "PVD", "GAS", "HPG"],
        "impact": "NEGATIVE",
        "notes": "Oil spike risk",
    }
    defaults.update(overrides)
    return defaults
