"""Thesis tracker for longterm watchlist: pillars, kill criteria, conviction drift.

All DB operations are async. Deterministic computations (status, drift detection)
are pure Python — LLM provides qualitative content, Python manages state.
"""

from __future__ import annotations

import json
from datetime import date

# ── Status constants ─────────────────────────────────────────────────────────

PILLAR_STATUSES = ("INTACT", "WEAKENING", "BROKEN")
KILL_STATUSES = ("NOT_MET", "WARNING", "TRIGGERED")

# Conviction levels ordered for drift detection (low → high)
CONVICTION_ORDER = ["Low", "Medium-Low", "Medium", "Medium-High", "High"]


# ── Deterministic computations ───────────────────────────────────────────────


def compute_thesis_status(pillars: list[dict]) -> tuple[str, int, int]:
    """Compute overall thesis status from pillar list.

    Returns (status, broken_count, weakening_count).
    Any BROKEN pillar → BROKEN overall.
    Any WEAKENING (no BROKEN) → WEAKENING overall.
    All INTACT → INTACT.
    """
    broken = sum(1 for p in pillars if p.get("status") == "BROKEN")
    weakening = sum(1 for p in pillars if p.get("status") == "WEAKENING")
    if broken > 0:
        return "BROKEN", broken, weakening
    if weakening > 0:
        return "WEAKENING", 0, weakening
    return "INTACT", 0, 0


def detect_conviction_drift(
    conviction_history: list[dict],
    current_conviction: str,
) -> dict | None:
    """Detect significant conviction drift (2+ levels).

    Returns drift dict if drift >= 2 levels, else None.
    conviction_history: list of {date, conviction, ...} newest-first.
    """
    if not conviction_history or current_conviction not in CONVICTION_ORDER:
        return None
    oldest = conviction_history[-1].get("conviction", "") if conviction_history else None
    if not oldest or oldest not in CONVICTION_ORDER:
        return None

    current_idx = CONVICTION_ORDER.index(current_conviction)
    oldest_idx = CONVICTION_ORDER.index(oldest)
    delta = current_idx - oldest_idx

    if abs(delta) >= 2:
        direction = "UP" if delta > 0 else "DOWN"
        return {
            "from_conviction": oldest,
            "to_conviction": current_conviction,
            "levels_drifted": abs(delta),
            "direction": direction,
            "oldest_date": conviction_history[-1].get("date"),
        }
    return None


def check_kill_criteria(ratios: dict, kill_criteria: list[dict]) -> list[dict]:
    """Check kill criteria against latest financial ratios.

    Returns updated kill_criteria list with status flags applied.
    Purely deterministic — compares ratio values against conditions.
    ROE stored as whole % (15.0 = 15%) in ratios dict.
    """
    updated = []
    for criterion in kill_criteria:
        condition = criterion.get("condition", "")
        current_status = criterion.get("status", "NOT_MET")
        new_status = _evaluate_condition(condition, ratios, current_status)
        updated.append({**criterion, "status": new_status, "checked_at": str(date.today())})
    return updated


def _evaluate_condition(condition: str, ratios: dict, current_status: str) -> str:
    """Pattern-match simple kill criteria conditions against ratios.

    Returns NOT_MET / WARNING / TRIGGERED.
    Conservative: only flags conditions we can parse; others unchanged.
    """
    condition_lower = condition.lower()
    roe_raw = ratios.get("roe")
    roe_pct = roe_raw  # already whole % from API normalization

    # "ROE below X%" → WARNING on first detection
    if "roe below" in condition_lower and roe_pct is not None:
        try:
            threshold = float(condition_lower.split("roe below")[1].split("%")[0].strip())
            if roe_pct < threshold:
                return "WARNING" if current_status == "NOT_MET" else current_status
        except (ValueError, IndexError):
            pass

    return current_status


# ── DB operations ────────────────────────────────────────────────────────────


async def get_thesis(ticker: str) -> dict | None:
    """Fetch thesis tracker entry for a ticker. Returns None if not found."""
    from shared.database import get_db

    db = await get_db()
    rows = await db.fetch_all(
        """SELECT ticker, pillars, kill_criteria, conviction_history,
                  overall_thesis_status, broken_count, weakening_count,
                  created_at, updated_at
           FROM thesis_tracker
           WHERE ticker = $1""",
        ticker.upper(),
    )
    return dict(rows[0]) if rows else None


async def get_thesis_batch(tickers: list[str]) -> dict[str, dict | None]:
    """Fetch thesis tracker entries for a batch of tickers in one query.

    Returns dict mapping uppercased ticker to thesis dict or None if not tracked.
    """
    from shared.database import get_db

    if not tickers:
        return {}

    normalized = [ticker.upper() for ticker in tickers]
    db = await get_db()
    rows = await db.fetch_all(
        """SELECT ticker, pillars, kill_criteria, conviction_history,
                  overall_thesis_status, broken_count, weakening_count,
                  created_at, updated_at
           FROM thesis_tracker
           WHERE ticker = ANY($1::text[])""",
        normalized,
    )
    found = {row["ticker"]: dict(row) for row in rows}
    return {ticker: found.get(ticker) for ticker in normalized}


async def upsert_thesis(
    ticker: str,
    pillars: list[dict],
    kill_criteria: list[dict],
) -> None:
    """Insert or update thesis tracker entry.

    Computes overall_thesis_status, broken_count, weakening_count
    deterministically from pillars before storing.
    """
    from shared.database import get_db

    ticker = ticker.upper()
    status, broken, weakening = compute_thesis_status(pillars)
    db = await get_db()
    await db.execute(
        """INSERT INTO thesis_tracker
               (ticker, pillars, kill_criteria, overall_thesis_status,
                broken_count, weakening_count, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, NOW())
           ON CONFLICT (ticker) DO UPDATE SET
               pillars               = EXCLUDED.pillars,
               kill_criteria         = EXCLUDED.kill_criteria,
               overall_thesis_status = EXCLUDED.overall_thesis_status,
               broken_count          = EXCLUDED.broken_count,
               weakening_count       = EXCLUDED.weakening_count,
               updated_at            = NOW()""",
        ticker,
        json.dumps(pillars),
        json.dumps(kill_criteria),
        status,
        broken,
        weakening,
    )


async def record_thesis_update(
    ticker: str,
    source: str,
    pillar_changes: list[dict] | None = None,
    kill_criteria_changes: list[dict] | None = None,
    conviction_change: dict | None = None,
    data_point: str | None = None,
    impact: str | None = None,
    action_taken: str | None = None,
) -> None:
    """Record a thesis update event in the audit log."""
    from shared.database import get_db

    db = await get_db()
    await db.execute(
        """INSERT INTO thesis_updates
               (ticker, source, pillar_changes, kill_criteria_changes,
                conviction_change, data_point, impact, action_taken)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
        ticker.upper(),
        source,
        json.dumps(pillar_changes) if pillar_changes else None,
        json.dumps(kill_criteria_changes) if kill_criteria_changes else None,
        json.dumps(conviction_change) if conviction_change else None,
        data_point,
        impact,
        action_taken,
    )


async def get_thesis_updates(ticker: str, limit: int = 10) -> list[dict]:
    """Fetch recent thesis updates for a ticker."""
    from shared.database import get_db

    db = await get_db()
    rows = await db.fetch_all(
        """SELECT id, ticker, update_date, source, pillar_changes,
                  kill_criteria_changes, conviction_change,
                  data_point, impact, action_taken, created_at
           FROM thesis_updates
           WHERE ticker = $1
           ORDER BY update_date DESC, created_at DESC
           LIMIT $2""",
        ticker.upper(),
        limit,
    )
    return [dict(r) for r in rows]


async def get_thesis_updates_batch(
    tickers: list[str], limit_per_ticker: int = 3
) -> dict[str, list[dict]]:
    """Fetch recent thesis updates for a batch of tickers in one query.

    Uses ROW_NUMBER() to keep only the top-N most recent updates per ticker.
    Returns dict mapping uppercased ticker to ordered list (newest first).
    """
    from shared.database import get_db

    if not tickers:
        return {}

    normalized = [ticker.upper() for ticker in tickers]
    db = await get_db()
    rows = await db.fetch_all(
        """SELECT id, ticker, update_date, source, pillar_changes,
                  kill_criteria_changes, conviction_change,
                  data_point, impact, action_taken, created_at
           FROM (
               SELECT *,
                      ROW_NUMBER() OVER (
                          PARTITION BY ticker
                          ORDER BY update_date DESC, created_at DESC
                      ) AS rn
               FROM thesis_updates
               WHERE ticker = ANY($1::text[])
           ) ranked
           WHERE rn <= $2
           ORDER BY ticker, update_date DESC, created_at DESC""",
        normalized,
        limit_per_ticker,
    )
    result: dict[str, list[dict]] = {ticker: [] for ticker in normalized}
    for row in rows:
        result[row["ticker"]].append(dict(row))
    return result
