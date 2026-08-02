"""Shared seed-from-article helper for new narratives (SWI-103 R2 RCA F1).

Single source of truth for both seed sites:
- `narrative_mutations.create_narrative` (DB row inserted via `upsert_narrative`).
- `narrative_tracker._assign_all_articles` (in-memory centroids dict updated
  alongside the DB write so within-scan matching sees fresh state).

Without a shared helper the two sites diverged: the DB row carried
`avg_sentiment=NULL` for abstain articles while the in-memory mirror still
seeded the raw scalar, re-introducing the SWI-103 corruption pattern from
the matching gate's perspective.
"""

from __future__ import annotations

from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from shared.rules.sentiment_confidence import is_trusted


class CentroidInfo(TypedDict):
    """In-memory shape of a narrative centroid record.

    Mirrors the columns built into `narrative_matching.build_centroid_index`
    so producer + consumer agree on the dict keys.
    """

    embedding: NDArray[np.float64]
    article_count: int
    source_count: int
    avg_sentiment: float | None
    sentiment_confidence_roll: str | None


def build_centroid_record(
    article: dict,
    embedding: list[float],
    label_meta: dict,
) -> dict:
    """Build the full in-memory centroid + matching-gate record for a new narrative.

    Layered on top of ``seed_centroid_from_article`` so the rolling-aggregator
    fields stay in one helper, plus the matching-gate fields the
    ``build_centroid_index`` consumer expects (``narrative_key``, ``theme``,
    ``half_life_days``, ``affected_tickers``). Used wherever a narrative is
    freshly created within a scan and the centroid mirror needs hydrating.
    """
    seeded = seed_centroid_from_article(article, embedding)
    return {
        **seeded,
        "narrative_key": label_meta.get("narrative_key") or "",
        "theme": "",
        "half_life_days": label_meta.get("half_life_days") or 3,
        "affected_tickers": list(label_meta.get("affected_tickers") or []),
    }


def seed_centroid_from_article(article: dict, embedding: list[float]) -> CentroidInfo:
    """Build the in-memory centroid record for a freshly-created narrative.

    `avg_sentiment` is set ONLY when the seed article's confidence is
    trusted (high/medium); otherwise NULL — matching the DB-side semantics
    in `narrative_mutations.create_narrative` so within-scan matching gates
    behave the same as cross-scan.
    """
    conf = article.get("sentiment_confidence")
    raw_score = article.get("sentiment_score")
    avg_sentiment = float(raw_score) if (is_trusted(conf) and raw_score is not None) else None
    return {
        "embedding": np.array(embedding),
        "article_count": 1,
        "source_count": 1,
        "avg_sentiment": avg_sentiment,
        "sentiment_confidence_roll": conf,
    }
