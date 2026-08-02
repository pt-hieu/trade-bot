"""Confidence ranking helpers for article/narrative sentiment.

Pure deterministic helpers — no async, no DB, no LLM (per `shared/rules/`
purity contract). NULL/None confidence is treated identically to 'abstain'
(SWI-103 R2 RCA F6: LLM failures write NULL on both score and confidence).

CONFIDENCE_RANK fixes a total order so `max_confidence` can pick the most
trusted contributor across a narrative's article set.
"""

from __future__ import annotations

CONFIDENCE_RANK: dict[str, int] = {"abstain": 0, "low": 1, "medium": 2, "high": 3}
TRUSTED: frozenset[str] = frozenset({"high", "medium"})


def is_trusted(conf: str | None) -> bool:
    """True iff confidence is 'high' or 'medium'. None/NULL → False (treated as abstain)."""
    if conf is None:
        return False
    return conf in TRUSTED


def is_opposite_sentiment(
    left_score: float | None,
    left_confidence: str | None,
    right_score: float | None,
    right_confidence: str | None,
    *,
    magnitude_floor: float,
) -> bool:
    """Fix 6 four-gate predicate: are these two sentiments confidently opposed?

    Both sides must be trusted, opposite-signed, and above ``magnitude_floor``.
    Single source of truth — ``match_existing_narrative`` and the intra-batch
    coalesce splitter both call this to keep behavior identical.
    """
    if not is_trusted(left_confidence) or not is_trusted(right_confidence):
        return False
    if left_score is None or right_score is None:
        return False
    left_value = float(left_score)
    right_value = float(right_score)
    if not ((left_value > 0 > right_value) or (left_value < 0 < right_value)):
        return False
    return not (abs(left_value) <= magnitude_floor or abs(right_value) <= magnitude_floor)


def max_confidence(confs: list[str | None]) -> str | None:
    """Return the highest-rank confidence in the list, or None when all are None.

    Used to roll narrative-level `sentiment_confidence_roll` from contributor
    article confidences (max-contributor strategy).
    """
    valid = [c for c in confs if c is not None]
    if not valid:
        return None
    return max(valid, key=lambda c: CONFIDENCE_RANK.get(c, 0))
