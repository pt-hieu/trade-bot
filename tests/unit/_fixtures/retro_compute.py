"""Shared pytest fixtures for retro/compute test splits."""

from __future__ import annotations

import pytest


@pytest.fixture
def eod_prices():
    """EOD prices in thousands VND (vnstock format)."""
    return {
        "TCB": {"open": 34.85, "high": 35.9, "low": 34.8, "close": 35.9, "volume": 11603200},
        "HDB": {"open": 27.0, "high": 27.5, "low": 26.5, "close": 27.2, "volume": 5000000},
        "VHM": {"open": 95.0, "high": 101.0, "low": 94.5, "close": 100.7, "volume": 8000000},
        "GAS": {"open": 80.0, "high": 80.5, "low": 75.0, "close": 75.5, "volume": 3000000},
        "FPT": {"open": 99.0, "high": 99.5, "low": 98.0, "close": 99.2, "volume": 4000000},
    }


@pytest.fixture
def buy_recs():
    """Recommendations with entry/stop/target in VND integers (DB format)."""
    return [
        {
            "ticker": "HDB",
            "action": "BUY",
            "entry_price": 26800,
            "stop_price": 26200,
            "target_price": 30000,
        },
        {
            "ticker": "TCB",
            "action": "BUY",
            "entry_price": 34000,
            "stop_price": 33000,
            "target_price": 38000,
        },
    ]
