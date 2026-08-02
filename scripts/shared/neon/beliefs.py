"""Agent belief persistence — write operations and belief chain linking.

Read-only queries live in belief_queries.py. All public symbols are re-exported
here so shared/neon/__init__.py and all existing callers work unchanged.
"""

import logging
from datetime import date

from ..database import get_db
from .belief_queries import (
    get_agent_belief_accuracy,
    get_all_belief_accuracy,
    get_all_prior_beliefs_by_ticker,
    get_latest_aggregated_beliefs,
    get_latest_beliefs_for_ensemble,
    get_prior_beliefs,
    get_stale_beliefs,  # noqa: F401 — re-exported via __init__.py
    get_unresolved_beliefs,
)

logger = logging.getLogger(__name__)

REVERSAL_CONVICTION_CAP = 0.6
PROBABILITY_SHIFT_THRESHOLD = 0.15


async def carry_forward_beliefs(
    scan_date: date,
    ensemble_type: str,
    decay_factor: float = 0.9,
    crisis_mode: bool = False,
) -> list[dict]:
    """Carry forward previous day's beliefs with decayed conviction.

    Used when EXIT_ONLY workflow skips sector agents, preserving belief chain
    continuity for calibration tracking.

    For CRISIS: stronger decay (0.7) + override BULLISH direction to NEUTRAL
    (carrying forward bullish bias into a crisis is dangerous).
    Sets days_held explicitly to avoid chain auto-increment contamination.
    """
    previous_beliefs = await get_latest_beliefs_for_ensemble(scan_date, ensemble_type)
    if not previous_beliefs:
        logger.info("No prior %s beliefs to carry forward for %s", ensemble_type, scan_date)
        return []

    effective_decay = 0.7 if crisis_mode else decay_factor
    carried = []
    for belief in previous_beliefs:
        new_conviction = round(float(belief.get("conviction") or 0.5) * effective_decay, 3)
        new_direction = belief.get("direction", "NEUTRAL")
        if crisis_mode and new_direction == "BULLISH":
            new_direction = "NEUTRAL"
        carried.append(
            {
                **belief,
                "ensemble_type": ensemble_type,
                "direction": new_direction,
                "conviction": new_conviction,
                "belief_status": "REAFFIRMED",
                "days_held": (belief.get("days_held") or 1) + 1,
                "update_reason": f"Carried forward (EXIT_ONLY, decay={effective_decay})",
            }
        )

    logger.info(
        "Carried forward %d %s beliefs for %s (decay=%.1f, crisis=%s)",
        len(carried),
        ensemble_type,
        scan_date,
        effective_decay,
        crisis_mode,
    )
    return carried


def _correct_belief_status(
    claimed_status: str,
    direction_changed: bool,
    probability_shifted: bool,
    has_prior: bool,
) -> str:
    """Deterministic belief status correction via transition rules.

    LLMs often mislabel belief status. This function enforces:
    - Direction change always means REVERSED (regardless of LLM claim)
    - Significant probability shift (>15pp bull) means UPDATED
    - No prior means NEW (regardless of LLM claim)
    """
    if not has_prior:
        return "NEW" if claimed_status != "NEW" else claimed_status

    if claimed_status == "NEW":
        if direction_changed:
            return "REVERSED"
        if probability_shifted:
            return "UPDATED"
        return "REAFFIRMED"

    if claimed_status == "REAFFIRMED":
        if direction_changed:
            return "REVERSED"
        if probability_shifted:
            return "UPDATED"
        return "REAFFIRMED"

    if claimed_status == "UPDATED":
        if direction_changed:
            return "REVERSED"
        return "UPDATED"

    if claimed_status == "REVERSED":
        if not direction_changed:
            return "UPDATED" if probability_shifted else "REAFFIRMED"
        return "REVERSED"

    return claimed_status


def _apply_reversal_penalty(belief: dict, belief_status: str) -> None:
    """Cap conviction for reversed beliefs. Mutates belief dict in place."""
    if belief_status != "REVERSED":
        return
    original_conviction = float(belief.get("conviction") or 0.5)
    if original_conviction > REVERSAL_CONVICTION_CAP:
        logger.info(
            "Capping reversed belief conviction %s/%s: %.2f -> %.2f",
            belief.get("agent_key", "?"),
            belief.get("ticker", "?"),
            original_conviction,
            REVERSAL_CONVICTION_CAP,
        )
        belief["conviction"] = REVERSAL_CONVICTION_CAP


# Re-export so `from shared.neon.beliefs import ...` keeps working for all callers
__all__ = [
    "get_prior_beliefs",
    "get_all_prior_beliefs_by_ticker",
    "get_unresolved_beliefs",
    "get_latest_aggregated_beliefs",
    "get_agent_belief_accuracy",
    "get_all_belief_accuracy",
    "insert_agent_beliefs",
    "resolve_beliefs",
]


async def insert_agent_beliefs(
    record_date: date,
    beliefs: list[dict],
    ensemble_type: str = "sector",
) -> None:
    """Persist agent beliefs with belief chain linking.

    Links each belief to its prior via prior_belief_id and computes days_held.
    Idempotent: deletes existing beliefs for same date+agent_key+ensemble_type.

    Raises on DB failure — the pipeline must see persistence failures so
    the morning run fails loud rather than producing recommendations
    without belief backing.
    """
    if not beliefs:
        return

    db = await get_db()
    try:
        # Bulk pre-fetch prior beliefs (outside transaction — read-only, no lock held)
        agent_keys = {belief["agent_key"] for belief in beliefs}
        prior_rows = await db.fetch_all(
            """
            SELECT DISTINCT ON (agent_key, ticker)
                id, agent_key, ticker, direction, days_held, bull_probability
            FROM agent_beliefs
            WHERE agent_key = ANY($1) AND record_date < $2
            ORDER BY agent_key, ticker, record_date DESC
            """,
            list(agent_keys),
            record_date,
        )
        prior_map = {(row["agent_key"], row["ticker"]): row for row in prior_rows}

        # Transaction ensures DELETE+INSERT is atomic — no data loss on partial failure
        async with db.transaction() as conn:
            for agent_key in agent_keys:
                await conn.execute(
                    """
                    DELETE FROM agent_beliefs
                    WHERE record_date = $1 AND agent_key = $2 AND ensemble_type = $3
                    """,
                    record_date,
                    agent_key,
                    ensemble_type,
                )

            inserted = 0
            for belief in beliefs:
                agent_key = belief["agent_key"]
                ticker = belief["ticker"]
                prior = prior_map.get((agent_key, ticker))

                prior_belief_id = prior["id"] if prior else None
                belief_status = belief.get("belief_status") or "NEW"

                # Validate belief continuity via deterministic transition rules
                new_direction = belief.get("direction")
                prior_direction = prior["direction"] if prior else None
                prior_bull = float(prior.get("bull_probability") or 0) if prior else 0
                new_bull = float(belief.get("bull_probability") or 0)

                corrected_status = _correct_belief_status(
                    claimed_status=belief_status,
                    direction_changed=bool(new_direction and new_direction != prior_direction),
                    probability_shifted=abs(new_bull - prior_bull) > PROBABILITY_SHIFT_THRESHOLD,
                    has_prior=prior is not None,
                )
                if corrected_status != belief_status:
                    logger.info(
                        "Auto-correcting %s/%s: %s->%s",
                        agent_key,
                        ticker,
                        belief_status,
                        corrected_status,
                    )
                    belief_status = corrected_status

                # Catches both auto-corrected and LLM-declared REVERSED
                _apply_reversal_penalty(belief, belief_status)

                # Compute days_held from chain
                if prior and belief.get("direction") == prior["direction"]:
                    days_held = (prior["days_held"] or 1) + 1
                else:
                    days_held = 1

                await conn.execute(
                    """
                    INSERT INTO agent_beliefs (
                        record_date, ticker, agent_key, ensemble_type,
                        belief_narrative, direction,
                        bull_probability, base_probability, bear_probability,
                        price_target_vnd, timeframe_days, conviction,
                        belief_status, prior_belief_id, days_held, update_reason
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16
                    )
                    ON CONFLICT (record_date, ticker, agent_key, ensemble_type)
                    DO UPDATE SET
                        belief_narrative = EXCLUDED.belief_narrative,
                        direction = EXCLUDED.direction,
                        bull_probability = EXCLUDED.bull_probability,
                        base_probability = EXCLUDED.base_probability,
                        bear_probability = EXCLUDED.bear_probability,
                        price_target_vnd = EXCLUDED.price_target_vnd,
                        timeframe_days = EXCLUDED.timeframe_days,
                        conviction = EXCLUDED.conviction,
                        belief_status = EXCLUDED.belief_status,
                        prior_belief_id = EXCLUDED.prior_belief_id,
                        days_held = EXCLUDED.days_held,
                        update_reason = EXCLUDED.update_reason
                    """,
                    record_date,
                    ticker,
                    agent_key,
                    ensemble_type,
                    belief.get("belief_narrative") or "",
                    belief["direction"],
                    float(belief["bull_probability"]),
                    float(belief["base_probability"]),
                    float(belief["bear_probability"]),
                    belief.get("price_target_vnd") or None,
                    belief.get("timeframe_days") or 5,
                    float(belief["conviction"]),
                    belief_status,
                    prior_belief_id,
                    days_held,
                    belief.get("update_reason"),
                )
                inserted += 1

        logger.info("Inserted %d agent beliefs for %s", inserted, record_date)
    except Exception as e:
        logger.error(
            "Failed to insert agent beliefs for date=%s ensemble=%s: %s",
            record_date,
            ensemble_type,
            e,
        )
        raise


async def resolve_beliefs(resolutions: list[dict]) -> int:
    """Batch-update beliefs with actual outcomes and Brier scores."""
    if not resolutions:
        return 0

    db = await get_db()
    resolved = 0
    for resolution in resolutions:
        await db.execute(
            """
            UPDATE agent_beliefs
            SET actual_direction = $2,
                actual_price_vnd = $3,
                outcome_date = $4,
                brier_score = $5,
                direction_correct = $6,
                price_error_pct = $7
            WHERE id = $1
            """,
            resolution["id"],
            resolution["actual_direction"],
            resolution["actual_price_vnd"],
            resolution["outcome_date"],
            resolution["brier_score"],
            resolution["direction_correct"],
            resolution.get("price_error_pct"),
        )
        resolved += 1

    logger.info("Resolved %d beliefs with outcomes", resolved)
    return resolved


async def tombstone_beliefs(belief_ids: list[int]) -> int:
    """Mark stale beliefs as EXPIRED — they aged past the scoring window.

    Sets outcome_date to their computed horizon and actual_direction to 'EXPIRED'
    to distinguish from scored beliefs (which have brier_score IS NOT NULL).
    """
    if not belief_ids:
        return 0

    db = await get_db()
    result = await db.execute(
        """
        UPDATE agent_beliefs
        SET outcome_date = record_date + timeframe_days * INTERVAL '1 day',
            actual_direction = 'EXPIRED'
        WHERE id = ANY($1)
          AND outcome_date IS NULL
        """,
        belief_ids,
    )
    count = int(result.split()[-1]) if result else 0
    logger.info("Tombstoned %d stale beliefs as EXPIRED", count)
    return count
