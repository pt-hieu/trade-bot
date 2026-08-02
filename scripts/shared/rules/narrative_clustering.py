"""Pure-Python clustering helpers for unmatched-article coalesce (SWI-74).

Layer 0 of the narrative-dedup plan. ``narrative_tracker._coalesce_unmatched``
calls ``cluster_unmatched_embeddings`` to group similar unmatched articles
within a single scan, then ``pick_cluster_representative`` to pick the
seed article (one LLM-label round-trip per cluster instead of per article).

The opposite-sentiment split predicate is identical to
``data.narrative_matching.match_existing_narrative``'s Fix 6 gate:
both sides trusted, opposite sign, both magnitudes above
``SENTIMENT_REJECT_MIN_MAGNITUDE``. Keeping the predicate uniform
across the write-time match path and the intra-batch coalesce path
prevents Hormuz-rise / Hormuz-fall pairs from collapsing inside a
batch when they would have been rejected at write-time match.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

import numpy as np

from shared.rules.narrative_thresholds import (
    INTRABATCH_COALESCE,
    INTRABATCH_COALESCE_UNTRUSTED,
    SENTIMENT_REJECT_MIN_MAGNITUDE,
)
from shared.rules.sentiment_confidence import (
    CONFIDENCE_RANK,
    is_opposite_sentiment,
    is_trusted,
)


class ArticleEmbeddingItem(TypedDict):
    """Stable contract at the rules-layer boundary.

    Callers wrap their richer article dict to this shape so the
    clustering helpers stay pyright-checkable without depending on the
    full ``articles`` row schema.
    """

    id: str
    published_at: datetime
    sentiment_score: float | None
    sentiment_confidence: str | None
    embedding: list[float]


def _unit_vector(values: list[float]) -> np.ndarray:
    """Return the L2-normalized vector, or a zero vector when norm is zero."""
    array = np.asarray(values, dtype=np.float64)
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        return array
    return array / norm


def is_opposite_sentiment_pair(left: ArticleEmbeddingItem, right: ArticleEmbeddingItem) -> bool:
    """Apply the Fix-6 four-gate predicate to two cluster items."""
    return is_opposite_sentiment(
        left.get("sentiment_score"),
        left.get("sentiment_confidence"),
        right.get("sentiment_score"),
        right.get("sentiment_confidence"),
        magnitude_floor=SENTIMENT_REJECT_MIN_MAGNITUDE,
    )


def _greedy_cluster(
    items: list[ArticleEmbeddingItem],
    threshold: float,
) -> list[list[ArticleEmbeddingItem]]:
    """Greedy single-link clustering on cosine ≥ threshold.

    Iterate items in order; each item joins the first existing cluster
    whose seed (first member) is within threshold, else seeds a new
    cluster. Embeddings are L2-normalized once so the per-pair cosine
    collapses to a dot product.
    """
    clusters: list[list[ArticleEmbeddingItem]] = []
    seed_units: list[np.ndarray] = []
    for item in items:
        unit_vector = _unit_vector(item["embedding"])
        placed = False
        for cluster_index, seed_unit in enumerate(seed_units):
            if float(np.dot(unit_vector, seed_unit)) >= threshold:
                clusters[cluster_index].append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
            seed_units.append(unit_vector)
    return clusters


def _split_onis_opposite_sentiment_pair(
    cluster: list[ArticleEmbeddingItem],
) -> list[list[ArticleEmbeddingItem]]:
    """Split a cluster so no two members are in opposite-sentiment per Fix 6.

    Greedy: walk members; place each into the first sub-cluster where
    no existing member triggers ``is_opposite_sentiment_pair`` against it.
    """
    sub_clusters: list[list[ArticleEmbeddingItem]] = []
    for member in cluster:
        placed = False
        for sub in sub_clusters:
            if not any(is_opposite_sentiment_pair(member, existing) for existing in sub):
                sub.append(member)
                placed = True
                break
        if not placed:
            sub_clusters.append([member])
    return sub_clusters


def cluster_unmatched_embeddings(
    items: list[ArticleEmbeddingItem],
    threshold: float = INTRABATCH_COALESCE,
) -> list[list[ArticleEmbeddingItem]]:
    """Cluster unmatched articles by mutual cosine, splitting opposites.

    All-untrusted special case: when no member of a raw cluster has
    ``is_trusted(sentiment_confidence)``, re-cluster that subset at
    the tighter ``INTRABATCH_COALESCE_UNTRUSTED`` threshold. The Fix 6
    guard cannot fire on untrusted members, so the tighter embedding
    match compensates. Cross-batch respawn for genuinely-novel-wording
    untrusted articles is an accepted residual.
    """
    if not items:
        return []

    raw = _greedy_cluster(items, threshold)
    refined: list[list[ArticleEmbeddingItem]] = []
    for cluster in raw:
        if len(cluster) == 1:
            refined.append(cluster)
            continue
        any_trusted = any(is_trusted(member.get("sentiment_confidence")) for member in cluster)
        if not any_trusted:
            tightened = _greedy_cluster(cluster, INTRABATCH_COALESCE_UNTRUSTED)
            refined.extend(tightened)
            continue
        refined.extend(_split_onis_opposite_sentiment_pair(cluster))
    return refined


def pick_cluster_representative(
    cluster: list[ArticleEmbeddingItem],
) -> ArticleEmbeddingItem:
    """Pick the cluster's seed article.

    Tiebreak order:
      1. ``is_trusted(sentiment_confidence)`` DESC — trusted-first is
         load-bearing because untrusted reps seed ``avg_sentiment=None``
         which makes the new centroid invisible to the matching gate's
         ``is_trusted`` guard for the rest of the scan.
      2. ``sentiment_confidence`` DESC by ``CONFIDENCE_RANK``.
      3. ``published_at`` ASC.
      4. ``id`` ASC.

    For all-untrusted clusters the cluster has already been tightened
    by ``cluster_unmatched_embeddings`` so deterministic id-ASC fallback
    is acceptable.
    """
    if not cluster:
        raise ValueError("pick_cluster_representative: empty cluster")

    def sort_key(item: ArticleEmbeddingItem) -> tuple[int, int, datetime, str]:
        trusted_rank = 1 if is_trusted(item.get("sentiment_confidence")) else 0
        conf_rank = CONFIDENCE_RANK.get(item.get("sentiment_confidence") or "abstain", 0)
        return (-trusted_rank, -conf_rank, item["published_at"], item["id"])

    return sorted(cluster, key=sort_key)[0]
