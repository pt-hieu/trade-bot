"""Unit tests for `shared.market_calendar.trading_days_between`."""

from __future__ import annotations

from datetime import date

import pytest

from shared.market_calendar import trading_days_between


def test_same_day_returns_zero() -> None:
    d = date(2026, 4, 24)
    assert trading_days_between(d, d) == 0


def test_negative_range_raises() -> None:
    with pytest.raises(ValueError, match="after end"):
        trading_days_between(date(2026, 5, 1), date(2026, 4, 24))


def test_ship_2026_04_24_to_2026_05_07_inclusive_counts_six() -> None:
    # End-inclusive contract: Apr 28, 29, May 4, 5, 6, 7 → 6.
    # Apr 25-26 weekend; Apr 27 Hung Kings; Apr 30 Reunification;
    # May 1 Labour; May 2-3 weekend.
    assert trading_days_between(date(2026, 4, 24), date(2026, 5, 7)) == 6


def test_ship_2026_04_24_plus_5_trading_days_lands_on_2026_05_06() -> None:
    # Anchors the SWI-61/17 verification window: 5 clean trading days
    # post-ship 2026-04-24 = Apr 28, 29, May 4, 5, 6 (earliest eligible
    # auto-promote on 2026-05-07).
    assert trading_days_between(date(2026, 4, 24), date(2026, 5, 6)) == 5


def test_weekend_endpoints_contribute_zero() -> None:
    # Sat → Sun: zero trading days between.
    assert trading_days_between(date(2026, 4, 25), date(2026, 4, 26)) == 0


def test_holiday_endpoints_contribute_zero() -> None:
    # Apr 30 Reunification → May 1 Labour Day: both holidays, no trading day in between.
    assert trading_days_between(date(2026, 4, 30), date(2026, 5, 1)) == 0
