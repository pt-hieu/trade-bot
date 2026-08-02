"""Tests for alert_registrar deterministic registration — picks + trailing stops."""

from __future__ import annotations

import logging
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


def _atr_trail_pick(ticker: str = "FPT") -> dict:
    return {
        "ticker": ticker,
        "action": "BUY",
        "entry": 30000,
        "stop": 28500,
        "target": None,
        "risk_reward": None,
        "strategy": "TREND_FOLLOW",
        "exit_family": "ATR_TRAIL",
    }


def _fixed_target_pick(ticker: str = "TPB") -> dict:
    return {
        "ticker": ticker,
        "action": "BUY",
        "entry": 30000,
        "stop": 29400,
        "target": 42000,
        "risk_reward": 4.0,
        "strategy": "BOUNCE",
        "exit_family": "FIXED_TARGET",
    }


@pytest.mark.asyncio
async def test_register_picks_atr_trail_alert_has_null_target():
    """ATR_TRAIL pick produces alert with target_price=None and no exception."""
    from agents.alert_registrar.deterministic import register_picks_as_alerts

    captured: list[dict] = []

    async def fake_register(alert: dict) -> int:
        captured.append(alert)
        return 1

    with patch(
        "agents.alert_registrar.deterministic.db_register_alert",
        new=AsyncMock(side_effect=fake_register),
    ):
        count = await register_picks_as_alerts(
            pre_computed_picks=[_atr_trail_pick()],
            source="picks",
            scan_date=date(2026, 5, 5),
            current_prices={"FPT": 31000.0},
        )

    assert count == 1
    assert len(captured) == 1
    alert = captured[0]
    assert alert["target_price"] is None
    assert alert["entry_price"] == 30000
    assert alert["stop_price"] == 28500
    assert "ATR_TRAIL" in alert["rationale"]


@pytest.mark.asyncio
async def test_register_picks_fixed_target_alert_unchanged():
    """FIXED_TARGET pick still produces integer target_price."""
    from agents.alert_registrar.deterministic import register_picks_as_alerts

    captured: list[dict] = []

    async def fake_register(alert: dict) -> int:
        captured.append(alert)
        return 1

    with patch(
        "agents.alert_registrar.deterministic.db_register_alert",
        new=AsyncMock(side_effect=fake_register),
    ):
        count = await register_picks_as_alerts(
            pre_computed_picks=[_fixed_target_pick()],
            source="picks",
            scan_date=date(2026, 5, 5),
            current_prices={"TPB": 30200.0},
        )

    assert count == 1
    assert captured[0]["target_price"] == 42000
    assert "R:R 4.0" in captured[0]["rationale"]


@pytest.mark.asyncio
async def test_register_picks_skips_none_entry_and_continues(caplog):
    """Pick with None entry is skipped; later picks still register."""
    from agents.alert_registrar.deterministic import register_picks_as_alerts

    bad = {**_fixed_target_pick("BAD"), "entry": None}
    good = _fixed_target_pick("GOOD")

    captured: list[dict] = []

    async def fake_register(alert: dict) -> int:
        captured.append(alert)
        return 1

    with (
        patch(
            "agents.alert_registrar.deterministic.db_register_alert",
            new=AsyncMock(side_effect=fake_register),
        ),
        caplog.at_level(logging.WARNING),
    ):
        count = await register_picks_as_alerts(
            pre_computed_picks=[bad, good],
            source="picks",
            scan_date=date(2026, 5, 5),
            current_prices={"GOOD": 30200.0},
        )

    assert count == 1
    assert captured[0]["ticker"] == "GOOD"
    assert any("skipped" in record.message.lower() for record in caplog.records)


@pytest.mark.asyncio
async def test_register_picks_isolated_per_row_on_db_failure():
    """db_register_alert raising on row 2 leaves rows 1 + 3 registered."""
    from agents.alert_registrar.deterministic import register_picks_as_alerts

    picks = [_fixed_target_pick("A"), _fixed_target_pick("B"), _fixed_target_pick("C")]
    calls: list[str] = []

    async def fake_register(alert: dict) -> int:
        calls.append(alert["ticker"])
        if alert["ticker"] == "B":
            raise RuntimeError("db blip")
        return len(calls)

    with patch(
        "agents.alert_registrar.deterministic.db_register_alert",
        new=AsyncMock(side_effect=fake_register),
    ):
        count = await register_picks_as_alerts(
            pre_computed_picks=picks,
            source="picks",
            scan_date=date(2026, 5, 5),
            current_prices={"A": 30200.0, "B": 30200.0, "C": 30200.0},
        )

    assert count == 2
    assert calls == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_holding_breakeven_floor_fires_with_no_table_row(mock_trading_config):
    """SWI-363: an underwater SWING holding with a breakeven_stop but NO
    trailing_stops row still gets a breakeven-floor alert via the holdings
    second pass (the catastrophic-floor coverage the fix exists to close)."""
    from agents.alert_registrar.deterministic import register_trailing_stop_alerts

    class _Snapshot:
        settled_by_ticker = {"ACV": True}
        earliest_entry_by_ticker = {}

    holdings = [
        {
            "ticker": "ACV",
            "avg_cost": 50000,
            "current_price_vnd": 45000,  # underwater
            "plan_type": "SWING",
            "breakeven_stop": 44910,
            "ticker_weight_pct": 5.0,
        }
    ]
    captured: list[dict] = []

    async def fake_register(alert: dict) -> int:
        captured.append(alert)
        return 1

    with (
        patch(
            "agents.alert_registrar.deterministic.fetch_all",
            new=AsyncMock(return_value=[]),  # no trailing_stops row
        ),
        patch(
            "agents.alert_registrar.deterministic.load_open_trades_snapshot",
            new=AsyncMock(return_value=_Snapshot()),
        ),
        patch("agents.alert_registrar.deterministic.is_sellable", return_value=True),
        patch(
            "agents.alert_registrar.deterministic.db_register_alert",
            new=AsyncMock(side_effect=fake_register),
        ),
    ):
        count = await register_trailing_stop_alerts(
            scan_date=date(2026, 5, 14),
            current_prices={"ACV": 45000.0},
            holdings=holdings,
        )

    assert count == 1
    assert captured[0]["stop_price"] == 44910
    assert "breakeven floor" in captured[0]["rationale"].lower()


@pytest.mark.asyncio
async def test_holding_floor_skips_non_swing_and_no_holdings(mock_trading_config):
    """SWI-363: LONGTERM holdings and the no-holdings case register nothing
    via the second pass."""
    from agents.alert_registrar.deterministic import register_trailing_stop_alerts

    class _Snapshot:
        settled_by_ticker = {"VHM": True}
        earliest_entry_by_ticker = {}

    longterm = [
        {
            "ticker": "VHM",
            "avg_cost": 50000,
            "current_price_vnd": 45000,
            "plan_type": "LONGTERM",
            "breakeven_stop": 44910,
            "ticker_weight_pct": 5.0,
        }
    ]
    with (
        patch("agents.alert_registrar.deterministic.fetch_all", new=AsyncMock(return_value=[])),
        patch(
            "agents.alert_registrar.deterministic.load_open_trades_snapshot",
            new=AsyncMock(return_value=_Snapshot()),
        ),
        patch("agents.alert_registrar.deterministic.is_sellable", return_value=True),
        patch(
            "agents.alert_registrar.deterministic.db_register_alert",
            new=AsyncMock(return_value=1),
        ),
    ):
        count = await register_trailing_stop_alerts(
            scan_date=date(2026, 5, 14),
            current_prices={"VHM": 45000.0},
            holdings=longterm,
        )
    assert count == 0  # LONGTERM is not a SWING breakeven-floor candidate


@pytest.mark.asyncio
async def test_register_trailing_stop_isolated_per_row():
    """Per-row try/except — one bad row does not abort the others."""
    from agents.alert_registrar.deterministic import register_trailing_stop_alerts

    rows = [
        {"ticker": "A", "stop_level": 28000, "stop_type": "catastrophic", "updated_at": None},
        {"ticker": "B", "stop_level": 28000, "stop_type": "catastrophic", "updated_at": None},
        {"ticker": "C", "stop_level": 28000, "stop_type": "catastrophic", "updated_at": None},
    ]

    class _Snapshot:
        settled_by_ticker = {"A": True, "B": True, "C": True}
        earliest_entry_by_ticker = {}

    calls: list[str] = []

    async def fake_register(alert: dict) -> int:
        calls.append(alert["ticker"])
        if alert["ticker"] == "B":
            raise RuntimeError("db blip")
        return len(calls)

    with (
        patch(
            "agents.alert_registrar.deterministic.fetch_all",
            new=AsyncMock(return_value=rows),
        ),
        patch(
            "agents.alert_registrar.deterministic.load_open_trades_snapshot",
            new=AsyncMock(return_value=_Snapshot()),
        ),
        patch(
            "agents.alert_registrar.deterministic.is_sellable",
            return_value=True,
        ),
        patch(
            "agents.alert_registrar.deterministic.db_register_alert",
            new=AsyncMock(side_effect=fake_register),
        ),
    ):
        count = await register_trailing_stop_alerts(
            scan_date=date(2026, 5, 5),
            current_prices={"A": 30000.0, "B": 30000.0, "C": 30000.0},
        )

    assert count == 2
    assert calls == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_breakeven_floor_alert_fires_when_above_stop():
    """SWI-157: bounced underwater SWING (current > breakeven_floor) registers
    a single trailing_stop alert with priority=high and stop_type breakeven_floor."""
    from agents.alert_registrar.deterministic import register_trailing_stop_alerts

    rows = [
        {
            "ticker": "ACV",
            "stop_level": 44910,
            "stop_type": "breakeven_floor",
            "updated_at": None,
        },
    ]

    class _Snapshot:
        settled_by_ticker = {"ACV": True}
        earliest_entry_by_ticker = {}

    captured: list[dict] = []

    async def fake_register(alert: dict) -> int:
        captured.append(alert)
        return 1

    with (
        patch(
            "agents.alert_registrar.deterministic.fetch_all",
            new=AsyncMock(return_value=rows),
        ),
        patch(
            "agents.alert_registrar.deterministic.load_open_trades_snapshot",
            new=AsyncMock(return_value=_Snapshot()),
        ),
        patch(
            "agents.alert_registrar.deterministic.is_sellable",
            return_value=True,
        ),
        patch(
            "agents.alert_registrar.deterministic.db_register_alert",
            new=AsyncMock(side_effect=fake_register),
        ),
    ):
        count = await register_trailing_stop_alerts(
            scan_date=date(2026, 5, 14),
            current_prices={"ACV": 45200.0},  # bounced above breakeven_floor
        )

    assert count == 1
    alert = captured[0]
    assert alert["source"] == "trailing_stop"
    assert alert["stop_price"] == 44910
    assert alert["priority"] == "high"
    assert "breakeven_floor" in alert["rationale"]


@pytest.mark.asyncio
async def test_breakeven_floor_alert_skips_when_already_below():
    """SWI-157: when current is already below the breakeven_floor (e.g. ACV
    today at 44,500 < 44,910), the existing `stop_level >= current` guard
    skips registration. Acceptable: alerting after the bell is noise; the
    next bounce-and-break is when the alert should fire."""
    from agents.alert_registrar.deterministic import register_trailing_stop_alerts

    rows = [
        {
            "ticker": "ACV",
            "stop_level": 44910,
            "stop_type": "breakeven_floor",
            "updated_at": None,
        },
    ]

    class _Snapshot:
        settled_by_ticker = {"ACV": True}
        earliest_entry_by_ticker = {}

    async def fake_register(alert: dict) -> int:  # pragma: no cover - should not fire
        raise AssertionError("should not register when current < stop_level")

    with (
        patch(
            "agents.alert_registrar.deterministic.fetch_all",
            new=AsyncMock(return_value=rows),
        ),
        patch(
            "agents.alert_registrar.deterministic.load_open_trades_snapshot",
            new=AsyncMock(return_value=_Snapshot()),
        ),
        patch(
            "agents.alert_registrar.deterministic.is_sellable",
            return_value=True,
        ),
        patch(
            "agents.alert_registrar.deterministic.db_register_alert",
            new=AsyncMock(side_effect=fake_register),
        ),
    ):
        count = await register_trailing_stop_alerts(
            scan_date=date(2026, 5, 14),
            current_prices={"ACV": 44500.0},  # underwater, already below floor
        )

    assert count == 0


@pytest.mark.asyncio
async def test_breakeven_floor_bypasses_7pct_band():
    """SWI-157: breakeven_floor is the cost-basis catastrophic equivalent —
    must register even when the floor is more than 7% (vn_max_daily_move)
    below current price, matching the existing `catastrophic` exemption."""
    from agents.alert_registrar.deterministic import register_trailing_stop_alerts

    rows = [
        {
            "ticker": "ACV",
            "stop_level": 44910,
            "stop_type": "breakeven_floor",
            "updated_at": None,
        },
    ]

    class _Snapshot:
        settled_by_ticker = {"ACV": True}
        earliest_entry_by_ticker = {}

    captured: list[dict] = []

    async def fake_register(alert: dict) -> int:
        captured.append(alert)
        return 1

    with (
        patch(
            "agents.alert_registrar.deterministic.fetch_all",
            new=AsyncMock(return_value=rows),
        ),
        patch(
            "agents.alert_registrar.deterministic.load_open_trades_snapshot",
            new=AsyncMock(return_value=_Snapshot()),
        ),
        patch(
            "agents.alert_registrar.deterministic.is_sellable",
            return_value=True,
        ),
        patch(
            "agents.alert_registrar.deterministic.db_register_alert",
            new=AsyncMock(side_effect=fake_register),
        ),
    ):
        count = await register_trailing_stop_alerts(
            scan_date=date(2026, 5, 14),
            current_prices={"ACV": 60000.0},  # 25%+ above floor — would normally trip 7% band
        )

    assert count == 1
    assert captured[0]["stop_price"] == 44910
