"""Unit tests for pipeline data validation layer."""

import pytest

from agents.tools.validation import (
    validate_pipeline_data,
    validate_sector_signals,
)

pytestmark = pytest.mark.usefixtures("mock_trading_config")


# ── validate_pipeline_data ──────────────────────────────────────────────────


def test_validate_pipeline_data_clean():
    """All valid data should produce no issues."""
    technicals = {
        "FPT": {"close": 120.0, "rsi": 45.0, "levels": {"swing_low": 110.0, "swing_high": 130.0}},
    }
    cash_balance = 80_000_000.0
    holdings = [{"ticker": "FPT", "plan_type": "SWING", "avg_cost": 100.0}]
    report = validate_pipeline_data(technicals, cash_balance, holdings)
    assert not report.has_issues
    assert not report.warnings
    assert not report.blockers
    assert not report.excluded_tickers


def test_validate_pipeline_data_invalid_price():
    """Ticker with price <= 0 should be excluded as blocker."""
    technicals = {"BAD": {"close": -1.0, "rsi": 50.0, "levels": {}}}
    report = validate_pipeline_data(technicals, 80_000_000.0, [])
    assert "BAD" in report.excluded_tickers
    assert any("BAD" in b for b in report.blockers)


def test_validate_pipeline_data_extreme_rsi():
    """Extreme RSI values should produce warnings."""
    technicals = {"HIGH": {"close": 50.0, "rsi": 97.0, "levels": {}}}
    report = validate_pipeline_data(technicals, 80_000_000.0, [])
    assert any("HIGH" in w and "RSI" in w for w in report.warnings)


def test_validate_pipeline_data_stale_levels():
    """swing_low >= close should warn about stale levels."""
    technicals = {
        "STALE": {
            "close": 100.0,
            "rsi": 50.0,
            "levels": {"swing_low": 105.0, "swing_high": 120.0},  # swing_low > close
        }
    }
    report = validate_pipeline_data(technicals, 80_000_000.0, [])
    assert any("STALE" in w and "swing_low" in w for w in report.warnings)


def test_validate_pipeline_data_low_cash():
    """Cash below reserve should warn."""
    report = validate_pipeline_data({}, 8_000_000.0, [])
    assert any("reserve" in w.lower() for w in report.warnings)


def test_validate_pipeline_data_near_reserve():
    """Cash just above reserve should warn about minimal entries."""
    report = validate_pipeline_data({}, 13_000_000.0, [])
    assert any("near reserve" in w.lower() or "minimal" in w.lower() for w in report.warnings)


def test_validate_pipeline_data_pl_mismatch():
    """Holdings with P/L mismatch beyond 2% should warn."""
    holdings = [
        {
            "ticker": "FPT",
            "plan_type": "SWING",
            "avg_cost": 100_000.0,
            "current_price_vnd": 120_000.0,
            "pct_from_entry": 5.0,  # should be ~20%
        }
    ]
    report = validate_pipeline_data({}, 80_000_000.0, holdings)
    assert any("FPT" in w and "P/L mismatch" in w for w in report.warnings)


def test_validate_pipeline_data_error_ticker_excluded():
    """Ticker with error field should be excluded (warning, not blocker)."""
    technicals = {"ERR": {"error": "API timeout"}}
    report = validate_pipeline_data(technicals, 80_000_000.0, [])
    assert "ERR" in report.excluded_tickers
    assert any("ERR" in w for w in report.warnings)


def test_validate_pipeline_data_extreme_pl():
    """Extreme P/L values should produce warnings."""
    holdings = [
        {
            "ticker": "FPT",
            "plan_type": "SWING",
            "avg_cost": 50_000.0,
            "current_price_vnd": 150_000.0,
            "pct_from_entry": 200.0,
        }
    ]
    report = validate_pipeline_data({}, 80_000_000.0, holdings)
    assert any("FPT" in w and "extreme" in w.lower() for w in report.warnings)


def test_validate_pipeline_data_dual_listed_ticker():
    """Dual-listed ticker (SWING + LONGTERM) validates each slice."""
    holdings = [
        {
            "ticker": "XYZ",
            "plan_type": "SWING",
            "avg_cost": 78_000,
            "current_price_vnd": 76_000,
            "pct_from_entry": -2.6,  # within tolerance of -2.56%
        },
        {
            "ticker": "XYZ",
            "plan_type": "LONGTERM",
            "avg_cost": 80_000,
            "current_price_vnd": 76_000,
            "pct_from_entry": -5.0,  # expected -5.00%
        },
    ]
    report = validate_pipeline_data({}, 80_000_000.0, holdings)
    # Both slices pass tolerance — no mismatch warnings
    assert not any("P/L mismatch" in w for w in report.warnings)
    assert not any("extreme" in w.lower() for w in report.warnings)


# ── validate_sector_signals ─────────────────────────────────────────────────


def test_validate_sector_signals_clean():
    """BUY signal with good data should not be flagged."""
    signals = [{"signal": "BUY", "ticker": "FPT", "sector": "technology"}]
    technicals = {"FPT": {"rsi": 42.0, "levels": {"swing_low": 110.0, "nearest_support": 112.0}}}
    flagged = validate_sector_signals(signals, technicals)
    assert len(flagged) == 0


def test_validate_sector_signals_overbought():
    """BUY signal with RSI > 70 should be flagged."""
    signals = [{"signal": "BUY", "ticker": "FPT", "sector": "technology"}]
    technicals = {"FPT": {"rsi": 75.0, "levels": {"swing_low": 110.0}}}
    flagged = validate_sector_signals(signals, technicals)
    assert len(flagged) == 1
    assert "overbought" in flagged[0]["issues"][0]


def test_validate_sector_signals_cold_sector():
    """BUY in cold sector should be flagged."""
    signals = [{"signal": "BUY", "ticker": "VHM", "sector": "real_estate"}]
    technicals = {"VHM": {"rsi": 45.0, "levels": {"swing_low": 80.0}}}
    rotation = {"hot_sectors": ["technology"], "cold_sectors": ["real_estate"]}
    flagged = validate_sector_signals(signals, technicals, rotation)
    assert len(flagged) == 1
    assert "cold sector" in flagged[0]["issues"][0]


def test_validate_sector_signals_no_support():
    """BUY without support level should be flagged."""
    signals = [{"signal": "BUY", "ticker": "FPT", "sector": "technology"}]
    technicals = {"FPT": {"rsi": 45.0, "levels": {}}}
    flagged = validate_sector_signals(signals, technicals)
    assert len(flagged) == 1
    assert "no support" in flagged[0]["issues"][0]


def test_validate_sector_signals_non_buy_not_flagged():
    """SELL/HOLD signals should not be validated."""
    signals = [
        {"signal": "SELL", "ticker": "FPT", "sector": "technology"},
        {"signal": "HOLD", "ticker": "VHM", "sector": "real_estate"},
    ]
    technicals = {"FPT": {"rsi": 75.0, "levels": {}}, "VHM": {"rsi": 80.0, "levels": {}}}
    flagged = validate_sector_signals(signals, technicals)
    assert len(flagged) == 0


def test_validate_sector_signals_multiple_issues():
    """BUY signal can have multiple issues simultaneously."""
    signals = [{"signal": "BUY", "ticker": "VHM", "sector": "real_estate"}]
    technicals = {"VHM": {"rsi": 78.0, "levels": {}}}  # overbought + no support
    rotation = {"hot_sectors": [], "cold_sectors": ["real_estate"]}
    flagged = validate_sector_signals(signals, technicals, rotation)
    assert len(flagged) == 1
    assert len(flagged[0]["issues"]) >= 2  # overbought + cold sector + no support
