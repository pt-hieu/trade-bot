"""Deterministic mapping from sub-agent views / beliefs to BUY/WATCH/WAIT/AVOID signals.

Single source of truth used by:
- sector.py timeout fallback (derive signals from sub-agent views)
- phase_recommendations coverage gap reconciliation (from deterministic beliefs)

Pure Python, no async / DB / LLM. Keeps math out of agent prompts per
CLAUDE.md "Deterministic calculations only in Python".
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypedDict

from shared.rules.audit_tags import DERIVED_FROM_BELIEFS
from shared.text_utils import split_first_sentence

Signal = Literal["BUY", "WATCH", "WAIT", "AVOID"]

# Rank used for the tiebreak rule: "BULLISH-leaning > NEUTRAL > BEARISH-leaning".
_SIGNAL_RANK: dict[str, int] = {
    "BUY": 4,
    "WATCH": 3,
    "WAIT": 2,
    "AVOID": 1,
}


class _ViewLike(TypedDict, total=False):
    """Structural subset of SectorAnalystView needed by the mapper."""

    ticker: str
    signal: Signal
    confidence: int
    reasoning: str


def derive_signal_from_views(views: Sequence[object]) -> tuple[Signal, str]:
    """Per-ticker majority vote across sub-agent views.

    Args:
        views: list of SectorAnalystView-shaped objects (or dicts) for ONE ticker.
               Each must expose `.signal` (Signal), `.confidence` (int 1-10),
               and `.reasoning` (str).

    Returns:
        (signal, note) tuple. `note` contains a short prefixed excerpt from the
        highest-confidence matching sub-agent's reasoning, prefixed with
        `[DERIVED_FROM_BELIEFS]` so reviewers can audit.

    Tiebreak rule: when the vote counts tie, pick the bullish-leaning signal
    (BUY > WATCH > WAIT > AVOID via _SIGNAL_RANK).
    """
    if not views:
        return "WAIT", f"{DERIVED_FROM_BELIEFS} No sub-agent views available"

    # Count votes per signal.
    vote_counts: dict[str, int] = {}
    for view in views:
        signal = _view_signal(view)
        vote_counts[signal] = vote_counts.get(signal, 0) + 1

    # Majority pick with tiebreak: max on (count, rank).
    winning_signal = max(
        vote_counts.items(),
        key=lambda kv: (kv[1], _SIGNAL_RANK.get(kv[0], 0)),
    )[0]

    # Find the highest-confidence matching view for the note excerpt.
    matching_views = [v for v in views if _view_signal(v) == winning_signal]
    best_view = max(matching_views, key=_view_confidence, default=None)
    if best_view is None:
        excerpt = "committee view"
    else:
        reasoning = _view_reasoning(best_view)
        excerpt = split_first_sentence(reasoning, max_len=120) or "committee view"

    note = f"{DERIVED_FROM_BELIEFS} {excerpt}"
    return winning_signal, note  # type: ignore[return-value]


def derive_signal_from_belief(belief: dict) -> Signal:
    """Deterministic direction → signal mapping for an aggregated belief dict.

    Used by T05 (coverage-gap reconciliation from deterministic beliefs).
    The mapping intentionally stays conservative — BULLISH → WATCH (not BUY)
    because a missing-from-recommendations ticker has not passed the pipeline's
    BUY gates and we do not want to retroactively promote it.

    Args:
        belief: aggregated belief dict with `direction` and probability fields.
    """
    direction = (belief or {}).get("direction", "NEUTRAL")
    if direction == "BULLISH":
        return "WATCH"
    if direction == "BEARISH":
        return "AVOID"
    return "WAIT"


def _view_signal(view: object) -> str:
    if isinstance(view, dict):
        return view.get("signal", "WAIT")
    return getattr(view, "signal", "WAIT")


def _view_confidence(view: object) -> int:
    raw = view.get("confidence", 0) if isinstance(view, dict) else getattr(view, "confidence", 0)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _view_reasoning(view: object) -> str:
    if isinstance(view, dict):
        return view.get("reasoning", "") or ""
    return getattr(view, "reasoning", "") or ""
