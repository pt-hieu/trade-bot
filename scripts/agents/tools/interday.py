"""
Inter-day context for critic agent.

Loads previous trading day's morning brief and detects recommendation drifts.
Helps critic flag consistency issues like EXIT → TRIM with identical data.
"""

import re
from datetime import date, timedelta
from pathlib import Path

from shared.errors import report_caught
from shared.market_calendar import is_trading_day

_RESEARCH_DIR = Path(__file__).parent.parent.parent.parent / "research"
_BRIEF_FILENAME = "morning-brief.md"


def _get_previous_trading_day(ref_date: date, max_lookback: int = 7) -> date | None:
    """Get most recent previous trading day with a brief available.

    Skips weekends and holidays. Checks for brief file existence.
    """
    for days_back in range(1, max_lookback + 1):
        candidate = ref_date - timedelta(days=days_back)
        if not is_trading_day(candidate):
            continue
        brief_path = _RESEARCH_DIR / candidate.isoformat() / _BRIEF_FILENAME
        if brief_path.exists():
            return candidate
    return None


async def load_previous_day_context(scan_date: date) -> dict:
    """Load previous trading day's brief for inter-day consistency checks.

    Args:
        scan_date: Today's scan date

    Returns:
        Dict with previous_brief (str|None), previous_date (date|None)
    """
    prev_date = _get_previous_trading_day(scan_date)
    if not prev_date:
        return {"previous_brief": None, "previous_date": None}

    brief_path = _RESEARCH_DIR / prev_date.isoformat() / _BRIEF_FILENAME
    try:
        previous_brief = brief_path.read_text(encoding="utf-8")
    except Exception as e:
        report_caught("tool.interday", e, prev_date=str(prev_date))
        return {"previous_brief": None, "previous_date": prev_date}

    return {
        "previous_brief": previous_brief,
        "previous_date": prev_date,
    }


def extract_position_recommendations(brief: str) -> dict[str, dict]:
    """Parse MY HOLDINGS section → {ticker: {action, stop, reason}}.

    Returns empty dict if section not found or parse fails.
    """
    if not brief:
        return {}

    # Find MY HOLDINGS section
    start = brief.find("MY HOLDINGS")
    if start == -1:
        return {}

    # Find next major section boundary
    end_markers = ["TOP PICKS", "SKIP THESE", "WHAT TO DO"]
    end = len(brief)
    for marker in end_markers:
        idx = brief.find(marker, start + 10)
        if idx != -1 and idx < end:
            end = idx

    section = brief[start:end]

    # Parse each position line: "- TICKER: ACTION — reason"
    recs = {}
    ticker_pattern = re.compile(
        r"[-•]\s*([A-Z]{2,5}):\s*(EXIT|TRIM|HOLD|ADD|WATCH)\b",
        re.IGNORECASE,
    )

    for match in ticker_pattern.finditer(section):
        ticker = match.group(1).upper()
        action = match.group(2).upper()

        # Extract context after the action (until next line or end)
        pos = match.end()
        line_end = section.find("\n", pos)
        context_str = section[pos : line_end if line_end != -1 else pos + 300].strip()
        # Remove leading separator chars
        context_str = context_str.lstrip("—-–: ").strip()

        # Extract stop if present
        stop_match = re.search(r"stop[=:@\s]+(\d[\d,.]*[kKmM]?)", context_str, re.IGNORECASE)
        stop = stop_match.group(1) if stop_match else None

        recs[ticker] = {
            "action": action,
            "stop": stop,
            "reason": context_str[:200],
        }

    return recs


def detect_interday_drifts(
    today_draft: str,
    previous_brief: str,
    current_holdings: list[dict] | None = None,
) -> list[str]:
    """Detect recommendation drifts between today and yesterday.

    Returns list of drift descriptions formatted for critic prompt injection.
    """
    if not today_draft or not previous_brief:
        return []

    prev_recs = extract_position_recommendations(previous_brief)
    today_recs = extract_position_recommendations(today_draft)

    if not prev_recs or not today_recs:
        return []

    drifts = []

    # Check common tickers for action regression
    for ticker in set(prev_recs) & set(today_recs):
        prev = prev_recs[ticker]
        today = today_recs[ticker]
        prev_action = prev["action"]
        today_action = today["action"]

        # EXIT → TRIM drift (most critical — loses urgency with same data)
        if prev_action == "EXIT" and today_action == "TRIM":
            drifts.append(
                f"[interday_drift] {ticker}: was EXIT yesterday, now TRIM — "
                "verify P/L/price changed before downgrading urgency"
            )

        # EXIT → HOLD drift
        elif prev_action == "EXIT" and today_action == "HOLD":
            drifts.append(
                f"[interday_drift] {ticker}: was EXIT yesterday, now HOLD — "
                "requires new bullish catalyst or confirmation stop held"
            )

        # TRIM → HOLD drift
        elif prev_action == "TRIM" and today_action == "HOLD":
            drifts.append(
                f"[interday_drift] {ticker}: was TRIM yesterday, now HOLD — "
                "was partial profit taken? If not, downgrade not justified"
            )

        # Stop loosening (regression)
        if prev.get("stop") and today.get("stop"):
            try:

                def _parse_stop(s: str) -> float:
                    s = s.replace(",", "").replace(".", "")
                    s = s.lower().replace("k", "000").replace("m", "000000")
                    return float(s)

                prev_stop = _parse_stop(prev["stop"])
                today_stop = _parse_stop(today["stop"])

                # Stop moved DOWN by more than 5% = regression
                if prev_stop > 0 and today_stop < prev_stop * 0.95:
                    drifts.append(
                        f"[stop_regression] {ticker}: stop loosened "
                        f"{prev['stop']} → {today['stop']} "
                        "(regression unless accumulation mode)"
                    )
            except (ValueError, AttributeError):
                pass

    # Unfollowed EXIT: EXIT yesterday, still in holdings today
    if current_holdings:
        held_tickers = {
            slice_row["ticker"] for slice_row in current_holdings if slice_row.get("ticker")
        }
        for ticker in set(prev_recs) - set(today_recs):
            if prev_recs[ticker]["action"] == "EXIT" and ticker in held_tickers:
                drifts.append(
                    f"[unfollowed_exit] {ticker}: was EXIT yesterday, still in holdings — "
                    "was exit executed? If not, re-evaluate urgency"
                )

    return drifts
