"""Layer-5 audit wrapper around ``validate_structured_recommendations``.

Phase A wiring (SWI-171). The recommendation validator stays
side-effect-free per /challenge round-1 finding 6 — this module is the
seam where the validator's pass/drop verdict on each BUY rec is
re-stamped onto the matching ``pre_gate_candidates`` audit row that
``picks.py`` already wrote.

In Phase A this is purely additive: the validator's behavior is
unchanged. Only the audit row's ``gated_by`` enum may flip from
``passed`` (picks.py wrote that after layers 1-4) to
``validator_max_picks`` (max_picks cull), ``rr_floor`` (R:R floor
re-check), or ``setup_invalid`` (geometry / NULL price drops).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pipeline.recommendation_builder import BUY_ACTIONS

if TYPE_CHECKING:
    from eval.score_recorder import ScoreRecorder
    from shared.rules.scoring import GatedBy, ScoringPhase

logger = logging.getLogger(__name__)


def _classify_validator_warning(reason: str) -> GatedBy:
    """Map a validator warning string to the matching ``gated_by`` enum.

    The validator emits warnings as free text (see
    ``recommendation_validator.py`` Pass 3). We pattern-match the prefix
    so the audit row records the closest semantic match. Default is
    ``rr_floor`` because the most common drop is the R:R floor check.
    """
    upper = reason.upper()
    if "MAX PICKS" in upper:
        return "validator_max_picks"
    if "R:R FLOOR" in upper or "R:R " in upper:
        return "rr_floor"
    if (
        "ZERO R:R" in upper
        or "GEOMETRY" in upper
        or "NO ENTRY PRICE" in upper
        or "NO STOP PRICE" in upper
        or "NO TARGET PRICE" in upper
    ):
        return "setup_invalid"
    if "MODE ENFORCEMENT" in upper or "REALLOCATION" in upper:
        return "validator_max_picks"
    return "rr_floor"


async def audit_validator_outcome(
    *,
    recorder: ScoreRecorder | None,
    phase: ScoringPhase,
    input_recs: Sequence[dict],
    output_recs: Sequence[dict],
    warnings: Sequence[str],
) -> None:
    """Re-stamp ``pre_gate_candidates`` rows for each BUY rec the validator saw.

    Side-effect-free wrt the recommendation flow — only writes audit
    rows. Fail-open: any recorder error is logged and swallowed.

    Args:
        recorder: Per-run audit recorder. ``None`` skips the wrapper
            (caller decided audit-mode is off).
        phase: ``'morning'`` | ``'midday'`` | ``'retro'``.
        input_recs: Recs the validator received.
        output_recs: Validator's ``validated`` list.
        warnings: Validator's ``warnings`` list (free text).
    """
    if recorder is None:
        return

    output_buy_tickers = {
        (r.get("ticker") or "").upper() for r in output_recs if r.get("action") in BUY_ACTIONS
    }
    input_buy_tickers = {
        (r.get("ticker") or "").upper() for r in input_recs if r.get("action") in BUY_ACTIONS
    }
    dropped = input_buy_tickers - output_buy_tickers
    survived = input_buy_tickers & output_buy_tickers

    # Build a ticker → reason index from the warnings list. Warnings
    # always include the ticker as the first non-prefix token, so a
    # simple substring scan suffices.
    warning_by_ticker: dict[str, str] = {}
    for warning in warnings:
        for ticker in dropped:
            if ticker in warning and ticker not in warning_by_ticker:
                warning_by_ticker[ticker] = warning

    # Survivors first — re-stamp 'passed' (idempotent if picks.py
    # already wrote it; meaningful when validator passed a rec the
    # picks loop didn't write, e.g. position_alerts source).
    for ticker in sorted(survived):
        await recorder.update_outcome(
            ticker=ticker,
            phase=phase,
            gated_by="passed",
            gate_reason=None,
        )

    # Drops — best-effort classification from the warning text.
    for ticker in sorted(dropped):
        reason = warning_by_ticker.get(ticker, "validator_drop")
        gated_by = _classify_validator_warning(reason)
        wrote = await recorder.update_outcome(
            ticker=ticker,
            phase=phase,
            gated_by=gated_by,
            gate_reason=reason,
        )
        if not wrote:
            # No prior side-store entry — typically means the rec came
            # from a non-picks source (position_alerts, retro carry-over).
            # Phase A: log so retro audit can spot the gap; Phase B may
            # need a synthetic row.
            logger.info(
                "score_audit: validator drop for %s phase=%s (no prior pre_gate row)",
                ticker,
                phase,
            )


__all__ = ["audit_validator_outcome"]
