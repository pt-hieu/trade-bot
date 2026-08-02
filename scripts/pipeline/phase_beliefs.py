"""Phase 2.5: Deterministic belief post-processing.

After LLM-produced beliefs are persisted, this phase applies:
1. Base rate anchoring (10% pull toward Vietnamese market base rates)
2. Conviction-weighted aggregation (accuracy-factor weighting, Brier exclusion)
3. Persistence as ensemble_type="deterministic"
"""

import asyncio
import logging
from collections import defaultdict
from datetime import date

from agents.belief_aggregation import (
    anchor_aggregated_belief,
    weighted_aggregate_beliefs,
)
from agents.belief_aggregation._constants import (
    current_brier_down_weight_threshold,
    set_runtime_base_rates,
)
from agents.belief_models import decay_belief_conviction
from shared.neon import get_all_belief_accuracy, insert_agent_beliefs
from shared.neon.belief_queries import compute_empirical_base_rates
from shared.observability import log_warn

logger = logging.getLogger(__name__)


async def post_process_beliefs(
    scan_date: date,
    sector_beliefs: list[dict],
    position_beliefs: list[dict],
) -> dict:
    """Deterministic post-processing: base rate anchoring + accuracy-weighted aggregation.

    Takes raw LLM-produced beliefs, applies deterministic corrections,
    persists as ensemble_type="deterministic" for downstream consumption.

    Returns:
        {"sector": [...], "positions": [...]} — aggregated beliefs by ticker.
    """
    all_beliefs = sector_beliefs + position_beliefs
    if not all_beliefs:
        logger.info("No beliefs to post-process")
        return {"sector": [], "positions": []}

    # Exclude LLM aggregator beliefs — they already incorporate sub-agents,
    # including them would double-count their views in the deterministic average.
    # Single source of truth: shared/rules/belief_calibration_exemption.py reads
    # `ensemble_role: aggregator` from agent YAML so adding a new aggregator
    # only requires the config field (Phase 2 §2.5).
    from shared.rules.belief_calibration_exemption import is_aggregator_double_counter

    filtered_beliefs = [
        {**b} for b in all_beliefs if not is_aggregator_double_counter(b.get("agent_key") or "")
    ]

    # Staleness decay before aggregation — stale beliefs get reduced weight
    for belief in filtered_beliefs:
        days_held = belief.get("days_held") or 1
        original_conviction = float(belief.get("conviction") or 0.5)
        belief["conviction"] = decay_belief_conviction(original_conviction, days_held)

    # Concurrent: calibration stats, dynamic base rates, Platt fitting (all independent)
    calibration_stats: dict[str, dict] = {}
    empirical_rates: dict[str, float] | None = None

    async def _fetch_calibration() -> dict[str, dict]:
        try:
            return await get_all_belief_accuracy(days_back=30)
        except Exception as error:
            logger.warning("Failed to fetch belief accuracy stats: %s", error)
            return {}

    async def _fetch_base_rates() -> dict[str, float] | None:
        try:
            rates = await compute_empirical_base_rates(days_back=90)
            logger.info("Dynamic base rates (90d): %s", rates)
            return rates
        except ValueError as rate_error:
            logger.warning("Failed to compute dynamic base rates: %s — using fallback", rate_error)
            return None

    calibration_stats, empirical_rates = await asyncio.gather(
        _fetch_calibration(),
        _fetch_base_rates(),
    )

    # Rebind the Brier down-weight threshold to the empirical-rates-derived
    # uninformed-forecaster anchor for this scan. Without this, the threshold
    # stays anchored to FALLBACK_BASE_RATES (module-load default) and the
    # graduated sigmoid reduction never activates against agents whose Brier
    # sits just above the empirical anchor (SWI: pipeline review 2026-05-07).
    if empirical_rates:
        set_runtime_base_rates(empirical_rates)
        logger.info(
            "Brier down-weight threshold rebound to %.4f using empirical base rates",
            current_brier_down_weight_threshold(),
        )

    # NOTE: base rate anchoring is applied AFTER aggregation, not before.
    # Anchoring sub-agent inputs destructively pulls bull_probability below
    # DISSENT_PRESERVATION_BULL_FLOOR (0.50) and silently no-ops dissent
    # preservation.
    beliefs_by_ticker: dict[str, list[dict]] = defaultdict(list)
    for belief in filtered_beliefs:
        beliefs_by_ticker[belief["ticker"]].append(belief)

    deterministic_sector = []
    deterministic_positions = []

    for ticker, ticker_beliefs in beliefs_by_ticker.items():
        aggregated = weighted_aggregate_beliefs(ticker_beliefs, calibration_stats)
        if not aggregated:
            continue

        # Anchor AFTER aggregation so dissent preservation reads raw sub-agent
        # values; then nudge the aggregated distribution 10% toward base rates.
        aggregated = anchor_aggregated_belief(aggregated, base_rates=empirical_rates)

        # Compute conviction as max of sub-agent convictions (capped at 0.9)
        max_conviction = max(
            (float(b.get("conviction") or 0.5) for b in ticker_beliefs),
            default=0.5,
        )
        aggregated_conviction = min(0.9, max_conviction)

        # Pick narrative from highest-conviction sub-agent matching aggregated direction.
        # Single pass: track best matching and best fallback simultaneously.
        direction_target = aggregated["direction"]
        best_matching = None
        best_matching_conviction = 0.0
        best_matching_no_target = None
        best_matching_no_target_conviction = 0.0
        best_fallback = None
        best_fallback_conviction = 0.0
        for belief in ticker_beliefs:
            belief_conviction = float(belief.get("conviction") or 0)
            price_target = belief.get("price_target_vnd")
            has_valid_target = bool(price_target and price_target > 0)
            if belief.get("direction") == direction_target:
                if has_valid_target:
                    if belief_conviction > best_matching_conviction:
                        best_matching = belief
                        best_matching_conviction = belief_conviction
                else:
                    if belief_conviction > best_matching_no_target_conviction:
                        best_matching_no_target = belief
                        best_matching_no_target_conviction = belief_conviction
            if belief_conviction > best_fallback_conviction:
                best_fallback = belief
                best_fallback_conviction = belief_conviction
        best_belief = best_matching or best_matching_no_target or best_fallback
        if best_belief is None:
            logger.warning("No best belief for %s (all convictions 0) — skipping", ticker)
            continue
        narrative = best_belief.get("belief_narrative") or ""

        belief_record = {
            "ticker": ticker,
            "agent_key": "deterministic_aggregator",
            "belief_narrative": narrative,
            "direction": aggregated["direction"],
            "bull_probability": aggregated["bull_probability"],
            "base_probability": aggregated["base_probability"],
            "bear_probability": aggregated["bear_probability"],
            "price_target_vnd": best_belief.get("price_target_vnd") or None,
            "timeframe_days": best_belief.get("timeframe_days") or 5,
            "conviction": aggregated_conviction,
            "belief_status": "NEW",
        }

        # Route to sector or positions based on source ensemble
        ensemble_type = best_belief.get("ensemble_type") or _infer_ensemble(
            best_belief.get("agent_key", "")
        )
        if ensemble_type == "positions":
            deterministic_positions.append(belief_record)
        else:
            deterministic_sector.append(belief_record)

    # Persist deterministic beliefs (each wrapped individually so one failure doesn't skip the other)
    if deterministic_sector:
        try:
            await insert_agent_beliefs(scan_date, deterministic_sector, "deterministic_sector")
        except Exception as error:
            logger.warning("Failed to insert deterministic sector beliefs: %s", error)
            log_warn(
                "DETERMINISTIC_BELIEF_INSERT_FAILED",
                ensemble="deterministic_sector",
                scan_date=str(scan_date),
                error=str(error),
            )

    if deterministic_positions:
        try:
            await insert_agent_beliefs(
                scan_date, deterministic_positions, "deterministic_positions"
            )
        except Exception as error:
            logger.warning("Failed to insert deterministic position beliefs: %s", error)
            log_warn(
                "DETERMINISTIC_BELIEF_INSERT_FAILED",
                ensemble="deterministic_positions",
                scan_date=str(scan_date),
                error=str(error),
            )

    total = len(deterministic_sector) + len(deterministic_positions)
    logger.info(
        "Deterministic aggregation: %d beliefs (%d sector, %d positions)",
        total,
        len(deterministic_sector),
        len(deterministic_positions),
    )

    # Soft guard against flat-output collapse (MON-2026-04-13-003). If the
    # aggregated bull distribution across tickers has near-zero variance AND
    # any sub-agent input had a non-NEUTRAL direction, something has gone
    # wrong (dissent preservation silently no-oped, calibration wiped every
    # weight, etc.). Warn without crashing.
    _warn_if_flat_aggregator_output(
        deterministic_sector + deterministic_positions, filtered_beliefs
    )

    return {
        "sector": deterministic_sector,
        "positions": deterministic_positions,
        "calibration_stats": calibration_stats,
    }


def _infer_ensemble(agent_key: str) -> str:
    """Infer ensemble type from agent_key prefix."""
    if agent_key.startswith("positions"):
        return "positions"
    return "sector"


def _warn_if_flat_aggregator_output(
    aggregated_records: list[dict],
    sub_agent_beliefs: list[dict],
) -> None:
    """Log a warning when deterministic_aggregator collapses a diverse
    sub-agent signal into a uniform NEUTRAL output.

    Signal criteria:
    - >= 5 aggregated records (ignore tiny samples).
    - stddev(bull_probability) across the batch < 0.02 (flat).
    - At least one sub-agent input had a non-NEUTRAL direction.
    """
    if len(aggregated_records) < 5:
        return
    bulls = [float(r.get("bull_probability") or 0.0) for r in aggregated_records]
    mean = sum(bulls) / len(bulls)
    variance = sum((b - mean) ** 2 for b in bulls) / len(bulls)
    stddev = variance**0.5
    if stddev >= 0.02:
        return
    has_directional_input = any(
        (b.get("direction") or "NEUTRAL") != "NEUTRAL" for b in sub_agent_beliefs
    )
    if not has_directional_input:
        return
    logger.warning(
        "deterministic_aggregator flat output: stddev=%.4f across %d tickers "
        "despite non-NEUTRAL sub-agent signals — check dissent preservation "
        "and calibration weight reduction",
        stddev,
        len(aggregated_records),
    )
