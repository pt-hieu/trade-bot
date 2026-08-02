"""
VN stock market holiday calendar.

Hardcoded holidays — HOSE publishes the next year's calendar each December.
Update VN_MARKET_HOLIDAYS dict annually (~5 min task).

CLI usage:
    python -m shared.market_calendar              # Check today
    python -m shared.market_calendar 2026-02-17   # Check specific date
    python -m shared.market_calendar --week        # Check if current week has trading days
"""

import sys
from datetime import date, datetime, timedelta

from shared.config import VIETNAM_TZ


def _today_vietnam() -> date:
    """Return today's date in Vietnam timezone (UTC+7)."""
    return datetime.now(VIETNAM_TZ).date()


# HOSE market holidays by year
# Source: https://www.calendarlabs.com/hnx-market-holidays-2026/
VN_MARKET_HOLIDAYS: dict[int, set[date]] = {
    2026: {
        date(2026, 1, 1),  # New Year
        date(2026, 2, 16),  # Tet
        date(2026, 2, 17),
        date(2026, 2, 18),
        date(2026, 2, 19),
        date(2026, 2, 20),
        date(2026, 4, 27),  # Hung Kings' Day
        date(2026, 4, 30),  # Reunification Day
        date(2026, 5, 1),  # Labor Day
        date(2026, 8, 31),  # Independence Day (observed)
        date(2026, 9, 1),
        date(2026, 9, 2),
    },
}


def is_trading_day(d: date | None = None) -> bool:
    """Check if a date is a VN stock market trading day.

    Returns False for weekends and known market holidays.
    Returns True for weekdays without known holidays (including years
    without holiday data — conservative default).
    """
    d = d or _today_vietnam()
    if d.weekday() >= 5:
        return False
    holidays = VN_MARKET_HOLIDAYS.get(d.year, set())
    return d not in holidays


def last_trading_day(d: date | None = None, max_lookback: int = 7) -> date:
    """Return the most recent trading day on or before `d`.

    Walks backward from `d` (default: yesterday in Vietnam TZ) skipping
    weekends and holidays. Useful when fetching market data outside
    trading hours — e.g., Monday 3 AM should get Friday's data.

    Raises ValueError if no trading day found within max_lookback days.
    """
    if d is None:
        d = _today_vietnam() - timedelta(days=1)
    for i in range(max_lookback):
        candidate = d - timedelta(days=i)
        if is_trading_day(candidate):
            return candidate
    msg = f"No trading day found within {max_lookback} days of {d}"
    raise ValueError(msg)


def next_trading_day(d: date, max_lookahead: int = 14) -> date:
    """Return the first trading day on or after `d`.

    Walks forward from `d` skipping weekends and holidays. Useful for
    belief-horizon resolution where a calendar horizon may land on a
    weekend or holiday and we need the first trading day at-or-after.

    `max_lookahead=14` covers Tet (worst case ~9 calendar days closed).
    Raises ValueError if no trading day found within max_lookahead days.
    """
    for i in range(max_lookahead):
        candidate = d + timedelta(days=i)
        if is_trading_day(candidate):
            return candidate
    msg = f"No trading day found within {max_lookahead} days of {d}"
    raise ValueError(msg)


def next_n_trading_days(d: date, n: int) -> date:
    """Return the date that is `n` trading days strictly after `d`.

    Walks forward skipping weekends and VN holidays. Used by alert expiry
    where conditional WATCH alerts should age out after ~5 trading days.
    """
    if n <= 0:
        return d
    current = d
    counted = 0
    while counted < n:
        current = current + timedelta(days=1)
        if is_trading_day(current):
            counted += 1
    return current


def trading_days_between(start: date, end: date) -> int:
    """Count of VN trading days strictly after `start` and on/before `end`.

    - Endpoints: start exclusive, end inclusive.
    - Same-day (start == end): 0.
    - Negative range (start > end): raises ValueError (callers should compare
      timestamps before querying; silent zero-return masks ordering bugs).
    - Non-trading-day endpoints are NOT rounded — they simply contribute 0
      to the count when iterated.
    """
    if start > end:
        msg = f"start={start} after end={end}"
        raise ValueError(msg)
    d = start
    count = 0
    while d < end:
        d = d + timedelta(days=1)
        if is_trading_day(d):
            count += 1
    return count


def is_trading_week(d: date | None = None) -> bool:
    """Check if the Mon-Fri week containing `d` has any trading days."""
    d = d or _today_vietnam()
    monday = d - timedelta(days=d.weekday())
    return any(is_trading_day(monday + timedelta(days=i)) for i in range(5))


def is_next_trading_week(d: date | None = None) -> bool:
    """Check if the Mon-Fri week AFTER the one containing `d` has trading days.

    Used by weekly watchlist update (runs Saturday) to decide whether
    to prepare for next week.
    """
    d = d or _today_vietnam()
    monday = d - timedelta(days=d.weekday())
    next_monday = monday + timedelta(days=7)
    return any(is_trading_day(next_monday + timedelta(days=i)) for i in range(5))


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--next-week" in args:
        result = is_next_trading_week()
        print(f"NEXT_TRADING_WEEK={str(result).lower()}")
        sys.exit(0 if result else 1)

    if "--week" in args:
        result = is_trading_week()
        print(f"TRADING_WEEK={str(result).lower()}")
        sys.exit(0 if result else 1)

    if args and args[0] not in ("--week", "--next-week"):
        check_date = date.fromisoformat(args[0])
    else:
        check_date = _today_vietnam()

    result = is_trading_day(check_date)
    print(f"TRADING={str(result).lower()}")
    sys.exit(0 if result else 1)
