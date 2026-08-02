"""Duplicate detection + supporting-article-id resolution helpers."""

from __future__ import annotations

# Geopolitical keyword set lives in `shared.rules.catalyst_news` so this
# module and `catalyst_classifier` consume the same vocabulary.
from shared.rules.catalyst_news import GEOPOLITICAL_KEYWORDS as _GEOPOLITICAL_KEYWORDS


def _find_duplicate_catalyst(
    event: str,
    existing_catalysts: list[dict],
    candidate_type: str = "regulatory",
) -> str | None:
    """Check if a catalyst with similar event name already exists.

    For non-geopolitical catalysts the rule stays at 0.5 word-overlap
    ratio (legacy behaviour for "FTSE Russell upgrade" vs
    "FTSE Russell mid-term review for Vietnam"). For geopolitical
    candidates we raise the bar to 0.7 AND require at least two shared
    geopolitical keywords — otherwise "Trump Hormuz blockade" and
    "US navy Hormuz blockade" merge incorrectly even though they are
    distinct incidents.
    """
    from shared.rules.catalyst_news import STOP_WORDS, normalize_text

    new_words = set(normalize_text(event).split()) - STOP_WORDS
    if len(new_words) < 2:
        return None

    is_geo = candidate_type == "geopolitical"
    threshold = 0.7 if is_geo else 0.5

    best_match: str | None = None
    best_overlap = 0

    for catalyst in existing_catalysts:
        existing_event = catalyst.get("event") or ""
        existing_words = set(normalize_text(existing_event).split()) - STOP_WORDS
        if len(existing_words) < 2:
            continue

        overlap = len(new_words & existing_words)
        min_size = min(len(new_words), len(existing_words))
        if min_size == 0:
            continue
        ratio = overlap / min_size

        if ratio < threshold or overlap <= best_overlap:
            continue

        if is_geo:
            shared_geo_keywords = (new_words & existing_words) & _GEOPOLITICAL_KEYWORDS
            if len(shared_geo_keywords) < 2:
                continue
            existing_type = catalyst.get("catalyst_type") or "regulatory"
            if existing_type != "geopolitical":
                continue

        best_overlap = overlap
        best_match = catalyst.get("catalyst_key")

    return best_match


def _resolve_supporting_ids(
    addition: dict,
    batch_article_ids: frozenset[str],
) -> list[str]:
    """Pick the specific article ids that evidence this addition.

    Prefer the agent-declared ``supporting_article_ids`` list. Fall back to
    empty — never auto-link all batch articles (the 2026-04-13 noise-vector
    bug was precisely this default).
    """
    declared = addition.get("supporting_article_ids") or []
    if not isinstance(declared, list):
        return []
    return [aid for aid in declared if aid in batch_article_ids]
