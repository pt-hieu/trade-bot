"""Narrative matching: embedding, centroid index, similarity search."""

import logging

import numpy as np

from agents.memory.embeddings import get_embedding_model
from shared.rules.narrative_thresholds import SENTIMENT_REJECT_MIN_MAGNITUDE
from shared.rules.sentiment_confidence import is_opposite_sentiment, is_trusted

logger = logging.getLogger(__name__)


def build_centroid_index(narratives: list[dict]) -> dict[str, dict]:
    """Build {narrative_id: {embedding, article_count, ...}} for in-memory matching."""
    index: dict[str, dict] = {}
    for narrative in narratives:
        centroid = narrative.get("centroid_embedding")
        if centroid is None:
            continue
        # pgvector returns string or list depending on driver
        if isinstance(centroid, str):
            centroid = [float(x) for x in centroid.strip("[]").split(",")]
        index[str(narrative["id"])] = {
            "embedding": np.array(centroid),
            "article_count": narrative.get("article_count") or 1,
            "source_count": narrative.get("source_count") or 1,
            "avg_sentiment": narrative.get("avg_sentiment"),
            "sentiment_confidence_roll": narrative.get("sentiment_confidence_roll"),
            "half_life_days": narrative.get("half_life_days") or 3,
            "affected_tickers": narrative.get("affected_tickers") or [],
            "narrative_key": narrative.get("narrative_key") or "",
            "theme": narrative.get("theme") or "",
        }
    return index


def embed_articles(articles: list[dict]) -> dict[str, list[float]]:
    """Batch embed article summaries using local model. Returns {article_id: embedding}."""
    model = get_embedding_model()
    texts = []
    ids = []
    for article in articles:
        title = article.get("title") or ""
        summary = article.get("summary") or ""
        text = f"{title}. {summary}".strip()
        if len(text) < 20:
            logger.info(
                "Skipping article %s for embedding: text too short (%d chars)",
                article.get("id"),
                len(text),
            )
            continue
        texts.append(text)
        ids.append(str(article["id"]))

    if not texts:
        return {}

    vectors = model.encode(texts, batch_size=32, convert_to_numpy=True)
    return {article_id: vector.tolist() for article_id, vector in zip(ids, vectors, strict=True)}


def find_nearest_in_memory(
    embedding: np.ndarray, centroids: dict[str, dict], threshold: float
) -> tuple[str | None, float]:
    """Find nearest narrative centroid via numpy cosine similarity. Returns (id, similarity)."""
    if not centroids:
        return None, 0.0

    ids = list(centroids.keys())
    matrix = np.stack([centroids[narrative_id]["embedding"] for narrative_id in ids])
    norms = np.linalg.norm(matrix, axis=1)
    embedding_norm = np.linalg.norm(embedding)
    if embedding_norm == 0:
        return None, 0.0
    similarities = matrix @ embedding / (norms * embedding_norm + 1e-10)
    best_idx = int(np.argmax(similarities))
    best_similarity = float(similarities[best_idx])

    if best_similarity >= threshold:
        return ids[best_idx], best_similarity
    return None, best_similarity


# Fix 6 (2026-04-21): direction-aware matching — an opposite-sentiment
# candidate rejects the match even when the embedding cosine similarity is
# high. The magnitude floor lives in shared/rules/narrative_thresholds.py
# so the intra-batch coalesce gate (SWI-74) uses the identical constant.


def match_existing_narrative(
    embedding: list[float],
    centroids: dict[str, dict],
    similarity_threshold: float,
    max_articles: int,
    candidate_avg_sentiment: float | None = None,
    candidate_confidence: str | None = None,
) -> str | None:
    """Check if article matches an existing narrative. Returns narrative_id or None.

    ``candidate_avg_sentiment`` + ``candidate_confidence`` together drive the
    opposite-sign reject (SWI-103): the gate fires only when BOTH the
    candidate article AND the narrative-level rollup carry confidence in
    {high, medium}. Low / abstain / None on either side bypasses the gate
    so a single mis-classified LLM call cannot reject otherwise-good
    matches (R1 RCA — bare scalar trust was the structural defect).
    """
    emb_array = np.array(embedding)
    nearest_id, similarity = find_nearest_in_memory(emb_array, centroids, similarity_threshold)
    if not nearest_id:
        return None

    narrative_info = centroids[nearest_id]
    narrative_article_count = narrative_info.get("article_count") or 1
    tightened_threshold = similarity_threshold + min(narrative_article_count * 0.003, 0.04)
    if similarity < tightened_threshold:
        return None
    if narrative_article_count >= max_articles:
        return None

    narrative_confidence = narrative_info.get("sentiment_confidence_roll")
    existing_avg = narrative_info.get("avg_sentiment")
    if is_opposite_sentiment(
        candidate_avg_sentiment,
        candidate_confidence,
        existing_avg,
        narrative_confidence,
        magnitude_floor=SENTIMENT_REJECT_MIN_MAGNITUDE,
    ):
        logger.info(
            "narrative_matching: rejected match %s (sim=%.3f) — opposite sentiment "
            "existing=%.2f candidate=%.2f",
            narrative_info.get("narrative_key") or nearest_id,
            similarity,
            float(existing_avg or 0.0),
            float(candidate_avg_sentiment or 0.0),
        )
        return None

    return nearest_id


def sentiment_shift(article: dict, narrative_info: dict) -> str:
    """Determine if article strengthens or weakens the narrative's sentiment.

    Confidence-gated (SWI-103 R2 F2): when either side is low/abstain/None,
    return 'neutral' so untrusted polarity does not flip the recorded
    direction of an in-flight narrative.
    """
    if not is_trusted(article.get("sentiment_confidence")):
        return "neutral"
    if not is_trusted(narrative_info.get("sentiment_confidence_roll")):
        return "neutral"

    article_sentiment = article.get("sentiment_score") or 0
    avg_sentiment = narrative_info.get("avg_sentiment") or 0

    if abs(article_sentiment) < 0.1:
        return "neutral"
    if (article_sentiment > 0 and avg_sentiment >= 0) or (
        article_sentiment < 0 and avg_sentiment <= 0
    ):
        return "strengthens"
    return "weakens"
