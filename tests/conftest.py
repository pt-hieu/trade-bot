"""
Shared pytest fixtures for swingy tests.
"""

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add scripts to path early so shared imports work
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Ensure no real API keys leak into tests."""
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)


@pytest.fixture
def mock_db_url(monkeypatch):
    """Provide a fake database URL."""
    monkeypatch.setenv("NEON_DATABASE_URL", "postgresql://test:test@localhost:5432/test")


def load_fixture(filename: str) -> dict | list:
    """Load a JSON fixture file."""
    filepath = FIXTURES_DIR / filename
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_prices() -> dict:
    """Sample prices data."""
    return {
        "TCB": {
            "date": "2026-01-30 00:00:00",
            "open": 34850,
            "high": 35900,
            "low": 34800,
            "close": 35900,
            "volume": 11603200,
        },
        "FPT": {
            "date": "2026-01-30 00:00:00",
            "open": 145000,
            "high": 147500,
            "low": 144000,
            "close": 146800,
            "volume": 5234100,
        },
    }


@pytest.fixture
def sample_technicals() -> dict:
    """Sample technicals data."""
    return {
        "TCB": {
            "rsi": 36.36,
            "ma20": 35.98,
            "ma50": 34.74,
            "macd": 0.12,
            "macd_signal": 0.29,
            "macd_histogram": -0.17,
            "price_vs_ma20": "below",
            "price_vs_ma50": "above",
            "levels": {
                "swing_high": 36.9,
                "swing_high_date": "2026-01-23",
                "swing_low": 33.05,
                "swing_low_date": "2025-12-26",
                "range_20d_high": 38.2,
                "range_20d_low": 33.8,
                "nearest_support": 34.74,
                "nearest_resistance": 35.98,
            },
            "pattern": {"pattern": None, "signal": None},
            "trend": {"trend": "SIDEWAYS", "strength": "weak", "momentum": "neutral"},
            "analysis": "TCB: SIDEWAYS (weak). RSI 36 approaching oversold.",
        },
    }


@pytest.fixture
def sample_learnings() -> dict:
    """Sample learnings structure (mirrors in-memory dict shape)."""
    return {
        "summary": {
            "total_days": 10,
            "overall_win_rate": 0.65,
        },
        "winning_patterns": [
            {
                "pattern": "Banking RSI < 35",
                "win_rate": 0.75,
                "actionable_rule": "Buy banking when RSI < 35",
            },
            {
                "pattern": "BUY on support bounce",
                "win_rate": 0.70,
                "actionable_rule": "Buy when price bounces from support",
            },
        ],
        "losing_patterns": [
            {
                "pattern": "BUY on RISK_OFF",
                "loss_rate": 0.6,
                "avoid_rule": "Avoid buys in RISK_OFF regime",
            },
        ],
        "sector_insights": [
            {"sector": "banking", "bias": "Strong/Resilient", "recent_accuracy": 0.7},
            {"sector": "real_estate", "bias": "Weak/Choppy", "recent_accuracy": 0.5},
            {"sector": "technology", "bias": "Mixed", "recent_accuracy": 0.6},
        ],
        "ticker_insights": [
            {"ticker": "TCB", "recent_accuracy": 75},
            {"ticker": "FPT", "recent_accuracy": 80},
            {"ticker": "VHM", "recent_accuracy": 25},
        ],
        "midday_patterns": {
            "days_with_midday": 5,
            "adjustment_win_rate": 0.6,
            "when_helpful": ["reversal days"],
            "when_harmful": ["trend continuation days"],
        },
        "trading_mode_patterns": {
            "mode_compliance_rate": 0.9,
            "mode_violations": [],
        },
        "rotation_patterns": {
            "total_days": 10,
            "overall_accuracy": 0.7,
            "hot_hit_rate": 0.65,
            "cold_hit_rate": 0.75,
            "avg_hot_vs_market": 1.2,
            "avg_cold_vs_market": -0.8,
            "sector_rotation_score": {
                "banking": {"as_hot": 0.8, "as_cold": 0.6},
                "technology": {"as_hot": 0.7, "as_cold": 0.5},
            },
        },
        "macro_patterns": {
            "total_days": 10,
            "overall_accuracy": 0.8,
            "regime_accuracy": {},
            "false_alarms": 2,
            "missed_drops": 1,
        },
        "daily_records": [
            {
                "date": "2026-01-29",
                "rotation_evaluation": {
                    "hot_sectors": ["banking"],
                    "cold_sectors": ["real_estate"],
                    "hot_hit_rate": 0.8,
                    "cold_hit_rate": 0.7,
                    "rotation_effective": True,
                    "market_regime": "RISK_ON",
                    "sector_returns": {"banking": 1.5, "real_estate": -0.5},
                    "market_avg_return": 0.5,
                },
            },
        ],
    }


@pytest.fixture
def mock_research_dir(tmp_path):
    """Create a temporary research directory."""
    scan_date = date(2026, 1, 30)
    research_dir = tmp_path / "research" / scan_date.strftime("%Y-%m-%d")
    research_dir.mkdir(parents=True)
    return tmp_path / "research"


@pytest.fixture
def mock_swing_watchlist() -> dict[str, list[str]]:
    """Mock swing watchlist data."""
    return {
        "banking": ["TCB", "VCB", "BID"],
        "technology": ["FPT", "MWG"],
        "real_estate": ["VHM", "NLG"],
    }


@pytest.fixture
def mock_portfolio_holdings() -> list[dict]:
    """Mock portfolio holdings data (list[HoldingData] — migration 2026-04-20)."""
    return [
        {
            "ticker": "NLG",
            "plan_type": "SWING",
            "shares": 1000,
            "avg_cost": 30000,
            "avg_cost_vnd": 30000.0,
            "type": "Stock",
            "current_price_vnd": 31500,
            "market_value": 31500000.0,
            "slice_weight_pct": 12.5,
            "ticker_weight_pct": 12.5,
            "pct_from_entry": 5.0,
            "breakeven_stop": 28500,
        },
        {
            "ticker": "TCB",
            "plan_type": "SWING",
            "shares": 500,
            "avg_cost": 35000,
            "avg_cost_vnd": 35000.0,
            "type": "Stock",
            "current_price_vnd": 35900,
            "market_value": 17950000.0,
            "slice_weight_pct": 8.3,
            "ticker_weight_pct": 8.3,
            "pct_from_entry": 2.6,
            "breakeven_stop": 33000,
        },
    ]


@pytest.fixture
def mock_longterm_watchlist() -> dict[str, dict]:
    """Mock long-term watchlist data."""
    return {
        "FPT": {"entry_zone": 95000, "conviction": "High", "sector": "Technology"},
        "TCB": {"entry_zone": 35000, "conviction": "High", "sector": "Banking"},
        "VHM": {"entry_zone": 115000, "conviction": "Medium-High", "sector": "Real Estate"},
    }


@pytest.fixture
def mock_trades() -> list[dict]:
    """Mock recent trades data."""
    return [
        {
            "ticker": "TCB",
            "entry_date": "2026-01-15",
            "entry_price": 34500,
            "shares": 500,
            "strategy": "BOUNCE",
            "status": "OPEN",
        },
        {
            "ticker": "FPT",
            "entry_date": "2026-01-10",
            "entry_price": 145000,
            "shares": 100,
            "strategy": "TREND",
            "status": "CLOSED",
            "exit_date": "2026-01-20",
            "exit_price": 150000,
            "pl_pct": 3.5,
        },
    ]


@pytest.fixture
def mock_active_goal() -> dict:
    """Mock active goal data."""
    return {
        "id": 1,
        "name": "January 2026",
        "target": 5000000,
        "realized": 1500000,
        "start_date": "2026-01-01",
        "deadline": "2026-01-31",
        "goal_type": "Monthly",
    }


@pytest.fixture
def mock_neon_module(
    mock_swing_watchlist,
    mock_portfolio_holdings,
    mock_longterm_watchlist,
    mock_trades,
    mock_active_goal,
    sample_learnings,
):
    """Create mock for the shared.neon module."""
    mock = MagicMock()

    # Create async mock functions
    async def get_swing_watchlist():
        return mock_swing_watchlist

    async def get_longterm_watchlist():
        return mock_longterm_watchlist

    async def get_portfolio_holdings():
        return mock_portfolio_holdings

    async def get_cash_balance():
        return 80_000_000  # 80M VND

    async def get_recent_trades(limit=10):
        return mock_trades[:limit]

    async def get_active_goal():
        return mock_active_goal

    async def get_learnings_summary():
        return sample_learnings.get("summary", {})

    async def get_winning_patterns(sector=None, action=None, limit=5):
        patterns = sample_learnings.get("winning_patterns", [])
        if sector:
            patterns = [p for p in patterns if sector.lower() in p.get("pattern", "").lower()]
        if action:
            patterns = [p for p in patterns if action.upper() in p.get("pattern", "").upper()]
        return [
            {"pattern": p["pattern"], "win_rate": p["win_rate"], "rule": p["actionable_rule"]}
            for p in patterns[:limit]
        ]

    async def get_losing_patterns(action=None, limit=5):
        patterns = sample_learnings.get("losing_patterns", [])
        if action:
            patterns = [p for p in patterns if action.upper() in p.get("pattern", "").upper()]
        return [
            {"pattern": p["pattern"], "loss_rate": p["loss_rate"], "avoid": p["avoid_rule"]}
            for p in patterns[:limit]
        ]

    async def get_sector_insights(sector=None):
        insights = sample_learnings.get("sector_insights", [])
        if sector:
            insights = [s for s in insights if sector.lower() in s.get("sector", "").lower()]
        return insights

    async def get_ticker_insights(ticker=None):
        insights = sample_learnings.get("ticker_insights", [])
        if ticker:
            insights = [t for t in insights if t.get("ticker", "").upper() == ticker.upper()]
        return insights

    mock.get_swing_watchlist = get_swing_watchlist
    mock.get_longterm_watchlist = get_longterm_watchlist
    mock.get_portfolio_holdings = get_portfolio_holdings
    mock.get_cash_balance = get_cash_balance
    mock.get_recent_trades = get_recent_trades
    mock.get_active_goal = get_active_goal
    mock.get_learnings_summary = get_learnings_summary
    mock.get_winning_patterns = get_winning_patterns
    mock.get_losing_patterns = get_losing_patterns
    mock.get_sector_insights = get_sector_insights
    mock.get_ticker_insights = get_ticker_insights

    return mock


@pytest.fixture
def sample_trades() -> list[dict]:
    """Sample closed trades for metrics testing."""
    return [
        {
            "ticker": "TCB",
            "entry_date": "2026-01-10",
            "entry_total": 10000000,
            "exit_total": 11500000,
            "pl_gross": 1500000,
            "pl_net": 1465000,
            "pl_pct": 15.0,
        },
        {
            "ticker": "FPT",
            "entry_date": "2026-01-15",
            "entry_total": 15000000,
            "exit_total": 14000000,
            "pl_gross": -1000000,
            "pl_net": -1045000,
            "pl_pct": -6.67,
        },
        {
            "ticker": "VHM",
            "entry_date": "2026-01-20",
            "entry_total": 12000000,
            "exit_total": 13200000,
            "pl_gross": 1200000,
            "pl_net": 1160400,
            "pl_pct": 10.0,
        },
    ]


@pytest.fixture(autouse=False)
def mock_trading_config():
    """Pre-populate trading config cache with defaults — no DB needed.

    Use this fixture in tests that call code relying on get_trading_config().
    Without it, get_trading_config() raises RuntimeError (not initialized).
    """
    import shared.trading_config as tc_module
    from shared.trading_config import TradingConfig, clear_trading_config_cache

    clear_trading_config_cache()
    tc_module._config = TradingConfig()  # seed with all defaults
    yield tc_module._config
    clear_trading_config_cache()
