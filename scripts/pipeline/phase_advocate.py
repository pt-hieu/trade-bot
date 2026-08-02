"""Phase 3.5: Advocate Reviews — bull and bear stress-testing of picks."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import TYPE_CHECKING

from shared.observability import log_warn, span
from shared.rules.exit_strategy import format_rr_display, read_rr, rr_sort_weight

if TYPE_CHECKING:
    from .types import DeterministicBeliefs

logger = logging.getLogger(__name__)

# Advocate verdict values (match Literal type in advocate_models.py)
VERDICT_AGREE = "AGREE"
VERDICT_CHALLENGE = "CHALLENGE"
VERDICT_MIXED = "MIXED"

# Gate mode values (controlled by ADVOCATE_GATE_MODE env var)
GATE_MODE_AUDIT = "audit"
GATE_MODE_ENFORCE = "enforce"

# Confidence threshold for bear CHALLENGE to gate a pick.
# Start at 0.7; calibrate after observing distribution in audit mode.
BEAR_CHALLENGE_CONFIDENCE_THRESHOLD = 0.7

# Gate never removes ALL picks — at least this many survive.
MIN_SURVIVING_PICKS = 1


async def run_advocate_reviews(
    pre_computed_picks: list[dict],
    deterministic_beliefs: DeterministicBeliefs,
    phase1_context: str,
    scan_date: date,
) -> dict[str, list[dict]]:
    """Run bull and bear advocate reviewers in parallel on pick candidates.

    Args:
        pre_computed_picks: Pre-validated picks with R:R from real levels
        deterministic_beliefs: Post-processed beliefs keyed by source
        phase1_context: Formatted market regime + macro context string
        scan_date: Trading date being analyzed

    Returns:
        {"bull": [review_dicts], "bear": [review_dicts]}
        Empty lists on failure (non-fatal).
    """
    if not pre_computed_picks:
        logger.info("No picks to review — skipping advocate phase")
        return {"bull": [], "bear": []}

    from agents.advocate_reviewer import (
        BEAR_AGENT_KEY,
        BULL_AGENT_KEY,
        run_bear_reviewer,
        run_bull_reviewer,
    )

    print(f"\n  Advocate review: {len(pre_computed_picks)} picks", flush=True)

    # Pre-fetch accuracy stats once (avoids duplicate DB query from parallel reviewers)
    accuracy_by_agent: dict[str, str] = {}
    try:
        from pipeline.outcome_reinforcement import build_accuracy_contexts_batch

        accuracy_by_agent = await build_accuracy_contexts_batch([BULL_AGENT_KEY, BEAR_AGENT_KEY])
    except Exception as accuracy_error:
        logger.debug("Accuracy context unavailable: %s", accuracy_error)

    with span("advocate_reviews", pick_count=len(pre_computed_picks)):
        try:
            bull_report, bear_report = await asyncio.wait_for(
                asyncio.gather(
                    run_bull_reviewer(
                        pre_computed_picks,
                        deterministic_beliefs,
                        phase1_context,
                        scan_date,
                        accuracy_prefix=accuracy_by_agent.get(BULL_AGENT_KEY, ""),
                    ),
                    run_bear_reviewer(
                        pre_computed_picks,
                        deterministic_beliefs,
                        phase1_context,
                        scan_date,
                        accuracy_prefix=accuracy_by_agent.get(BEAR_AGENT_KEY, ""),
                    ),
                ),
                # Fits latency-triage per-agent budget (3 * 75s primary +
                # 120s fallback = 345s) with parallelism headroom (SWI-318).
                timeout=900,
            )

            bull_reviews = [review.model_dump() for review in bull_report.reviews]
            bear_reviews = [review.model_dump() for review in bear_report.reviews]

            print(
                f"  Bull: {len(bull_reviews)} reviews | Bear: {len(bear_reviews)} reviews",
                flush=True,
            )

            result = {"bull": bull_reviews, "bear": bear_reviews}

            # Persist for audit trail (non-fatal)
            try:
                from shared.neon.advocate_reviews import insert_advocate_reviews

                persisted = await insert_advocate_reviews(scan_date, result)
                if persisted:
                    print(f"  Persisted {persisted} advocate reviews to DB", flush=True)
            except Exception as persist_error:
                logger.warning("Advocate review persistence failed (non-fatal): %s", persist_error)
                log_warn(
                    "ADVOCATE_REVIEW_PERSIST_FAILED",
                    scope="phase_advocate",
                    scan_date=str(scan_date),
                    error=str(persist_error),
                )

            return result

        except TimeoutError:
            logger.warning(
                "Advocate reviews timed out after 120s for %d picks",
                len(pre_computed_picks),
            )
            return {"bull": [], "bear": []}
        except Exception as e:
            logger.warning(
                "Advocate reviews failed for %d picks: %s",
                len(pre_computed_picks),
                e,
            )
            return {"bull": [], "bear": []}


def apply_advocate_gate(
    pre_computed_picks: list[dict],
    advocate_reviews: dict[str, list[dict]],
    position_alerts: dict | None = None,
    trading_mode: str = "NORMAL",
) -> tuple[list[dict], list[dict]]:
    """Deterministic gate: filter picks based on advocate verdicts.

    Args:
        pre_computed_picks: Pre-validated pick candidates
        advocate_reviews: {"bull": [review_dicts], "bear": [review_dicts]}
        position_alerts: Position alerts dict (for REALLOCATION safety)
        trading_mode: Current trading mode (NORMAL/LOW_CASH/REALLOCATION)

    Returns:
        (filtered_picks, gated_tickers) — gated_tickers includes reason + arguments
        for synthesis SKIP THESE context.

    Gate mode controlled by ADVOCATE_GATE_MODE env var:
        "audit" (default): log decisions, return all picks unchanged
        "enforce": actually remove gated picks
    """
    gate_mode = os.environ.get("ADVOCATE_GATE_MODE", GATE_MODE_AUDIT)
    bull_reviews = advocate_reviews.get("bull") or []
    bear_reviews = advocate_reviews.get("bear") or []

    if not bull_reviews and not bear_reviews:
        logger.warning("Advocate gate bypassed: empty reviews (timeout or failure)")
        return list(pre_computed_picks), []

    # Index reviews by ticker
    bull_by_ticker = {review.get("ticker"): review for review in bull_reviews}
    bear_by_ticker = {review.get("ticker"): review for review in bear_reviews}

    # Build set of EXIT tickers for REALLOCATION safety
    exit_tickers: set[str] = set()
    if trading_mode == "REALLOCATION" and position_alerts:
        for alert in position_alerts.get("alerts") or []:
            if alert.get("action") == "EXIT":
                exit_tickers.add(alert.get("ticker", ""))

    surviving_picks: list[dict] = []
    gated_tickers: list[dict] = []

    for pick in pre_computed_picks:
        ticker = pick.get("ticker", "?")
        bear_review = bear_by_ticker.get(ticker)
        bull_review = bull_by_ticker.get(ticker)

        gate_decision = _evaluate_gate_decision(bear_review, bull_review)

        # REALLOCATION safety: never gate a pick that has a matching EXIT
        if gate_decision["should_gate"] and ticker in exit_tickers:
            logger.info("Advocate gate: %s REALLOCATION-protected (has matching EXIT)", ticker)
            gate_decision["should_gate"] = False
            pick = {**pick, "advocate_warning": True}

        if gate_decision["should_gate"]:
            gated_entry = {
                "ticker": ticker,
                "gated_by": gate_decision["reason"],
                "bear_confidence": gate_decision.get("bear_confidence", 0),
                "bear_arguments": gate_decision.get("bear_arguments", []),
                "sector": pick.get("sector", ""),
                # read_rr returns None for trailing exits — preserved here so
                # the rescue comparator below can rank trailing as max-bound.
                "risk_reward": read_rr(pick),
            }
            gated_tickers.append(gated_entry)
            print(
                f"  [Advocate Gate] {ticker}: GATED — {gate_decision['reason']} "
                f"(bear conf={gate_decision.get('bear_confidence', 0):.2f})",
                flush=True,
            )
        elif gate_decision.get("warn"):
            pick = {**pick, "advocate_warning": True}
            surviving_picks.append(pick)
            print(
                f"  [Advocate Gate] {ticker}: WARNING — {gate_decision['reason']}",
                flush=True,
            )
        else:
            surviving_picks.append(pick)

    # Snapshot gated list before rescue (for audit mode reporting)
    all_gated_tickers = list(gated_tickers)

    # min_surviving_picks floor: if gate would remove ALL, keep the best one.
    # Trailing exits (risk_reward=None) rank as max-bound — they have unbounded
    # upside and should be rescued preferentially over fixed-target picks.
    if not surviving_picks and gated_tickers:
        best_gated = max(gated_tickers, key=lambda g: rr_sort_weight(g, descending=False))
        best_ticker = best_gated["ticker"]
        rescued_pick = next((p for p in pre_computed_picks if p.get("ticker") == best_ticker), None)
        if rescued_pick:
            surviving_picks.append({**rescued_pick, "advocate_warning": True})
            gated_tickers = [g for g in gated_tickers if g["ticker"] != best_ticker]
            logger.warning(
                "Advocate gate: all picks would be gated — rescued %s (best R:R %s)",
                best_ticker,
                format_rr_display(best_gated.get("risk_reward")),
            )

    if gate_mode == GATE_MODE_AUDIT:
        # Audit mode: log decisions but return all picks unchanged
        # Use pre-rescue gated list so synthesis gets full context
        if all_gated_tickers:
            logger.info(
                "Advocate gate AUDIT: would gate %d picks: %s",
                len(all_gated_tickers),
                [g["ticker"] for g in all_gated_tickers],
            )
        return list(pre_computed_picks), all_gated_tickers

    # Enforce mode: return filtered list (with rescue applied)
    return surviving_picks, gated_tickers


def _evaluate_gate_decision(
    bear_review: dict | None,
    bull_review: dict | None,
) -> dict:
    """Evaluate whether a pick should be gated based on advocate verdicts.

    Returns dict with keys: should_gate, warn, reason, bear_confidence, bear_arguments.
    """
    bear_verdict = (bear_review.get("verdict") if bear_review else "") or ""
    bull_verdict = (bull_review.get("verdict") if bull_review else "") or ""
    bear_confidence = (bear_review.get("confidence") if bear_review else 0) or 0
    bear_arguments = (bear_review.get("key_arguments") if bear_review else []) or []

    result = {
        "should_gate": False,
        "warn": False,
        "reason": "",
        "bear_confidence": bear_confidence,
        "bear_arguments": bear_arguments,
    }

    # Both CHALLENGE — strongest gate signal
    if bear_verdict == VERDICT_CHALLENGE and bull_verdict == VERDICT_CHALLENGE:
        result["should_gate"] = True
        result["reason"] = "both_reviewers_challenge"
        return result

    # Bear CHALLENGE with high confidence, bull AGREE
    if (
        bear_verdict == VERDICT_CHALLENGE
        and bear_confidence > BEAR_CHALLENGE_CONFIDENCE_THRESHOLD
        and bull_verdict == VERDICT_AGREE
    ):
        result["should_gate"] = True
        result["reason"] = "bear_high_confidence_challenge"
        return result

    # Bear CHALLENGE with low confidence, or bear CHALLENGE + bull MIXED → warning only
    if bear_verdict == VERDICT_CHALLENGE:
        result["warn"] = True
        if bull_verdict == VERDICT_MIXED:
            result["reason"] = "bear_challenge_bull_mixed"
        else:
            result["reason"] = "bear_low_confidence_challenge"
        return result

    return result
