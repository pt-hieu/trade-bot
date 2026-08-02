"""Tests for data.narrative_matching.match_existing_narrative.

Fix 6 (2026-04-21) — direction-aware matching rejects opposite-sentiment
matches to stop the Hormuz rise/fall triplet from collapsing.
"""

from __future__ import annotations

import numpy as np

from data.narrative_matching import match_existing_narrative


def _make_centroid(
    *,
    embedding: np.ndarray,
    avg_sentiment: float = 0.5,
    article_count: int = 1,
    narrative_key: str = "n1",
    sentiment_confidence_roll: str | None = "high",
) -> dict:
    return {
        "embedding": embedding,
        "article_count": article_count,
        "source_count": 1,
        "avg_sentiment": avg_sentiment,
        "narrative_key": narrative_key,
        "sentiment_confidence_roll": sentiment_confidence_roll,
    }


def _aligned_embedding(dim: int = 8) -> np.ndarray:
    """Produce a deterministic unit-length vector for high-similarity testing."""
    return np.ones(dim) / np.sqrt(dim)


class TestSentimentDirectionGuard:
    def test_opposite_sentiment_rejects_match(self) -> None:
        embedding = _aligned_embedding()
        centroids = {
            "n1": _make_centroid(embedding=embedding, avg_sentiment=0.6),
        }
        result = match_existing_narrative(
            embedding=embedding.tolist(),
            centroids=centroids,
            similarity_threshold=0.7,
            max_articles=20,
            candidate_avg_sentiment=-0.6,
            candidate_confidence="high",
        )
        assert result is None

    def test_same_sign_sentiment_keeps_match(self) -> None:
        embedding = _aligned_embedding()
        centroids = {
            "n1": _make_centroid(embedding=embedding, avg_sentiment=0.6),
        }
        result = match_existing_narrative(
            embedding=embedding.tolist(),
            centroids=centroids,
            similarity_threshold=0.7,
            max_articles=20,
            candidate_avg_sentiment=0.4,
        )
        assert result == "n1"

    def test_low_magnitude_candidate_does_not_reject(self) -> None:
        """Tiny near-zero candidate sentiment is unstable — don't flip matches on it."""
        embedding = _aligned_embedding()
        centroids = {
            "n1": _make_centroid(embedding=embedding, avg_sentiment=0.6),
        }
        result = match_existing_narrative(
            embedding=embedding.tolist(),
            centroids=centroids,
            similarity_threshold=0.7,
            max_articles=20,
            candidate_avg_sentiment=-0.05,
        )
        assert result == "n1"

    def test_low_magnitude_existing_does_not_reject(self) -> None:
        embedding = _aligned_embedding()
        centroids = {
            "n1": _make_centroid(embedding=embedding, avg_sentiment=0.05),
        }
        result = match_existing_narrative(
            embedding=embedding.tolist(),
            centroids=centroids,
            similarity_threshold=0.7,
            max_articles=20,
            candidate_avg_sentiment=-0.6,
        )
        assert result == "n1"

    def test_none_sentiment_falls_back_to_legacy_behavior(self) -> None:
        """Callers that pass `candidate_avg_sentiment=None` get the pre-fix behavior."""
        embedding = _aligned_embedding()
        centroids = {
            "n1": _make_centroid(embedding=embedding, avg_sentiment=0.6),
        }
        result = match_existing_narrative(
            embedding=embedding.tolist(),
            centroids=centroids,
            similarity_threshold=0.7,
            max_articles=20,
            candidate_avg_sentiment=None,
        )
        assert result == "n1"


class TestLegacyThresholdBehavior:
    """Preserve pre-Fix-6 threshold tightening logic."""

    def test_low_similarity_returns_none(self) -> None:
        embedding = _aligned_embedding()
        far_centroid = -embedding  # opposite direction → cosine sim -1
        centroids = {
            "n1": _make_centroid(embedding=far_centroid, avg_sentiment=0.3),
        }
        result = match_existing_narrative(
            embedding=embedding.tolist(),
            centroids=centroids,
            similarity_threshold=0.7,
            max_articles=20,
            candidate_avg_sentiment=0.3,
        )
        assert result is None

    def test_article_count_cap(self) -> None:
        embedding = _aligned_embedding()
        centroids = {
            "n1": _make_centroid(embedding=embedding, avg_sentiment=0.3, article_count=25),
        }
        result = match_existing_narrative(
            embedding=embedding.tolist(),
            centroids=centroids,
            similarity_threshold=0.7,
            max_articles=20,
            candidate_avg_sentiment=0.3,
        )
        assert result is None
