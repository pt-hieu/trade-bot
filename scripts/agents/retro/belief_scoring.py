#!/usr/bin/env python3
"""
Belief scoring — Brier scores and outcome resolution for agent beliefs.

Runs as Step 3.9 in the retro pipeline: finds beliefs whose prediction
horizon has passed, computes Brier scores against actual price movement.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Direction classification threshold (percentage)
DIRECTION_THRESHOLD_PCT = 1.5


@dataclass
class BeliefScoringResult:
    """Outcome of a belief scoring run — makes silent failures visible."""

    resolved: int = 0
    unresolved_found: int = 0
    skipped_missing_outcome_price: list[str] = field(default_factory=list)
    skipped_missing_entry_price: list[str] = field(default_factory=list)
    skipped_not_yet_mature: list[str] = field(default_factory=list)
    fetch_error: bool = False
    persist_error: bool = False
    tombstoned: int = 0


def compute_brier_score(
    bull_probability: float,
    base_probability: float,
    bear_probability: float,
    actual_direction: str,
) -> float:
    """Multi-class Brier score.

    Score = sum((predicted_i - actual_i)^2) for each class.
    Range: [0, 2]. Lower = better. 0 = perfect, 2 = maximally wrong.

    Args:
        bull_probability: predicted P(BULLISH)
        base_probability: predicted P(NEUTRAL)
        bear_probability: predicted P(BEARISH)
        actual_direction: "BULLISH", "NEUTRAL", or "BEARISH"
    """
    actual_vector = {
        "BULLISH": (1.0, 0.0, 0.0),
        "NEUTRAL": (0.0, 1.0, 0.0),
        "BEARISH": (0.0, 0.0, 1.0),
    }

    if actual_direction not in actual_vector:
        raise ValueError(f"Invalid direction: {actual_direction}")

    actual = actual_vector[actual_direction]
    predicted = (bull_probability, base_probability, bear_probability)

    return sum((p - a) ** 2 for p, a in zip(predicted, actual, strict=True))


def classify_actual_direction(
    entry_price_vnd: int,
    actual_price_vnd: int,
    threshold_pct: float = DIRECTION_THRESHOLD_PCT,
) -> str:
    """Classify actual price movement as BULLISH/BEARISH/NEUTRAL.

    Args:
        entry_price_vnd: price at prediction time (VND)
        actual_price_vnd: price at horizon (VND)
        threshold_pct: movement threshold (default 3%)
    """
    if entry_price_vnd <= 0:
        return "NEUTRAL"

    change_pct = (actual_price_vnd - entry_price_vnd) / entry_price_vnd * 100

    if change_pct > threshold_pct:
        return "BULLISH"
    elif change_pct < -threshold_pct:
        return "BEARISH"
    return "NEUTRAL"


def _parse_close_vnd(price_data: dict | None) -> int | None:
    """Extract close price as VND integer, treating 0 as missing data."""
    if not price_data:
        return None
    close = price_data.get("close")
    if not close or close <= 0:
        return None
    from shared.units import thousands_to_vnd

    return thousands_to_vnd(close)


async def resolve_mature_beliefs(scan_date: date) -> BeliefScoringResult:
    """Find beliefs whose horizon has passed, compute Brier scores, update DB.

    Called as Step 3.9 in the retro pipeline, after EOD prices are fetched.
    """

    from shared.market_calendar import last_trading_day, next_trading_day
    from shared.neon import (
        get_stale_beliefs,
        get_unresolved_beliefs,
        resolve_beliefs,
        tombstone_beliefs,
    )
    from shared.vnstock_client import get_price_on_date

    # SWI-382: a retro running on a weekend/holiday receives a non-trading
    # scan_date. Normalize to the last trading day so the maturity boundary
    # (`trading_horizon > scan_date`) and outcome-price lookups align to real
    # sessions — Friday-mature beliefs resolve instead of being deferred until
    # the next weekday run. No-op when scan_date is already a trading day.
    scan_date = last_trading_day(scan_date)

    result = BeliefScoringResult()

    try:
        unresolved = await get_unresolved_beliefs(max_age_days=60, scan_date=scan_date)
    except Exception as error:
        logger.warning("Failed to fetch unresolved beliefs: %s", error)
        result.fetch_error = True
        return result

    result.unresolved_found = len(unresolved)
    if not unresolved:
        logger.info("No mature beliefs to resolve")
        return result

    logger.info("Found %d unresolved beliefs eligible for scoring", len(unresolved))

    resolutions = []
    price_cache: dict[tuple[str, date], int | None] = {}

    for belief in unresolved:
        ticker = belief["ticker"]
        agent_key = belief["agent_key"]
        calendar_horizon = belief["record_date"] + timedelta(days=belief["timeframe_days"])
        trading_horizon = next_trading_day(calendar_horizon)
        if trading_horizon > scan_date:
            result.skipped_not_yet_mature.append(f"{agent_key}/{ticker}")
            continue
        outcome_date = trading_horizon

        cache_key = (ticker, outcome_date)
        if cache_key not in price_cache:
            try:
                price_data = await get_price_on_date(ticker, outcome_date)
                price_cache[cache_key] = _parse_close_vnd(price_data)
            except Exception as exception:
                logger.warning(
                    "Failed to get price for %s on %s: %s", ticker, outcome_date, exception
                )
                price_cache[cache_key] = None

        actual_price_vnd = price_cache[cache_key]
        if actual_price_vnd is None:
            logger.warning(
                "Skipping belief %s/%s: missing outcome price for %s on %s",
                agent_key,
                ticker,
                ticker,
                outcome_date,
            )
            result.skipped_missing_outcome_price.append(f"{agent_key}/{ticker}")
            continue

        # Fetch entry price (price at prediction time)
        entry_cache_key = (ticker, belief["record_date"])
        if entry_cache_key not in price_cache:
            try:
                entry_data = await get_price_on_date(ticker, belief["record_date"])
                price_cache[entry_cache_key] = _parse_close_vnd(entry_data)
            except Exception as exception:
                logger.warning(
                    "Failed to get entry price for %s on %s: %s",
                    ticker,
                    belief["record_date"],
                    exception,
                )
                price_cache[entry_cache_key] = None

        entry_price_vnd = price_cache[entry_cache_key]
        if entry_price_vnd is None:
            logger.warning(
                "Skipping belief %s/%s: missing entry price for %s on %s",
                agent_key,
                ticker,
                ticker,
                belief["record_date"],
            )
            result.skipped_missing_entry_price.append(f"{agent_key}/{ticker}")
            continue

        actual_direction = classify_actual_direction(entry_price_vnd, actual_price_vnd)
        brier_score = compute_brier_score(
            float(belief["bull_probability"]),
            float(belief["base_probability"]),
            float(belief["bear_probability"]),
            actual_direction,
        )
        direction_correct = belief["direction"] == actual_direction
        price_error_pct = None
        if belief.get("price_target_vnd") and actual_price_vnd:
            price_error_pct = round(
                (actual_price_vnd - belief["price_target_vnd"]) / actual_price_vnd * 100,
                2,
            )

        resolutions.append(
            {
                "id": belief["id"],
                "actual_direction": actual_direction,
                "actual_price_vnd": actual_price_vnd,
                "outcome_date": outcome_date,
                "brier_score": round(brier_score, 4),
                "direction_correct": direction_correct,
                "price_error_pct": price_error_pct,
            }
        )

    try:
        result.resolved = await resolve_beliefs(resolutions)
    except Exception as error:
        logger.warning("Failed to persist belief resolutions: %s", error)
        result.persist_error = True
        return result

    skipped_outcome = len(result.skipped_missing_outcome_price)
    skipped_entry = len(result.skipped_missing_entry_price)
    skipped_not_yet_mature = len(result.skipped_not_yet_mature)

    # Surface silent failures: found beliefs but resolved none.
    # Not-yet-mature beliefs are expected on holiday-adjacent days; only flag
    # when there are unresolved beliefs that *should* have been scored.
    matureable = result.unresolved_found - skipped_not_yet_mature
    if matureable > 0 and result.resolved == 0:
        sample_tickers = list({b["ticker"] for b in unresolved})[:5]
        logger.warning(
            "BELIEF SCORING GAP: found %d unresolved beliefs (%d matureable) but resolved 0. "
            "Skipped outcome=%d, entry=%d, not_yet_mature=%d. Sample tickers: %s. "
            "Check get_price_on_date() — likely returning None for all historical dates.",
            result.unresolved_found,
            matureable,
            skipped_outcome,
            skipped_entry,
            skipped_not_yet_mature,
            ", ".join(sample_tickers),
        )

    logger.info(
        "Belief scoring complete for %s: resolved=%d, found=%d, "
        "skipped_outcome=%d, skipped_entry=%d, skipped_not_yet_mature=%d",
        scan_date,
        result.resolved,
        result.unresolved_found,
        skipped_outcome,
        skipped_entry,
        skipped_not_yet_mature,
    )

    # Tombstone beliefs that aged out of the scoring window (self-healing).
    # These have outcome_date IS NULL but record_date older than max_age_days,
    # so they'll never be picked up by get_unresolved_beliefs.
    try:
        stale = await get_stale_beliefs(max_age_days=60, scan_date=scan_date)
        if stale:
            result.tombstoned = await tombstone_beliefs([belief["id"] for belief in stale])
    except Exception as error:
        logger.warning("Failed to tombstone stale beliefs: %s", error)

    return result
