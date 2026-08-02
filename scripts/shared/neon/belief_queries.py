"""Pure SELECT queries for agent belief data."""

from collections.abc import Sequence
from datetime import date

from asyncpg import Record

from ..database import get_db


async def get_prior_beliefs(agent_key: str, scan_date: date) -> list[dict]:
    """Get this agent's most recent beliefs (for belief continuity).

    Returns the latest belief per ticker for this agent_key,
    looking back at most 5 trading days from scan_date.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT DISTINCT ON (ticker)
            id, ticker, belief_narrative, direction,
            bull_probability, base_probability, bear_probability,
            price_target_vnd, timeframe_days, conviction,
            belief_status, days_held, record_date
        FROM agent_beliefs
        WHERE agent_key = $1
          AND record_date < $2
          AND record_date >= $2 - INTERVAL '7 days'
        ORDER BY ticker, record_date DESC
        """,
        agent_key,
        scan_date,
    )
    return [dict(row) for row in rows]


async def get_all_prior_beliefs_by_ticker(
    scan_date: date,
    tickers: list[str] | None = None,
) -> dict[str, list[dict]]:
    """Batch-fetch prior beliefs for all agents, grouped by ticker.

    Returns {ticker: [belief_dict, ...]} with agent_key included in each dict.
    Used by enrichment_loader for context injection.
    """
    db = await get_db()
    query = """
        SELECT DISTINCT ON (agent_key, ticker)
            ticker, agent_key, direction, conviction,
            bull_probability, base_probability, bear_probability,
            belief_status, days_held, record_date
        FROM agent_beliefs
        WHERE record_date < $1
          AND record_date >= $1 - INTERVAL '7 days'
    """
    params: list = [scan_date]
    if tickers:
        query += "  AND ticker = ANY($2)"
        params.append(tickers)
    query += "\nORDER BY agent_key, ticker, record_date DESC"

    rows = await db.fetch_all(query, *params)

    result: dict[str, list[dict]] = {}
    for row in rows:
        row_dict = dict(row)
        ticker = row_dict["ticker"]
        if ticker not in result:
            result[ticker] = []
        result[ticker].append(row_dict)
    return result


async def get_unresolved_beliefs(
    max_age_days: int = 10, scan_date: date | None = None
) -> list[dict]:
    """Get beliefs past their horizon that haven't been scored yet.

    Args:
        max_age_days: only look back this many days from reference date.
        scan_date: reference date for horizon check. Defaults to CURRENT_DATE
            for live runs; pass explicitly for backfills/determinism.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT id, record_date, ticker, agent_key, direction,
               bull_probability, base_probability, bear_probability,
               price_target_vnd, timeframe_days
        FROM agent_beliefs
        WHERE outcome_date IS NULL
          AND record_date + timeframe_days * INTERVAL '1 day'
              <= COALESCE($2::date, CURRENT_DATE)
          AND record_date >= COALESCE($2::date, CURRENT_DATE) - $1 * INTERVAL '1 day'
        ORDER BY record_date
        """,
        max_age_days,
        scan_date,
    )
    return [dict(row) for row in rows]


async def get_stale_beliefs(max_age_days: int = 60, scan_date: date | None = None) -> list[dict]:
    """Get beliefs that aged out of the scoring window and will never be resolved.

    Inverse of get_unresolved_beliefs' age filter: finds beliefs where
    outcome_date IS NULL AND record_date is older than max_age_days from scan_date.
    These beliefs' horizons have passed but they fell outside the lookback window.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT id, record_date, ticker, agent_key, timeframe_days
        FROM agent_beliefs
        WHERE outcome_date IS NULL
          AND record_date + timeframe_days * INTERVAL '1 day'
              <= COALESCE($2::date, CURRENT_DATE)
          AND record_date < COALESCE($2::date, CURRENT_DATE) - $1 * INTERVAL '1 day'
        ORDER BY record_date
        """,
        max_age_days,
        scan_date,
    )
    return [dict(row) for row in rows]


async def get_latest_aggregated_beliefs(
    scan_date: date,
    ensemble_type: str | None = None,
) -> list[dict]:
    """Fetch today's aggregated beliefs for downstream consumption.

    Returns beliefs from aggregator agents (sector_aggregator, positions_aggregator,
    deterministic_aggregator), for the exact scan_date.
    Callers handle fallback logic (e.g., phase_picks tries deterministic then LLM).
    """
    db = await get_db()
    query = """
        SELECT ticker, agent_key, ensemble_type, direction,
               bull_probability, base_probability, bear_probability,
               price_target_vnd, timeframe_days, conviction,
               belief_narrative, belief_status, days_held
        FROM agent_beliefs
        WHERE record_date = $1
          AND agent_key IN ('sector_aggregator', 'positions_aggregator', 'deterministic_aggregator')
    """
    params: list = [scan_date]
    if ensemble_type:
        query += "  AND ensemble_type = $2"
        params.append(ensemble_type)
    query += "\nORDER BY ticker"
    rows = await db.fetch_all(query, *params)
    return [dict(row) for row in rows]


async def get_latest_beliefs_for_ensemble(
    scan_date: date,
    ensemble_type: str,
) -> list[dict]:
    """Fetch most recent beliefs for an ensemble type, for carry-forward.

    Returns the latest belief per (agent_key, ticker) looking back up to 7 days.
    Used by carry_forward_beliefs when EXIT_ONLY skips sector agents.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT DISTINCT ON (agent_key, ticker)
            agent_key, ticker, ensemble_type, direction,
            bull_probability, base_probability, bear_probability,
            price_target_vnd, timeframe_days, conviction,
            belief_narrative, belief_status, days_held
        FROM agent_beliefs
        WHERE ensemble_type = $1
          AND record_date < $2
          AND record_date >= $2 - INTERVAL '7 days'
        ORDER BY agent_key, ticker, record_date DESC
        """,
        ensemble_type,
        scan_date,
    )
    return [dict(row) for row in rows]


async def get_agent_belief_accuracy(agent_key: str, days_back: int = 30) -> dict:
    """Per-agent calibration stats for prompt injection."""
    db = await get_db()
    row = await db.fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE brier_score IS NOT NULL) AS scored_beliefs,
            ROUND(AVG(brier_score) FILTER (WHERE brier_score IS NOT NULL), 4)
                AS avg_brier,
            ROUND(AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END)
                FILTER (WHERE direction_correct IS NOT NULL), 3)
                AS direction_accuracy,
            ROUND(AVG(conviction), 3) AS avg_conviction,
            ROUND(AVG(days_held) FILTER (WHERE belief_status != 'NEW'), 1)
                AS avg_streak_length,
            COUNT(*) FILTER (WHERE belief_status = 'REVERSED') AS reversals,
            ROUND(AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END)
                FILTER (WHERE days_held >= 3
                    AND direction_correct IS NOT NULL), 3)
                AS accuracy_streak_3plus
        FROM agent_beliefs
        WHERE agent_key = $1
          AND record_date >= CURRENT_DATE - $2 * INTERVAL '1 day'
        """,
        agent_key,
        days_back,
    )
    return dict(row) if row else {}


async def get_all_belief_accuracy(days_back: int = 30) -> dict[str, dict]:
    """All agents' calibration stats.

    NOTE: days_back is accepted but unused — v_agent_belief_accuracy view
    has its own hardcoded lookback window for brier_30d.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT * FROM v_agent_belief_accuracy
        WHERE scored_beliefs > 0
        """,
    )
    return {row["agent_key"]: dict(row) for row in rows}


def _rows_to_distribution(rows: Sequence[Record], column: str) -> dict[str, float]:
    """Convert grouped COUNT rows to a probability distribution."""
    counts: dict[str, int] = {}
    total = 0
    for row in rows:
        counts[row[column]] = int(row["cnt"])
        total += int(row["cnt"])
    if total == 0:
        return {}
    return {
        "BULLISH": round(counts.get("BULLISH", 0) / total, 4),
        "NEUTRAL": round(counts.get("NEUTRAL", 0) / total, 4),
        "BEARISH": round(counts.get("BEARISH", 0) / total, 4),
    }


async def compute_empirical_base_rates(days_back: int = 90) -> dict[str, float]:
    """Compute empirical base rates from scored belief outcomes.

    Queries actual_direction distribution from resolved beliefs over the
    rolling window. Used by apply_base_rate_anchor for correct calibration.

    Returns:
        {"BULLISH": float, "NEUTRAL": float, "BEARISH": float} summing to 1.0

    Raises:
        ValueError: If no scored beliefs found in the window.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT actual_direction, COUNT(*) as cnt
        FROM agent_beliefs
        WHERE actual_direction IS NOT NULL
          AND brier_score IS NOT NULL
          AND record_date >= CURRENT_DATE - $1 * INTERVAL '1 day'
        GROUP BY actual_direction
        """,
        days_back,
    )
    if not rows:
        raise ValueError(
            f"No scored beliefs found in last {days_back} days — "
            "cannot compute base rates. Check belief_scoring pipeline."
        )

    result = _rows_to_distribution(rows, "actual_direction")
    if not result:
        raise ValueError("Zero total scored beliefs — cannot compute base rates.")
    return result


async def compute_agent_prediction_vs_actual(
    agent_key: str, days_back: int = 30
) -> tuple[dict[str, float], dict[str, float]]:
    """Compute predicted and actual direction distributions in a single query.

    Returns:
        (predicted_distribution, actual_distribution) — each is
        {"BULLISH": float, "NEUTRAL": float, "BEARISH": float} or {} if no data.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT direction, actual_direction, COUNT(*) as cnt
        FROM agent_beliefs
        WHERE agent_key = $1
          AND brier_score IS NOT NULL
          AND actual_direction IS NOT NULL
          AND record_date >= CURRENT_DATE - $2 * INTERVAL '1 day'
        GROUP BY direction, actual_direction
        """,
        agent_key,
        days_back,
    )
    if not rows:
        return {}, {}

    # Derive both distributions from the cross-tab
    predicted_counts: dict[str, int] = {}
    actual_counts: dict[str, int] = {}
    total = 0
    for row in rows:
        count = int(row["cnt"])
        total += count
        predicted_counts[row["direction"]] = predicted_counts.get(row["direction"], 0) + count
        actual_counts[row["actual_direction"]] = (
            actual_counts.get(row["actual_direction"], 0) + count
        )

    if total == 0:
        return {}, {}

    predicted = {
        "BULLISH": round(predicted_counts.get("BULLISH", 0) / total, 4),
        "NEUTRAL": round(predicted_counts.get("NEUTRAL", 0) / total, 4),
        "BEARISH": round(predicted_counts.get("BEARISH", 0) / total, 4),
    }
    actual = {
        "BULLISH": round(actual_counts.get("BULLISH", 0) / total, 4),
        "NEUTRAL": round(actual_counts.get("NEUTRAL", 0) / total, 4),
        "BEARISH": round(actual_counts.get("BEARISH", 0) / total, 4),
    }
    return predicted, actual


async def get_scored_beliefs_for_platt(
    agent_key: str, days_back: int = 90
) -> list[tuple[float, float, float, str]]:
    """Fetch scored beliefs for Platt scaling calibration.

    Returns list of (bull_prob, base_prob, bear_prob, actual_direction) tuples
    for beliefs that have been resolved (brier_score IS NOT NULL).
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT bull_probability, base_probability, bear_probability, actual_direction
        FROM agent_beliefs
        WHERE agent_key = $1
          AND brier_score IS NOT NULL
          AND actual_direction IS NOT NULL
          AND record_date >= CURRENT_DATE - $2 * INTERVAL '1 day'
        ORDER BY record_date
        """,
        agent_key,
        days_back,
    )
    return [
        (
            float(row["bull_probability"]),
            float(row["base_probability"]),
            float(row["bear_probability"]),
            row["actual_direction"],
        )
        for row in rows
    ]
