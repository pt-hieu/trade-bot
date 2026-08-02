"""Tests for insert_records.py — ticker validation and HOLD validation."""

import logging
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from shared.neon.insert_records import _is_valid_ticker, _normalize_trading_mode


def _make_db_mock(fetch_val_side_effect: list[object]) -> AsyncMock:
    """Build an AsyncMock with a working `db.transaction()` context manager.

    db.fetch_val (outside txn) and conn.fetchval (inside txn) drain from the
    same sequence — the transaction yields the mock itself.
    """
    db = AsyncMock()
    values = iter(fetch_val_side_effect)

    async def _drain(*_args, **_kwargs):
        return next(values)

    db.fetch_val = AsyncMock(side_effect=_drain)
    db.fetchval = AsyncMock(side_effect=_drain)
    db.execute = AsyncMock()
    db.execute_many = AsyncMock()
    db.executemany = AsyncMock()

    @asynccontextmanager
    async def _txn():
        yield db

    db.transaction = _txn  # type: ignore[method-assign]
    return db


# ============================================================================
# Ticker validation
# ============================================================================


class TestNormalizeTradingMode:
    @pytest.mark.parametrize(
        "mode,expected",
        [
            ("NORMAL", "NORMAL"),
            ("LOW_CASH", "LOW_CASH"),
            ("REALLOCATION", "REALLOCATION"),
            ("normal", "NORMAL"),
            ("low_cash", "LOW_CASH"),
            (None, None),
            ("", None),
            ("N/A", "NORMAL"),
            ("UNKNOWN", "NORMAL"),
            ("GARBAGE", "NORMAL"),
        ],
    )
    def test_normalize_trading_mode(self, mode, expected):
        assert _normalize_trading_mode(mode) == expected


class TestIsValidTicker:
    @pytest.mark.parametrize(
        "ticker,expected",
        [
            ("FPT", True),
            ("TCB", True),
            ("VHM", True),
            ("A32", True),
            ("HP", True),
            ("LOGISTICS", False),
            ("PLASTICS", False),
            ("", False),
            ("fpt", False),
            ("12AB", False),
            ("ABCDE", False),
        ],
    )
    def test_ticker_validation(self, ticker, expected):
        assert _is_valid_ticker(ticker) is expected


# ============================================================================
# HOLD validation for non-held tickers
# ============================================================================


class TestHoldValidation:
    """HOLD/EXIT/TRIM/ADD for tickers not in portfolio should be downgraded to WATCH."""

    @pytest.fixture
    def mock_db(self):
        # fetch values for non-empty rec path:
        #   1) INSERT RETURNING id=1
        #   2) eval_count=0 (no retro yet — early-return guard skipped)
        # The inside-txn COUNT is skipped when rows is non-empty.
        return _make_db_mock(fetch_val_side_effect=[1, 0])

    @pytest.fixture
    def mock_holdings(self):
        # list[HoldingData] shape (migration 2026-04-20).
        return [
            {"ticker": "FPT", "plan_type": "SWING", "shares": 100, "avg_cost_vnd": 90000},
            {"ticker": "VHM", "plan_type": "SWING", "shares": 50, "avg_cost_vnd": 95000},
        ]

    @pytest.mark.asyncio
    async def test_hold_for_held_ticker_stays_hold(self, mock_db, mock_holdings):
        recs = [{"ticker": "FPT", "action": "HOLD"}]
        scan = date(2026, 3, 6)

        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=mock_db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            result = await insert_morning_recommendations(scan, "NORMAL", "NORMAL", recs)

        assert result is True
        # Verify execute_many was called with HOLD action (not WATCH)
        assert mock_db.executemany.call_count == 1
        rows = mock_db.executemany.call_args[0][1]  # second positional arg = rows
        assert len(rows) == 1
        assert rows[0][2] == "HOLD"  # action is 3rd element (index 2) in row tuple

    @pytest.mark.asyncio
    async def test_hold_for_non_held_ticker_downgraded_to_watch(
        self, mock_db, mock_holdings, caplog
    ):
        recs = [{"ticker": "BSR", "action": "HOLD"}]
        scan = date(2026, 3, 6)

        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=mock_db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
            caplog.at_level(logging.WARNING),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            result = await insert_morning_recommendations(scan, "NORMAL", "NORMAL", recs)

        assert result is True
        # Non-held ticker HOLD downgrade now handled upstream by recommendation_validator
        # insert_records just inserts as-is
        assert mock_db.executemany.call_count == 1
        rows = mock_db.executemany.call_args[0][1]
        assert len(rows) == 1
        assert rows[0][2] == "HOLD"  # no downgrade at insert layer

    @pytest.mark.asyncio
    async def test_exit_for_held_ticker_stays_exit(self, mock_db, mock_holdings):
        recs = [{"ticker": "VHM", "action": "EXIT"}]
        scan = date(2026, 3, 6)

        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=mock_db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            result = await insert_morning_recommendations(scan, "NORMAL", "NORMAL", recs)

        assert result is True
        assert mock_db.executemany.call_count == 1
        rows = mock_db.executemany.call_args[0][1]
        assert len(rows) == 1
        assert rows[0][2] == "EXIT"

    @pytest.mark.asyncio
    async def test_exit_for_non_held_ticker_stays_exit(self, mock_db, mock_holdings):
        """EXIT for non-held ticker is no longer downgraded at insert layer."""
        recs = [{"ticker": "PLX", "action": "EXIT"}]
        scan = date(2026, 3, 6)

        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=mock_db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            result = await insert_morning_recommendations(scan, "NORMAL", "NORMAL", recs)

        assert result is True
        assert mock_db.executemany.call_count == 1
        rows = mock_db.executemany.call_args[0][1]
        assert len(rows) == 1
        assert rows[0][2] == "EXIT"  # no downgrade at insert layer

    @pytest.mark.asyncio
    async def test_buy_not_affected_by_hold_validation(self, mock_db, mock_holdings):
        """BUY for non-held ticker should NOT be downgraded."""
        recs = [
            {
                "ticker": "TCB",
                "action": "BUY",
                "entry_price": 35.0,
                "stop_price": 34.0,
                "target_price": 38.0,
            }
        ]
        scan = date(2026, 3, 6)

        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=mock_db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            result = await insert_morning_recommendations(scan, "NORMAL", "NORMAL", recs)

        assert result is True
        assert mock_db.executemany.call_count == 1
        rows = mock_db.executemany.call_args[0][1]
        assert len(rows) == 1
        assert rows[0][2] == "BUY"  # not downgraded

    @pytest.mark.asyncio
    async def test_morning_refuses_to_clobber_existing_recs_with_empty_payload(self, mock_holdings):
        """morning.py must not DELETE good rows when incoming payload is empty."""
        # fetch values: id=1, eval_count=0, existing_recs_in_db=12 (morning had data)
        db = _make_db_mock(fetch_val_side_effect=[1, 0, 12])
        scan = date(2026, 4, 19)
        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
            pytest.raises(RuntimeError, match="MORNING_EMPTY_RECS"),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            await insert_morning_recommendations(scan, "NORMAL", "NORMAL", [])

    @pytest.mark.asyncio
    async def test_morning_empty_recs_with_empty_db_is_silent(self, mock_holdings):
        """Legitimately empty day — DB has nothing, payload empty → no raise."""
        db = _make_db_mock(fetch_val_side_effect=[1, 0, 0])
        scan = date(2026, 4, 19)
        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            ok = await insert_morning_recommendations(scan, "NORMAL", "NORMAL", [])
        assert ok is True

    @pytest.mark.asyncio
    async def test_executemany_failure_propagates_exception(self, mock_holdings):
        """SWI-308: executemany failures must propagate (non-prod) rather than
        being swallowed. Postgres-level rollback of the parent daily_records
        UPSERT is verified at the DB level in
        tests/integration/test_check_constraints_round_trip.py — this unit
        test only asserts the exception travels out of the morning writer.
        """
        # fetch_val sequence: parent UPSERT id=42, eval_count=0
        db = _make_db_mock(fetch_val_side_effect=[42, 0])

        # Simulate a CHECK constraint violation on executemany
        async def _raise_check_violation(*_args, **_kwargs):
            raise ValueError("daily_recs_plan_shape_action_chk violated")

        db.executemany = AsyncMock(side_effect=_raise_check_violation)
        recs = [
            {
                "ticker": "FPT",
                "action": "WATCH",
                "plan_shape": "BREAKOUT",
                # No trigger_price → CHECK fires at DB
            }
        ]
        scan = date(2026, 5, 11)
        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            # SWI-NN: narrow_db_error re-raises non-connectivity errors.
            # The atomic transaction means daily_records rolls back too —
            # verified at the DB level by tests/integration/
            # test_check_constraints_round_trip.py.
            with pytest.raises(ValueError, match="daily_recs_plan_shape_action_chk"):
                await insert_morning_recommendations(scan, "NORMAL", "NORMAL", recs)

    @pytest.mark.asyncio
    async def test_last_good_morning_passes_strict(self, mock_db, mock_holdings, monkeypatch):
        """Strict-mode green-light: replay a representative last-good morning
        rec set under SWINGY_ENV=development. _build_rec_row must NOT raise —
        the producer-side coerce already eliminated invariant violations, so
        the boundary guard's strict assertion only fires on regressions.
        """
        monkeypatch.setenv("SWINGY_ENV", "development")
        recs = [
            {
                "ticker": "FPT",
                "action": "BUY",
                "entry_price": 130000,
                "stop_price": 125000,
                "target_price": 145000,
                "section": "TOP_PICKS",
                "source": "picks",
            },
            {
                "ticker": "VCB",
                "action": "WATCH",
                "section": "WHAT_TO_DO",
                "source": "sector_signals",
                "plan_shape": "BREAKOUT",
                "trigger_price": 90000,
                "stop_price": 87000,
                "target_price": 95000,
            },
            {
                "ticker": "VHM",
                "action": "WATCH",
                "section": "WHAT_TO_DO",
                "source": "sector_signals",
                # Producer correctly emits NONE because no trigger
                "plan_shape": "NONE",
            },
        ]
        scan = date(2026, 5, 11)
        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=mock_db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            result = await insert_morning_recommendations(scan, "NORMAL", "NORMAL", recs)
        assert result is True
        rows = mock_db.executemany.call_args[0][1]
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_invalid_ticker_skipped_entirely(self, mock_holdings, caplog):
        """Sector labels like LOGISTICS should be skipped — empty payload path."""
        # All recs filtered → rows is empty → COUNT runs inside txn (returns 0).
        db = _make_db_mock(fetch_val_side_effect=[1, 0, 0])
        recs = [{"ticker": "LOGISTICS", "action": "BUY"}]
        scan = date(2026, 3, 6)

        with (
            patch("shared.neon.insert_records.morning.get_db", return_value=db),
            patch("shared.neon.portfolio.get_portfolio_holdings", return_value=mock_holdings),
            caplog.at_level(logging.WARNING),
        ):
            from shared.neon.insert_records import insert_morning_recommendations

            result = await insert_morning_recommendations(scan, "NORMAL", "NORMAL", recs)

        assert result is True
        # No executemany should fire — rows is empty after filtering.
        assert db.executemany.call_count == 0
        assert "Skipping invalid rec" in caplog.text
