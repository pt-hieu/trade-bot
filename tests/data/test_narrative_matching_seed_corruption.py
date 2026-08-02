"""Pin the SWI-103 root cause: a single wrong-sign LLM call must not
fragment a healthy narrative thread.

Constructs a centroid with a strong positive avg_sentiment + trusted
confidence, then probes the matching gate with one wrong-sign article at
each confidence level. Untrusted candidates bypass the reject; trusted
candidates fire it. This pins the *consumer* fix (confidence-gated
matching), not the LLM scorer behaviour.
"""

from __future__ import annotations

import numpy as np

from data.narrative_matching import match_existing_narrative


def _centroid(avg_sentiment: float, conf: str | None) -> dict[str, dict]:
    return {
        "n1": {
            "embedding": np.array([1.0, 0.0, 0.0]),
            "article_count": 5,
            "source_count": 3,
            "avg_sentiment": avg_sentiment,
            "sentiment_confidence_roll": conf,
        }
    }


def test_wrong_sign_with_trusted_confidence_rejects():
    centroids = _centroid(+0.7, "high")
    result = match_existing_narrative(
        embedding=[1.0, 0.0, 0.0],
        centroids=centroids,
        similarity_threshold=0.7,
        max_articles=20,
        candidate_avg_sentiment=-0.6,
        candidate_confidence="high",
    )
    assert result is None, "trusted opposite-sign candidate should be rejected"


def test_wrong_sign_with_low_confidence_bypasses_reject():
    centroids = _centroid(+0.7, "high")
    result = match_existing_narrative(
        embedding=[1.0, 0.0, 0.0],
        centroids=centroids,
        similarity_threshold=0.7,
        max_articles=20,
        candidate_avg_sentiment=-0.6,
        candidate_confidence="low",
    )
    assert result == "n1", "low-confidence candidate should bypass the gate"


def test_wrong_sign_with_abstain_confidence_bypasses_reject():
    centroids = _centroid(+0.7, "high")
    result = match_existing_narrative(
        embedding=[1.0, 0.0, 0.0],
        centroids=centroids,
        similarity_threshold=0.7,
        max_articles=20,
        candidate_avg_sentiment=-0.6,
        candidate_confidence="abstain",
    )
    assert result == "n1"


def test_wrong_sign_with_none_confidence_bypasses_reject():
    centroids = _centroid(+0.7, "high")
    result = match_existing_narrative(
        embedding=[1.0, 0.0, 0.0],
        centroids=centroids,
        similarity_threshold=0.7,
        max_articles=20,
        candidate_avg_sentiment=-0.6,
        candidate_confidence=None,
    )
    assert result == "n1"


def test_untrusted_narrative_rollup_bypasses_reject():
    centroids = _centroid(+0.7, "low")
    result = match_existing_narrative(
        embedding=[1.0, 0.0, 0.0],
        centroids=centroids,
        similarity_threshold=0.7,
        max_articles=20,
        candidate_avg_sentiment=-0.6,
        candidate_confidence="high",
    )
    assert result == "n1", "low-confidence rollup on narrative side bypasses the gate"


def test_same_sign_high_confidence_matches():
    centroids = _centroid(+0.7, "high")
    result = match_existing_narrative(
        embedding=[1.0, 0.0, 0.0],
        centroids=centroids,
        similarity_threshold=0.7,
        max_articles=20,
        candidate_avg_sentiment=+0.5,
        candidate_confidence="high",
    )
    assert result == "n1"
