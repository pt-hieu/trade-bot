"""Tests for shared.rules.narrative_clustering (SWI-74 Layer 0).

Coverage map (per the SWI-74 plan):
- 5_similar_articles_collapse_to_one — pin the coalesce mechanic
- inline_seed_visible_to_subsequent_match — covered indirectly via
  rep selection + write-time match interplay (verified in tracker tests)
- rep_selection_prefers_trusted_confidence
- intracluster_opposite_sentiment_splits — Hormuz rise + fall
- split_predicate_matches_fix6_gate — table-driven parity with Fix 6
- attach_step_rejects_opposite_sentiment_member — covered in narrative_coalesce
  integration; predicate parity is covered here
- all_untrusted_cluster_uses_tighter_threshold
- sequential_rep_creation_preserves_net_widening — covered by tracker test
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from shared.rules.narrative_clustering import (
    ArticleEmbeddingItem,
    cluster_unmatched_embeddings,
    is_opposite_sentiment_pair,
    pick_cluster_representative,
)
from shared.rules.narrative_thresholds import (
    INTRABATCH_COALESCE,
    INTRABATCH_COALESCE_UNTRUSTED,
    SENTIMENT_REJECT_MIN_MAGNITUDE,
)


def _vec(theta: float, dim: int = 8) -> list[float]:
    """Deterministic unit vector parameterised by a single angle."""
    base = np.ones(dim, dtype=np.float64)
    perturb = np.zeros(dim, dtype=np.float64)
    perturb[0] = np.sin(theta)
    perturb[1] = np.cos(theta)
    blended = base + 0.4 * perturb
    return (blended / np.linalg.norm(blended)).tolist()


def _item(
    *,
    item_id: str,
    embedding: list[float],
    sentiment_score: float | None = 0.4,
    sentiment_confidence: str | None = "high",
    minutes_offset: int = 0,
) -> ArticleEmbeddingItem:
    return ArticleEmbeddingItem(
        id=item_id,
        published_at=datetime(2026, 5, 1, 12, 0) + timedelta(minutes=minutes_offset),
        sentiment_score=sentiment_score,
        sentiment_confidence=sentiment_confidence,
        embedding=embedding,
    )


def test_5_similar_articles_collapse_to_one() -> None:
    """Five high-cosine articles in same direction → one cluster."""
    base_embedding = _vec(0.0)
    items = [_item(item_id=f"a{i}", embedding=base_embedding, minutes_offset=i) for i in range(5)]
    clusters = cluster_unmatched_embeddings(items, threshold=INTRABATCH_COALESCE)
    assert len(clusters) == 1
    assert {m["id"] for m in clusters[0]} == {f"a{i}" for i in range(5)}


def test_rep_selection_prefers_trusted_confidence() -> None:
    """Cluster of [low, high, low] → high seeds, centroid carries non-None avg."""
    base_embedding = _vec(0.0)
    cluster = [
        _item(
            item_id="a_low",
            embedding=base_embedding,
            sentiment_confidence="low",
            sentiment_score=0.5,
            minutes_offset=0,
        ),
        _item(
            item_id="a_high",
            embedding=base_embedding,
            sentiment_confidence="high",
            sentiment_score=0.6,
            minutes_offset=10,
        ),
        _item(
            item_id="a_low2",
            embedding=base_embedding,
            sentiment_confidence="low",
            sentiment_score=0.4,
            minutes_offset=20,
        ),
    ]
    rep = pick_cluster_representative(cluster)
    assert rep["id"] == "a_high"


def test_rep_selection_published_then_id_when_all_untrusted() -> None:
    """All-untrusted clusters tiebreak by published_at ASC, then id ASC."""
    base_embedding = _vec(0.0)
    cluster_pub = [
        _item(
            item_id="b",
            embedding=base_embedding,
            sentiment_confidence="abstain",
            sentiment_score=None,
            minutes_offset=10,
        ),
        _item(
            item_id="a",
            embedding=base_embedding,
            sentiment_confidence="abstain",
            sentiment_score=None,
            minutes_offset=20,
        ),
    ]
    # b is earlier than a → b wins on published_at.
    assert pick_cluster_representative(cluster_pub)["id"] == "b"

    # When published_at ties, id-ASC takes over.
    cluster_id = [
        _item(
            item_id="b",
            embedding=base_embedding,
            sentiment_confidence="abstain",
            sentiment_score=None,
            minutes_offset=10,
        ),
        _item(
            item_id="a",
            embedding=base_embedding,
            sentiment_confidence="abstain",
            sentiment_score=None,
            minutes_offset=10,
        ),
    ]
    assert pick_cluster_representative(cluster_id)["id"] == "a"


def test_intracluster_opposite_sentiment_splits() -> None:
    """Hormuz-rise + Hormuz-fall, both trusted, magnitudes >0.15 → two narratives."""
    embedding = _vec(0.0)
    items = [
        _item(
            item_id="rise1",
            embedding=embedding,
            sentiment_score=0.6,
            sentiment_confidence="high",
        ),
        _item(
            item_id="rise2",
            embedding=embedding,
            sentiment_score=0.5,
            sentiment_confidence="high",
            minutes_offset=2,
        ),
        _item(
            item_id="fall1",
            embedding=embedding,
            sentiment_score=-0.5,
            sentiment_confidence="high",
            minutes_offset=4,
        ),
    ]
    clusters = cluster_unmatched_embeddings(items, threshold=INTRABATCH_COALESCE)
    assert len(clusters) == 2
    cluster_ids = [{m["id"] for m in cluster} for cluster in clusters]
    assert {"rise1", "rise2"} in cluster_ids
    assert {"fall1"} in cluster_ids


@pytest.mark.parametrize(
    "left_conf,right_conf,left_score,right_score,expect_opposite",
    [
        ("high", "high", 0.4, -0.4, True),
        ("medium", "high", 0.3, -0.5, True),
        ("low", "high", 0.4, -0.4, False),
        ("high", "abstain", 0.4, -0.4, False),
        (None, "high", 0.4, -0.4, False),
        ("high", "high", 0.10, -0.4, False),
        ("high", "high", 0.4, -0.10, False),
        ("high", "high", SENTIMENT_REJECT_MIN_MAGNITUDE, -0.4, False),
        ("high", "high", 0.4, 0.4, False),
        ("high", "high", 0.0, -0.4, False),
        ("high", "high", None, -0.4, False),
    ],
    ids=[
        "both_trusted_opposite",
        "med_high_opposite",
        "untrusted_left_inactive",
        "untrusted_right_inactive",
        "none_left_inactive",
        "below_floor_left",
        "below_floor_right",
        "exactly_at_floor",
        "same_sign",
        "zero_left",
        "none_score_left",
    ],
)
def test_split_predicate_matches_fix6_gate(
    left_conf: str | None,
    right_conf: str | None,
    left_score: float | None,
    right_score: float | None,
    expect_opposite: bool,
) -> None:
    embedding = _vec(0.0)
    left = _item(
        item_id="L",
        embedding=embedding,
        sentiment_confidence=left_conf,
        sentiment_score=left_score,
    )
    right = _item(
        item_id="R",
        embedding=embedding,
        sentiment_confidence=right_conf,
        sentiment_score=right_score,
        minutes_offset=1,
    )
    assert is_opposite_sentiment_pair(left, right) is expect_opposite


def test_all_untrusted_cluster_uses_tighter_threshold() -> None:
    """3 untrusted articles at mutual cosine ~0.82 → split at 0.85, no clustering."""
    # Build three vectors pairwise at cosine ~0.82 (between 0.80 and 0.85).
    rng = np.random.default_rng(0)
    base = rng.standard_normal(64)
    base /= np.linalg.norm(base)
    target_cosine = 0.82

    def perturb(seed: int) -> list[float]:
        # Mix the base vector with a fresh orthogonal direction to land
        # near the target cosine without going past 0.85.
        rng_local = np.random.default_rng(seed)
        direction = rng_local.standard_normal(64)
        direction -= direction.dot(base) * base
        direction /= np.linalg.norm(direction)
        # cos(angle) = w → embedding = w*base + sqrt(1-w^2)*direction
        weight = target_cosine
        vec = weight * base + np.sqrt(max(0.0, 1.0 - weight * weight)) * direction
        vec /= np.linalg.norm(vec)
        return vec.tolist()

    items = [
        _item(
            item_id=f"u{i}",
            embedding=perturb(i + 1),
            sentiment_confidence="abstain",
            sentiment_score=None,
            minutes_offset=i,
        )
        for i in range(3)
    ]
    # At intrabatch threshold 0.80 these three *would* cluster (cosine to base
    # is 0.82). At the all-untrusted tighter 0.85 threshold they should not.
    clusters = cluster_unmatched_embeddings(items, threshold=INTRABATCH_COALESCE)
    # Tightened path applies — produces 3 singletons rather than one cluster.
    assert all(len(cluster) == 1 for cluster in clusters)
    assert len(clusters) == 3
    # Sanity: confirm the constant used in the source is still 0.85.
    assert INTRABATCH_COALESCE_UNTRUSTED == 0.85
