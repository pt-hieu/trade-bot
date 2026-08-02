"""Tests for T+2 settlement rules.

Pins the T+2 trading-day math and the settled-shares query so the
registration-time and evaluation-time guards don't silently regress.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from shared.rules.settlement import (
    get_settled_shares_by_ticker,
    is_sellable,
    load_open_trades_snapshot,
    settlement_date,
    trading_days_after,
    trading_days_between,
)


class TestTradingDaysAfter:
    """Intra-week + holiday-spanning forward walk."""

    def test_n_equals_2_intra_week(self):
        # Mon 2026-05-11 -> Tue (TD1) -> Wed (TD2): Wed 2026-05-13.
        assert trading_days_after(date(2026, 5, 11), 2) == date(2026, 5, 13)

    def test_n_equals_2_across_weekend(self):
        # Fri 2026-05-08 -> Sat/Sun skipped -> Mon (TD1) -> Tue (TD2).
        assert trading_days_after(date(2026, 5, 8), 2) == date(2026, 5, 12)

    def test_n_equals_0_returns_base(self):
        assert trading_days_after(date(2026, 5, 11), 0) == date(2026, 5, 11)


class TestTradingDaysBetween:
    """Inverse of trading_days_after — count trading days in (start, end]."""

    def test_same_day_returns_zero(self):
        assert trading_days_between(date(2026, 5, 11), date(2026, 5, 11)) == 0

    def test_end_before_start_returns_zero(self):
        assert trading_days_between(date(2026, 5, 13), date(2026, 5, 11)) == 0

    def test_intra_week_counts(self):
        # Mon 2026-05-11 -> Wed 2026-05-13 = Tue + Wed = 2 trading days.
        assert trading_days_between(date(2026, 5, 11), date(2026, 5, 13)) == 2

    def test_skips_weekend(self):
        # Fri 2026-05-08 -> Tue 2026-05-12 = Mon + Tue = 2 (Sat/Sun skipped).
        assert trading_days_between(date(2026, 5, 8), date(2026, 5, 12)) == 2


class TestSettlementDate:
    """T+2 settlement on real VN calendar."""

    def test_friday_skips_weekend(self):
        # Fri 2026-05-08 -> Tue 2026-05-12 (Sat/Sun skipped, no holidays).
        assert settlement_date(date(2026, 5, 8)) == date(2026, 5, 12)

    def test_crosses_reunification_labor_weekend(self):
        # Wed 2026-04-29 -> skip Thu Reunification (Apr 30), Fri Labor (May 1),
        # Sat/Sun -> Mon (TD1) -> Tue (TD2) = Tue 2026-05-05.
        assert settlement_date(date(2026, 4, 29)) == date(2026, 5, 5)


class TestIsSellable:
    """Binary sellable guard."""

    def test_ticker_with_settled_shares(self):
        assert is_sellable("ACV", {"ACV": 100}) is True

    def test_ticker_not_in_map(self):
        assert is_sellable("ACV", {"FPT": 100}) is False

    def test_ticker_zero_shares(self):
        assert is_sellable("ACV", {"ACV": 0}) is False

    def test_ticker_none_value(self):
        # None-safe dict access per CLAUDE.md `get(k) or default`.
        assert is_sellable("ACV", {"ACV": None}) is False  # type: ignore[dict-item]


class TestLoadOpenTradesSnapshot:
    """Snapshot returns both settled-shares and earliest-entry dicts from
    a single DB scan of OPEN trades.
    """

    @pytest.mark.asyncio
    async def test_partitions_settled_vs_unsettled(self):
        # as_of = Wed 2026-05-13. Entry Fri 2026-05-08 settles Tue 2026-05-12.
        # Entry Tue 2026-05-12 settles Thu 2026-05-14. Entry today (5-13)
        # settles Fri 2026-05-15. Only the T-3 lot contributes to settled.
        as_of = date(2026, 5, 13)
        rows = [
            {"ticker": "ACV", "entry_date": date(2026, 5, 8), "shares": 100},  # settled
            {"ticker": "ACV", "entry_date": date(2026, 5, 12), "shares": 50},  # unsettled
            {"ticker": "FPT", "entry_date": date(2026, 5, 13), "shares": 200},  # unsettled
        ]
        with patch(
            "shared.rules.settlement.fetch_all",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = rows
            snapshot = await load_open_trades_snapshot(as_of)
        assert snapshot.settled_by_ticker == {"ACV": 100}
        assert snapshot.earliest_entry_by_ticker == {
            "ACV": date(2026, 5, 8),
            "FPT": date(2026, 5, 13),
        }

    @pytest.mark.asyncio
    async def test_multiple_lots_sum_and_keep_min_entry(self):
        as_of = date(2026, 5, 13)
        rows = [
            {"ticker": "ACV", "entry_date": date(2026, 5, 6), "shares": 200},
            {"ticker": "ACV", "entry_date": date(2026, 5, 1), "shares": 100},
        ]
        with patch(
            "shared.rules.settlement.fetch_all",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = rows
            snapshot = await load_open_trades_snapshot(as_of)
        assert snapshot.settled_by_ticker == {"ACV": 300}
        assert snapshot.earliest_entry_by_ticker == {"ACV": date(2026, 5, 1)}

    @pytest.mark.asyncio
    async def test_null_or_zero_shares_drop_from_settled_but_earliest_still_records(self):
        as_of = date(2026, 5, 13)
        rows = [
            {"ticker": "ACV", "entry_date": date(2026, 5, 1), "shares": None},
            {"ticker": "ACV", "entry_date": date(2026, 5, 1), "shares": 0},
        ]
        with patch(
            "shared.rules.settlement.fetch_all",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = rows
            snapshot = await load_open_trades_snapshot(as_of)
        assert snapshot.settled_by_ticker == {}
        assert snapshot.earliest_entry_by_ticker == {"ACV": date(2026, 5, 1)}

    @pytest.mark.asyncio
    async def test_get_settled_shares_by_ticker_wrapper(self):
        as_of = date(2026, 5, 13)
        rows = [{"ticker": "ACV", "entry_date": date(2026, 5, 1), "shares": 100}]
        with patch(
            "shared.rules.settlement.fetch_all",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = rows
            result = await get_settled_shares_by_ticker(as_of)
        assert result == {"ACV": 100}


class TestClosedTradeOrphanStop:
    """Regression: trailing_stops row with no matching OPEN trade must log
    the 'no OPEN trade' branch, not None-interpolate settlement_date.
    """

    @pytest.mark.asyncio
    async def test_skip_log_branch_when_no_open_row(self, caplog):
        import logging

        from agents.alert_registrar.deterministic import register_trailing_stop_alerts

        caplog.set_level(logging.INFO, logger="agents.alert_registrar.deterministic")

        stop_rows = [
            {
                "ticker": "ACV",
                "stop_level": 50000,
                "stop_type": "trailing",
                "updated_at": date(2026, 5, 13),
            }
        ]

        async def fake_fetch_all(query, *_args):
            if "FROM trailing_stops" in query:
                return stop_rows
            return []  # no OPEN trades

        with (
            patch(
                "agents.alert_registrar.deterministic.fetch_all",
                new=fake_fetch_all,
            ),
            patch(
                "shared.rules.settlement.fetch_all",
                new=fake_fetch_all,
            ),
            patch(
                "agents.alert_registrar.deterministic.db_register_alert",
                new_callable=AsyncMock,
            ) as mock_register,
        ):
            count = await register_trailing_stop_alerts(
                scan_date=date(2026, 5, 13),
                current_prices={"ACV": 60000},
            )

        assert count == 0
        mock_register.assert_not_awaited()
        assert any(
            "no OPEN trade" in rec.getMessage() and "ACV" in rec.getMessage()
            for rec in caplog.records
        )


class TestUnsettledSkipLog:
    """Regression: unsettled ticker logs 'unsettled' branch with settle date."""

    @pytest.mark.asyncio
    async def test_skip_log_branch_when_unsettled(self, caplog):
        import logging

        from agents.alert_registrar.deterministic import register_trailing_stop_alerts

        caplog.set_level(logging.INFO, logger="agents.alert_registrar.deterministic")

        stop_rows = [
            {
                "ticker": "ACV",
                "stop_level": 50000,
                "stop_type": "trailing",
                "updated_at": date(2026, 5, 13),
            }
        ]
        # OPEN trade entered today -> unsettled on today.
        open_trade_rows = [{"ticker": "ACV", "entry_date": date(2026, 5, 13), "shares": 100}]

        async def fake_fetch_all(query, *_args):
            if "FROM trailing_stops" in query:
                return stop_rows
            return open_trade_rows

        with (
            patch(
                "agents.alert_registrar.deterministic.fetch_all",
                new=fake_fetch_all,
            ),
            patch(
                "shared.rules.settlement.fetch_all",
                new=fake_fetch_all,
            ),
            patch(
                "agents.alert_registrar.deterministic.db_register_alert",
                new_callable=AsyncMock,
            ) as mock_register,
        ):
            count = await register_trailing_stop_alerts(
                scan_date=date(2026, 5, 13),
                current_prices={"ACV": 60000},
            )

        assert count == 0
        mock_register.assert_not_awaited()
        assert any(
            "unsettled" in rec.getMessage() and "ACV" in rec.getMessage() for rec in caplog.records
        )
