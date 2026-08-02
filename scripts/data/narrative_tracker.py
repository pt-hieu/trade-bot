"""Narrative threading: embed articles, cluster into story threads, decay stale ones."""

import asyncio
import logging
from datetime import date

from shared.agent_config import LLM_LABELING_CONCURRENCY
from shared.neon.articles import list_articles_range
from shared.neon.company_profiles import get_profiles_batch
from shared.neon.narratives import (
    add_narrative_update,
    batch_count_distinct_sources,
    get_all_active_with_embeddings,
    mark_dead_narratives,
    mark_stale_narratives,
    refresh_all_conviction_scores,
    refresh_narrative_maturity,
    update_article_narrative,
)
from shared.observability import span
from shared.rules.narrative_thresholds import WRITE_TIME_MATCH
from shared.silent_failure import (
    SILENT_FAILURE_MAX_LABELING_FAILURE_RATIO,
    SILENT_FAILURE_MIN_ARTICLES,
    SILENT_FAILURE_MIN_SUCCESS_RATIO,
    NarrativeTrackerSilentFailure,
)
from shared.vn_universe import VNUniverseUnavailable, load_vn_universe_async

from .narrative_coalesce import coalesce_unmatched
from .narrative_matching import (
    build_centroid_index,
    embed_articles,
    match_existing_narrative,
    sentiment_shift,
)
from .narrative_mutations import (
    JUNK_NARRATIVE_PATTERNS,
    create_narrative,
    update_narrative_aggregates,
)
from .narrative_seed import build_centroid_record

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = WRITE_TIME_MATCH
MAX_ARTICLES_PER_NARRATIVE = 20
# SWI-103 R2 arch F3: hoisted to shared/agent_config.py so all labeling
# orchestrators (narrative + article sentiment) share one cap.
LABELING_CONCURRENCY = LLM_LABELING_CONCURRENCY

# Re-export silent-failure + mutation helpers for backwards-compatible imports.
__all__ = (
    "JUNK_NARRATIVE_PATTERNS",
    "NarrativeTrackerSilentFailure",
    "SILENT_FAILURE_MAX_LABELING_FAILURE_RATIO",
    "SILENT_FAILURE_MIN_ARTICLES",
    "SILENT_FAILURE_MIN_SUCCESS_RATIO",
    "track_narratives",
)


async def track_narratives(scan_date: date) -> dict:
    """Main entry: embed today's articles, assign to narratives, decay stale.

    Returns summary dict with counts.
    """
    with span("narrative_tracking", scan_date=str(scan_date)):
        articles = await list_articles_range(scan_date, scan_date)
        if not articles:
            print("  [narratives] No articles for today, skipping")
            return {"assigned": 0, "created": 0, "stale": 0}

        embeddings = embed_articles(articles)
        print(f"  [narratives] Embedded {len(embeddings)}/{len(articles)} articles")

        active_narratives = await get_all_active_with_embeddings()
        narrative_centroids = build_centroid_index(active_narratives)

        # SWI-197 / SWI-200: hoist universe + sector_map ONCE per run so the
        # aggregator filters are O(1) per article. The sector_map covers every
        # ticker present in matched-narrative aggregates — built from the union
        # of the active_narratives' existing affected_tickers and the current
        # batch's article tickers.
        try:
            vn_universe: frozenset[str] | None = await load_vn_universe_async()
        except VNUniverseUnavailable:
            logger.warning(
                "track_narratives: VN universe unavailable — falling back to shape-only filter"
            )
            vn_universe = None

        sector_map = await _build_sector_map(articles, active_narratives)

        narrative_meta = {
            n["id"]: {
                "narrative_type": n.get("narrative_type"),
                "affected_sectors": n.get("affected_sectors") or [],
            }
            for n in active_narratives
        }

        assigned, created, assignment_failures = await _assign_all_articles(
            articles,
            embeddings,
            scan_date,
            narrative_centroids,
            vn_universe=vn_universe,
            sector_map=sector_map,
            narrative_meta=narrative_meta,
        )

        if assignment_failures > 0:
            logger.warning(
                "Narrative tracking: %d/%d articles failed or unmatched",
                assignment_failures,
                len(articles),
            )

        # Ratio invariant (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-003).
        # High-volume day with ~zero output means the labeler is silently broken.
        # Combined absolute + ratio test avoids false alarms on weekends/low-RSS days.
        total_output = assigned + created
        if (
            len(articles) >= SILENT_FAILURE_MIN_ARTICLES
            and total_output / len(articles) < SILENT_FAILURE_MIN_SUCCESS_RATIO
        ):
            raise NarrativeTrackerSilentFailure(
                scan_date,
                len(articles),
                assigned,
                created,
                detail=(
                    f"success ratio {total_output / len(articles):.3f} "
                    f"< floor {SILENT_FAILURE_MIN_SUCCESS_RATIO}"
                ),
            )

        refreshed = await refresh_all_conviction_scores()
        maturity_updated = await refresh_narrative_maturity()

        stale_age, stale_dead = await asyncio.gather(
            mark_stale_narratives(max_age_days=14),
            mark_dead_narratives(min_age_days=3, max_conviction=0.10),
        )
        stale = stale_age + stale_dead

        print(
            f"  [narratives] {assigned} assigned, {created} new, "
            f"{refreshed} refreshed, {maturity_updated} maturity, "
            f"{stale} stale ({stale_age} aged, {stale_dead} dead)"
        )
        return {"assigned": assigned, "created": created, "stale": stale}


async def _build_sector_map(
    articles: list[dict],
    active_narratives: list[dict],
) -> dict[str, str | None]:
    """Fetch ``ticker -> sector_id`` for every ticker that may flow into the
    aggregator (active narrative tickers ∪ batch article tickers). One DB
    round-trip; returned dict keys upper-cased.
    """
    tickers: set[str] = set()
    for narrative in active_narratives:
        for ticker in narrative.get("affected_tickers") or []:
            if ticker:
                tickers.add(str(ticker).upper())
    for article in articles:
        for ticker in article.get("affected_tickers") or []:
            if ticker:
                tickers.add(str(ticker).upper())
    if not tickers:
        return {}
    profiles = await get_profiles_batch(sorted(tickers))
    return {row["ticker"]: row.get("sector_id") for row in profiles}


async def _assign_all_articles(
    articles: list[dict],
    embeddings: dict[str, list[float]],
    scan_date: date,
    centroids: dict[str, dict],
    *,
    vn_universe: frozenset[str] | None = None,
    sector_map: dict[str, str | None] | None = None,
    narrative_meta: dict[str, dict] | None = None,
) -> tuple[int, int, int]:
    """Two-phase assignment: match existing narratives, then parallel-label new ones.

    Returns (assigned, created, failures).
    """
    matched: list[tuple[dict, list[float], str]] = []
    unmatched: list[tuple[dict, list[float]]] = []

    for article in articles:
        article_id = str(article["id"])
        embedding = embeddings.get(article_id)
        if not embedding:
            continue
        # Fix 6 (2026-04-21): pass the article's own sentiment so opposite-sign
        # candidates (e.g. Hormuz-closure news matching a Hormuz-reopening
        # narrative) are rejected even when cosine similarity is high.
        article_sentiment = article.get("sentiment_score")
        nearest_id = match_existing_narrative(
            embedding,
            centroids,
            SIMILARITY_THRESHOLD,
            MAX_ARTICLES_PER_NARRATIVE,
            candidate_avg_sentiment=(
                float(article_sentiment) if article_sentiment is not None else None
            ),
            candidate_confidence=article.get("sentiment_confidence"),
        )
        if nearest_id:
            matched.append((article, embedding, nearest_id))
        else:
            unmatched.append((article, embedding))

    # Batch-fetch source counts for all matched narratives (avoid N+1)
    matched_narrative_ids = list({narrative_id for _, _, narrative_id in matched})
    source_counts = (
        await batch_count_distinct_sources(matched_narrative_ids) if matched_narrative_ids else {}
    )

    assigned = 0
    meta = narrative_meta or {}
    for article, embedding, narrative_id in matched:
        try:
            narr = meta.get(narrative_id) or {}
            await update_narrative_aggregates(
                narrative_id,
                centroids[narrative_id],
                article,
                embedding,
                scan_date,
                source_counts.get(narrative_id) or 1,
                universe=vn_universe,
                sector_map=sector_map,
                narrative_type=narr.get("narrative_type"),
                affected_sectors=narr.get("affected_sectors") or [],
            )
            await add_narrative_update(
                narrative_id=narrative_id,
                article_id=str(article["id"]),
                update_date=scan_date,
                headline=article.get("title") or "Untitled",
                sentiment_shift=sentiment_shift(article, centroids[narrative_id]),
            )
            await update_article_narrative(str(article["id"]), narrative_id, embedding)
            assigned += 1
        except Exception as e:
            logger.warning("Matched article update failed for %s: %s", article.get("id"), e)

    created = 0
    failures = 0
    exception_count = 0
    if unmatched:
        # SWI-74 Layer 1: coalesce same-event articles within this batch
        # so siblings dedup against each other instead of producing
        # parallel `narrative_key` variants ("iran_us_peace_talks_islamabad"
        # vs "us_iran_peace_talks_islamabad"). Coalesce mutates centroids +
        # narrative_meta in place; the post-coalesce residual goes to the
        # parallel-label fallback below.
        unmatched, coalesce_created, coalesce_attached = await coalesce_unmatched(
            unmatched,
            centroids,
            scan_date,
            similarity_threshold=SIMILARITY_THRESHOLD,
            max_articles_per_narrative=MAX_ARTICLES_PER_NARRATIVE,
            vn_universe=vn_universe,
            sector_map=sector_map,
            narrative_meta=meta,
        )
        created += coalesce_created
        assigned += coalesce_attached

    if unmatched:
        semaphore = asyncio.Semaphore(LABELING_CONCURRENCY)

        async def _throttled_create(article: dict, embedding: list[float]) -> dict | None:
            async with semaphore:
                return await create_narrative(article, embedding, scan_date)

        label_tasks = [_throttled_create(article, embedding) for article, embedding in unmatched]
        results = await asyncio.gather(*label_tasks, return_exceptions=True)

        for (article, embedding), result in zip(unmatched, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("Parallel labeling failed for %s: %s", article.get("id"), result)
                failures += 1
                exception_count += 1
                continue
            if result:
                narrative_id = result["id"]
                await update_article_narrative(str(article["id"]), narrative_id, embedding)
                created += 1
                # build_centroid_record carries SWI-103 R2 RCA F1's abstain
                # semantics (avg_sentiment=None for untrusted seeds) into the
                # in-memory mirror so within-scan gating matches DB state.
                centroids[narrative_id] = build_centroid_record(article, embedding, result)
                meta[narrative_id] = {
                    "narrative_type": result.get("narrative_type"),
                    "affected_sectors": list(result.get("affected_sectors") or []),
                }
            else:
                failures += 1

        # Loud failure when the labeler dies wholesale (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-003).
        # ``return_exceptions=True`` alone turned every silent labeler error into a counted
        # failure, masking provider outages. This threshold keeps transient failures tolerable
        # while paging on-call when > 20% of unmatched articles error out.
        if (
            len(unmatched) >= SILENT_FAILURE_MIN_ARTICLES
            and exception_count > SILENT_FAILURE_MAX_LABELING_FAILURE_RATIO * len(unmatched)
        ):
            raise NarrativeTrackerSilentFailure(
                scan_date,
                len(unmatched),
                assigned,
                created,
                detail=(
                    f"{exception_count}/{len(unmatched)} labeling exceptions "
                    f"> ratio {SILENT_FAILURE_MAX_LABELING_FAILURE_RATIO}"
                ),
            )

    return assigned, created, failures


# Creator + aggregate-updater live in data.narrative_mutations (extracted to
# keep this file under the 350-line cap). Import + re-export above.
