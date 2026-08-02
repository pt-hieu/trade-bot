"""Deterministic post-LLM parser for the free-text ``CatalystAddition.expected``.

Bridges the LLM-emitted narrative ("Q3 2026", "ongoing", "Effective immediately")
to the DB ``catalysts.expected_date`` column + the new
``catalysts.expected_status`` enum.

Status enum:
  - ``dated``       → concrete ISO/EU/US-style date (writes ``expected_date``)
  - ``quarter``     → ``Q1-4 YYYY`` (writes the last day of the quarter)
  - ``month``       → ``<MonthName> YYYY`` (writes the last day of the month)
  - ``relative``    → "next 30 days", "in 2 weeks" (writes today + delta)
  - ``ongoing``     → narrative without temporal token ("ongoing", "tbd",
                      "in due course") — ``expected_date`` stays NULL but the
                      catalyst is intentionally dateless. Lifecycle expiry
                      runs through the phases-or-confidence path.
  - ``unparseable`` → temporal token present BUT parsing failed. Surfaces a
                      tighter 14d staleness in
                      :func:`refresh_catalyst_lifecycle` so genuine
                      parser-failures don't escape the imminent gate forever.

Bias rule (round-2 review fix): plain narrative without any temporal token
is biased to ``ongoing``. Only flag ``unparseable`` when a temporal token
(year, month, ``Q1-4``, ``days/weeks/months``) is present AND parsing fails
— prevents flooding the lifecycle scorer with false ``unparseable`` rows.

Pure deterministic Python. No async, no DB, no LLM.
"""

from __future__ import annotations

import calendar
import logging
import re
from datetime import date, timedelta
from typing import Literal

logger = logging.getLogger(__name__)

ExpectedStatus = Literal["dated", "quarter", "month", "relative", "ongoing", "unparseable"]


# Phrases that map directly to ``ongoing`` regardless of any other token.
# Run TRIM + lowercase + strip non-alphanumeric before membership check so
# trailing punctuation and unicode quirks don't break the lookup.
_ONGOING_PHRASES: frozenset[str] = frozenset(
    {
        "ongoing",
        "effective immediately",
        "continuous",
        "indefinite",
        "tbd",
        "until further notice",
        "in due course",
        "n a",  # "n/a" after non-alnum strip
        "none",
        "",
    }
)

# Any of these tokens make a parse-failure ``unparseable`` rather than
# ``ongoing``. Without one of these, the string is considered dateless
# narrative and biased to ``ongoing`` (round-2 review).
_TEMPORAL_TOKEN_RE = re.compile(
    r"\b("
    r"20\d{2}"
    r"|q[1-4]"
    r"|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r"|days?|weeks?|months?|next\s+\d+|in\s+\d+"
    r")\b",
    re.IGNORECASE,
)

# ISO date: 2026-08-15 (canonical) or 2026/08/15.
_ISO_DATE_RE = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b")

# EU date: 15/08/2026 or 15-08-2026 (day first, 4-digit year).
_EU_DATE_RE = re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b")

# Quarter: Q3 2026 / q3 2026 / 2026 Q3 / Q3-2026.
_QUARTER_RE = re.compile(r"\b(?:q([1-4])\s*[-/]?\s*(\d{4})|(\d{4})\s+q([1-4]))\b", re.IGNORECASE)

# Month label: "August 2026" / "Aug 2026" / "Aug. 2026".
_MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH_LOOKUP: dict[str, int] = {}
for _idx, _name in enumerate(_MONTH_NAMES, start=1):
    _MONTH_LOOKUP[_name] = _idx
    _MONTH_LOOKUP[_name[:3]] = _idx  # 3-letter abbreviation
_MONTH_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\.?\s+(\d{4})\b",
    re.IGNORECASE,
)

# Relative window: "next 30 days", "in 2 weeks", "in 3 months".
_RELATIVE_RE = re.compile(
    r"\b(?:next|in)\s+(\d{1,3})\s+(day|days|week|weeks|month|months)\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    """Lowercase, strip non-alnum (preserving spaces) for phrase lookup."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


def _last_day_of_month(year: int, month: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last)


def _last_day_of_quarter(year: int, quarter: int) -> date:
    end_month = quarter * 3
    return _last_day_of_month(year, end_month)


def parse_expected(
    expected: str | None,
    today: date,
) -> tuple[date | None, ExpectedStatus]:
    """Parse the agent-emitted ``expected`` text into ``(date, status)``.

    The first matching shape wins:
      1. ``ongoing`` phrase set (with TRIM + non-alnum strip).
      2. ISO ``YYYY-MM-DD`` or ``YYYY/MM/DD``.
      3. Quarter ``Qn YYYY`` / ``YYYY Qn``.
      4. Month ``<MonthName> YYYY``.
      5. EU ``DD/MM/YYYY`` or ``DD-MM-YYYY``.
      6. Relative ``next N days/weeks/months`` / ``in N …``.
      7. Bias to ``ongoing`` when no temporal token present, else ``unparseable``.

    Args:
        expected: Free-text emitted by the catalyst-discovery LLM. Empty /
            None / whitespace-only inputs return ``(None, "ongoing")`` —
            the caller's catalyst already implies a phased lifecycle.
        today: Reference date for relative parses (``next 30 days`` → today + 30).

    Returns:
        ``(date_or_None, status)``. ``date`` is None when the catalyst is
        intentionally dateless or the parse failed.
    """
    if not expected:
        return None, "ongoing"

    raw = str(expected).strip()
    normalized = _normalize(raw)

    # Step 1 — explicit ongoing phrases.
    if normalized in _ONGOING_PHRASES:
        return None, "ongoing"

    # Step 2 — ISO date.
    iso_match = _ISO_DATE_RE.search(raw)
    if iso_match:
        try:
            year = int(iso_match.group(1))
            month = int(iso_match.group(2))
            day = int(iso_match.group(3))
            return date(year, month, day), "dated"
        except ValueError:
            pass  # fall through to next shape

    # Step 3 — quarter (preferred over month so "Q3 2026" doesn't accidentally
    # match a month rule on the year alone).
    quarter_match = _QUARTER_RE.search(raw)
    if quarter_match:
        if quarter_match.group(1) and quarter_match.group(2):
            quarter = int(quarter_match.group(1))
            year = int(quarter_match.group(2))
        else:
            year = int(quarter_match.group(3))
            quarter = int(quarter_match.group(4))
        try:
            return _last_day_of_quarter(year, quarter), "quarter"
        except ValueError:
            pass

    # Step 4 — month label.
    month_match = _MONTH_RE.search(raw)
    if month_match:
        month_name = month_match.group(1).lower()
        month = _MONTH_LOOKUP.get(month_name) or _MONTH_LOOKUP.get(month_name[:3])
        if month is not None:
            year = int(month_match.group(2))
            try:
                return _last_day_of_month(year, month), "month"
            except ValueError:
                pass

    # Step 5 — EU/ambiguous DD/MM/YYYY. Only after ISO so 2026-08-15 wins.
    eu_match = _EU_DATE_RE.search(raw)
    if eu_match:
        try:
            day = int(eu_match.group(1))
            month = int(eu_match.group(2))
            year = int(eu_match.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return date(year, month, day), "dated"
        except ValueError:
            pass

    # Step 6 — relative window.
    relative_match = _RELATIVE_RE.search(raw)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2).lower()
        if unit.startswith("day"):
            days = amount
        elif unit.startswith("week"):
            days = amount * 7
        else:
            days = amount * 30
        return today + timedelta(days=days), "relative"

    # Step 7 — bias rule. Pure narrative without a temporal token → ongoing.
    if not _TEMPORAL_TOKEN_RE.search(raw):
        return None, "ongoing"

    logger.info("parse_expected: temporal token but unparseable shape — expected=%r", raw)
    return None, "unparseable"


# ``unparseable`` is excluded so junk parses don't poison the active fleet —
# `_persist_discoveries` drops + logs them per-row (failure-mode-asymmetry:
# batch survives). New status = migration + this set + the parity test
# (`tests/shared/test_catalyst_expected_parser_parity.py`) in the same change.
PERSIST_OK_STATUSES: frozenset[ExpectedStatus] = frozenset(
    {"dated", "quarter", "month", "relative", "ongoing"}
)


__all__ = ["ExpectedStatus", "PERSIST_OK_STATUSES", "parse_expected"]
