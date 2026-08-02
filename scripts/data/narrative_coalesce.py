"""Intra-batch coalesce of unmatched articles (SWI-74 Layer 1).

Sits between match-existing and parallel-label phases of
``narrative_tracker._assign_all_articles``. Without coalesce, parallel
labelers each pick a free-form ``narrative_key`` for the same real-world
event so the DB-side ``ON CONFLICT (narrative_key)`` guard never fires
(LLM picks ``iran_us_peace_talks_islamabad`` for one article and
``us_iran_peace_talks_islamabad`` for the next).

Concurrency contract:
  * Cluster-rep ``create_narrative`` calls run SEQUENTIALLY in
    largest-cluster-first order. Each new centroid is seeded into the
    in-memory ``centroids`` dict before the next rep is processed so a
    later cluster's rep MAY match an earlier seeded centroid at the
    write-time threshold (asymmetric thresholds — 0.80 intra-batch vs
    0.72 write-time — produce intentional soft net-widening).
  * Member attach is fanned out via ``asyncio.gather`` after all reps
    are seeded — those calls only write per-article aggregates and do
    not mutate the rep-creation invariants.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from datetime import datetime as _dt
from typing import TYPE_CHECKING

from shared.neon.narratives import add_narrative_update, update_article_narrative
from shared.rules.narrative_clustering import (
    ArticleEmbeddingItem,
    cluster_unmatched_embeddings,
    is_opposite_sentiment_pair,
    pick_cluster_representative,
)

from .narrative_matching import match_existing_narrative, sentiment_shift
from .narrative_mutations import create_narrative, update_narrative_aggregates
from .narrative_seed import build_centroid_record

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)


def _to_cluster_item(article: dict, embedding: list[float]) -> ArticleEmbeddingItem:
    """Wrap a richer article dict to the rules-layer contract.

    Articles missing ``published_at`` log a warning and fall back to
    ``datetime.min`` so id-ASC tiebreak still produces deterministic
    ordering; the warning surfaces a producer-side defect (article ingest
    must always populate the column) without killing the scan.
    """
    published_at = article.get("published_at")
    if not isinstance(published_at, _dt):
        logger.warning(
            "narrative_coalesce: article %s missing published_at (got %r); "
            "falling back to datetime.min for cluster ordering",
            article.get("id"),
            published_at,
        )
        published_at = _dt.min
    score = article.get("sentiment_score")
    return ArticleEmbeddingItem(
        id=str(article["id"]),
        published_at=published_at,
        sentiment_score=float(score) if score is not None else None,
        sentiment_confidence=article.get("sentiment_confidence"),
        embedding=embedding,
    )


async def _attach_member(
    *,
    article: dict,
    embedding: list[float],
    narrative_id: str,
    centroid_info: dict,
    scan_date: date,
    vn_universe,
    sector_map,
    narrative_type: str | None,
    affected_sectors: list[str],
) -> bool:
    """Attach a non-rep cluster member to an existing seed narrative.

    Returns True on success, False on failure. The aggregate update path
    matches the ``matched`` branch of ``_assign_all_articles`` so the
    rolling centroid + sentiment behave identically.
    """
    try:
        await update_narrative_aggregates(
            narrative_id,
            centroid_info,
            article,
            embedding,
            scan_date,
            1,
            universe=vn_universe,
            sector_map=sector_map,
            narrative_type=narrative_type,
            affected_sectors=affected_sectors,
        )
        await add_narrative_update(
            narrative_id=narrative_id,
            article_id=str(article["id"]),
            update_date=scan_date,
            headline=article.get("title") or "Untitled",
            sentiment_shift=sentiment_shift(article, centroid_info),
        )
        await update_article_narrative(str(article["id"]), narrative_id, embedding)
        return True
    except Exception as exc:  # noqa: BLE001 — logged with full context
        logger.warning(
            "coalesce: attach failed narrative=%s article=%s error=%s",
            narrative_id,
            article.get("id"),
            exc,
        )
        return False


async def coalesce_unmatched(
    unmatched: list[tuple[dict, list[float]]],
    centroids: dict[str, dict],
    scan_date: date,
    *,
    similarity_threshold: float,
    max_articles_per_narrative: int,
    vn_universe: frozenset[str] | None,
    sector_map: Mapping[str, str | None] | None,
    narrative_meta: dict[str, dict],
) -> tuple[list[tuple[dict, list[float]]], int, int]:
    """Cluster unmatched articles, label one rep per cluster, attach the rest.

    Returns ``(still_unmatched, created, attached)``. ``still_unmatched``
    is the list of articles that remain unlabeled (typically because
    their cluster's rep create failed) — caller continues to the
    parallel-label fallback for them.

    Mutates ``centroids`` and ``narrative_meta`` in place so the
    write-time match path can route subsequent batch articles into the
    freshly seeded narratives.
    """
    if not unmatched:
        return [], 0, 0

    by_id: dict[str, tuple[dict, list[float]]] = {
        str(article["id"]): (article, embedding) for article, embedding in unmatched
    }
    items = [_to_cluster_item(article, embedding) for article, embedding in unmatched]
    clusters = cluster_unmatched_embeddings(items)
    # Largest cluster first → most "settled" centroids seeded first; later
    # clusters' reps may match earlier seeds at the write-time threshold.
    clusters.sort(key=len, reverse=True)

    still_unmatched: list[tuple[dict, list[float]]] = []
    created = 0
    attach_jobs: list = []
    # Members split off by the Fix-6 attach guard get queued as singleton
    # clusters and processed in a second pass — avoids appending to
    # ``clusters`` while iterating it.
    pending_singletons: list[ArticleEmbeddingItem] = []

    cluster_queue: list[list[ArticleEmbeddingItem]] = list(clusters)

    while cluster_queue:
        cluster = cluster_queue.pop(0)
        if not cluster:
            continue

        rep_item = pick_cluster_representative(cluster)
        rep_id = rep_item["id"]
        rep_article, rep_embedding = by_id[rep_id]

        # Fix-6 attach guard: even within a cluster, an untrusted-positive
        # rep paired with a trusted-negative-magnitude member would
        # otherwise pollute the rolling sentiment. Split-off members
        # re-enter the queue as singletons so they get their own label.
        members_to_attach: list[ArticleEmbeddingItem] = []
        for member in cluster:
            if member["id"] == rep_id:
                continue
            if is_opposite_sentiment_pair(rep_item, member):
                pending_singletons.append(member)
                continue
            members_to_attach.append(member)

        try:
            created_meta = await create_narrative(rep_article, rep_embedding, scan_date)
        except Exception as exc:  # noqa: BLE001 — DB/network errors propagate from upsert_narrative; downgrade so one bad rep doesn't kill the batch.
            logger.warning(
                "coalesce: rep create exception for article %s: %s",
                rep_article.get("id"),
                exc,
            )
            created_meta = None

        if not created_meta:
            for member in cluster:
                still_unmatched.append(by_id[member["id"]])
            continue

        narrative_id = created_meta["id"]
        await update_article_narrative(rep_id, narrative_id, rep_embedding)
        created += 1

        narrative_type = created_meta.get("narrative_type")
        affected_sectors = list(created_meta.get("affected_sectors") or [])

        centroids[narrative_id] = build_centroid_record(rep_article, rep_embedding, created_meta)
        narrative_meta[narrative_id] = {
            "narrative_type": narrative_type,
            "affected_sectors": affected_sectors,
        }

        for member in members_to_attach:
            member_article, member_embedding = by_id[member["id"]]
            attach_jobs.append(
                _attach_member(
                    article=member_article,
                    embedding=member_embedding,
                    narrative_id=narrative_id,
                    centroid_info=centroids[narrative_id],
                    scan_date=scan_date,
                    vn_universe=vn_universe,
                    sector_map=sector_map,
                    narrative_type=narrative_type,
                    affected_sectors=affected_sectors,
                )
            )

        # Drain split-off singletons onto the queue tail so they share the
        # sequential create + soft-net-widening invariants of the main pass.
        if pending_singletons:
            cluster_queue.extend([member] for member in pending_singletons)
            pending_singletons.clear()

    attach_results = (
        await asyncio.gather(*attach_jobs, return_exceptions=True) if attach_jobs else []
    )
    attached = 0
    for result in attach_results:
        if isinstance(result, BaseException):
            logger.warning("coalesce: attach task raised: %s", result)
            continue
        if result:
            attached += 1

    # Soft-net-widening fallback: route surviving residuals through the
    # write-time matcher so they reuse a freshly seeded centroid instead
    # of paying another label round. ``match_existing_narrative`` is pure
    # in-memory, so we collect routes synchronously and fan the
    # ``_attach_member`` writes out via gather.
    fallback_routes: list[tuple[str, dict, list[float], str]] = []
    for article, embedding in still_unmatched:
        article_sentiment = article.get("sentiment_score")
        nearest_id = match_existing_narrative(
            embedding,
            centroids,
            similarity_threshold,
            max_articles_per_narrative,
            candidate_avg_sentiment=(
                float(article_sentiment) if article_sentiment is not None else None
            ),
            candidate_confidence=article.get("sentiment_confidence"),
        )
        if nearest_id:
            fallback_routes.append((str(article["id"]), article, embedding, nearest_id))

    if fallback_routes:
        fallback_jobs = [
            _attach_member(
                article=article,
                embedding=embedding,
                narrative_id=narrative_id,
                centroid_info=centroids[narrative_id],
                scan_date=scan_date,
                vn_universe=vn_universe,
                sector_map=sector_map,
                narrative_type=(narrative_meta.get(narrative_id) or {}).get("narrative_type"),
                affected_sectors=(narrative_meta.get(narrative_id) or {}).get("affected_sectors")
                or [],
            )
            for _, article, embedding, narrative_id in fallback_routes
        ]
        fallback_results = await asyncio.gather(*fallback_jobs, return_exceptions=True)
        rerouted_ids: set[str] = set()
        for (article_id, _, _, _), result in zip(fallback_routes, fallback_results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("coalesce: fallback attach raised: %s", result)
                continue
            if result:
                attached += 1
                rerouted_ids.add(article_id)
        if rerouted_ids:
            still_unmatched = [
                pair for pair in still_unmatched if str(pair[0]["id"]) not in rerouted_ids
            ]

    return still_unmatched, created, attached
