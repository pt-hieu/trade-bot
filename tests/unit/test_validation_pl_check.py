"""Tests for validation.py P/L consistency check.

Group 8: validation previously read `pl_pct`/`pnl_pct` (non-existent keys
on portfolio rows) so the consistency check never fired. Now reads
canonical `pct_from_entry`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def _trading_config():
    from shared.trading_config import TradingConfig

    return TradingConfig()


def test_pl_mismatch_is_flagged(_trading_config):
    """Synthetic -12.3% brief vs -10.1% actual → flag via calculated expected."""
    from agents.tools.validation import validate_pipeline_data

    # avg=80000, current=72000 → expected -10.0%. Stored -12.3% → >2% drift.
    holdings = [
        {
            "ticker": "FPT",
            "plan_type": "SWING",
            "shares": 100,
            "avg_cost": 80000,
            "current_price_vnd": 72000,
            "pct_from_entry": -12.3,
        }
    ]
    with patch(
        "agents.tools.validation.get_trading_config",
        return_value=_trading_config,
    ):
        report = validate_pipeline_data(
            technicals={},
            cash_balance=50_000_000,
            holdings=holdings,
            macro=None,
        )
    assert any("P/L mismatch" in w for w in report.warnings)
    assert any("-12.3%" in w for w in report.warnings)


def test_pl_within_tolerance_does_not_flag(_trading_config):
    """Within 2% tolerance → no warning."""
    from agents.tools.validation import validate_pipeline_data

    # expected -10.0%, stored -10.1% (within 2% tolerance)
    holdings = [
        {
            "ticker": "FPT",
            "plan_type": "SWING",
            "shares": 100,
            "avg_cost": 80000,
            "current_price_vnd": 72000,
            "pct_from_entry": -10.1,
        }
    ]
    with patch(
        "agents.tools.validation.get_trading_config",
        return_value=_trading_config,
    ):
        report = validate_pipeline_data(
            technicals={},
            cash_balance=50_000_000,
            holdings=holdings,
            macro=None,
        )
    assert not any("P/L mismatch" in w for w in report.warnings)


def test_legacy_pnl_pct_key_does_not_hide_mismatch(_trading_config):
    """Previously masked bug: `pl_pct`/`pnl_pct` fallback never matched real key."""
    from agents.tools.validation import validate_pipeline_data

    # Row has legacy key only — new code must treat as "P/L unknown" (no
    # mismatch warning) rather than silently passing because the fallback
    # chain succeeded on a wrong value.
    holdings = [
        {
            "ticker": "FPT",
            "plan_type": "SWING",
            "shares": 100,
            "avg_cost": 80000,
            "current_price_vnd": 72000,
            "pnl_pct": -10.1,  # legacy key
        }
    ]
    with patch(
        "agents.tools.validation.get_trading_config",
        return_value=_trading_config,
    ):
        report = validate_pipeline_data(
            technicals={},
            cash_balance=50_000_000,
            holdings=holdings,
            macro=None,
        )
    # No P/L warning because pct_from_entry is missing (read as None).
    assert not any("P/L mismatch" in w for w in report.warnings)
    assert not any("extreme P/L" in w for w in report.warnings)
