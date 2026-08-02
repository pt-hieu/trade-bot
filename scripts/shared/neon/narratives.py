"""Narrative thread DB operations."""

import logging
from datetime import date

from shared.vn_universe import filter_vn_tickers

from ..database import get_db

logger = logging.getLogger(__name__)

# News v2 cutover (SWI-241): every read goes through `pipeline_version='v2'`
# so legacy v1 rows stay queryable for audit but never reach the LLMs.
# Rollback path = `git revert` of the cutover commit; v1 rows still live in
# the table.
PIPELINE_VERSION_V2 = "v2"


async def get_active_narratives(tickers: list[str] | None = None) -> list[dict]:
    """Get active narratives, optionally filtered by affected tickers (GIN overlap)."""
    db = await get_db()
    # Explicit columns — excludes centroid_embedding (large vector, unused by display callers)
    columns = """id, narrative_key, theme, narrative_type, article_count,
                 source_count, avg_sentiment, half_life_days, affected_tickers,
                 affected_sectors, conviction_score, summary, trading_implication,
                 maturity, first_seen, last_seen, status, related_catalysts,
                 pipeline_version"""
    # SWI-203: read-time defense-in-depth — drop narratives that are either
    # stale (last_seen older than 7 days) or have empty affected_tickers.
    # Writer-side sweeper (SWI-73) is the primary cleanup; this guard keeps
    # downstream agents from being polluted while the sweeper backfills.
    # pipeline_version is bound positionally — inlining via f-string adjacent
    # to a non-whitespace-terminated string literal previously produced
    # `> 0AND pipeline_version=...` and a Postgres parse error.
    if tickers:
        rows = await db.fetch_all(
            f"""SELECT {columns} FROM narratives
               WHERE status = 'active' AND affected_tickers && $1
                 AND last_seen >= CURRENT_DATE - INTERVAL '7 days'
                 AND array_length(affected_tickers, 1) > 0
                 AND pipeline_version = $2
               ORDER BY conviction_score DESC""",
            tickers,
            PIPELINE_VERSION_V2,
        )
    else:
        rows = await db.fetch_all(
            f"""SELECT {columns} FROM narratives
               WHERE status = 'active'
                 AND last_seen >= CURRENT_DATE - INTERVAL '7 days'
                 AND array_length(affected_tickers, 1) > 0
                 AND pipeline_version = $1
               ORDER BY conviction_score DESC""",
            PIPELINE_VERSION_V2,
        )
    return [dict(r) for r in rows]


async def get_all_active_with_embeddings() -> list[dict]:
    """Get active narratives with centroid embeddings for in-memory matching."""
    db = await get_db()
    rows = await db.fetch_all(
        """SELECT id, narrative_key, theme, narrative_type, article_count,
                  source_count, avg_sentiment, sentiment_confidence_roll,
                  half_life_days, affected_tickers,
                  centroid_embedding
           FROM narratives
           WHERE status = 'active' AND centroid_embedding IS NOT NULL""",
    )
    return [dict(r) for r in rows]


_UPSERT_NARRATIVE_SQL = """
INSERT INTO narratives
  (narrative_key, theme, narrative_type, affected_tickers, affected_sectors,
   article_count, source_count, avg_sentiment, first_seen, last_seen,
   conviction_score, half_life_days, summary, trading_implication,
   centroid_embedding, status, maturity, sentiment_confidence_roll,
   pipeline_version)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::vector,$16,$17,
        $18::sentiment_confidence_enum,$19)
ON CONFLICT (narrative_key) DO UPDATE SET
  theme = EXCLUDED.theme,
  affected_tickers = EXCLUDED.affected_tickers,
  affected_sectors = EXCLUDED.affected_sectors,
  article_count = EXCLUDED.article_count,
  source_count = EXCLUDED.source_count,
  avg_sentiment = EXCLUDED.avg_sentiment,
  sentiment_confidence_roll = EXCLUDED.sentiment_confidence_roll,
  last_seen = EXCLUDED.last_seen,
  conviction_score = EXCLUDED.conviction_score,
  summary = EXCLUDED.summary,
  trading_implication = EXCLUDED.trading_implication,
  centroid_embedding = EXCLUDED.centroid_embedding,
  pipeline_version = EXCLUDED.pipeline_version,
  updated_at = NOW()
RETURNING id
"""


async def upsert_narrative(data: dict) -> str | None:
    """Upsert a narrative by narrative_key. Returns narrative UUID or None on failure.

    News v2 (SWI-241):
      * `pipeline_version` defaults to ``v2`` so newly-written rows surface
        through the v2 read filter. Pass ``pipeline_version='v1'`` only when
        explicitly back-loading legacy data (no live caller does this).
      * Affected tickers are filtered through the VN universe before insert
        (write-side structural-invariant guard, design-challenge review).
    """
    db = await get_db()
    try:
        affected_tickers = filter_vn_tickers(
            list(data.get("affected_tickers") or []),
            context="upsert_narrative",
        )
        embedding = data.get("centroid_embedding")
        row = await db.fetch_one(
            _UPSERT_NARRATIVE_SQL,
            data["narrative_key"],
            data["theme"],
            data["narrative_type"],
            affected_tickers,
            data.get("affected_sectors", []),
            data.get("article_count", 0),
            data.get("source_count", 0),
            data.get("avg_sentiment"),
            data.get("first_seen"),
            data.get("last_seen"),
            data.get("conviction_score"),
            data.get("half_life_days"),
            data.get("summary"),
            data.get("trading_implication"),
            str(embedding) if embedding else None,
            data.get("status", "active"),
            data.get("maturity", "emerging"),
            data.get("sentiment_confidence_roll"),
            data.get("pipeline_version") or PIPELINE_VERSION_V2,
        )
        return str(row["id"]) if row else None
    except Exception as e:
        logger.warning("Failed to upsert narrative: %s", e)
        return None


async def add_narrative_update(
    narrative_id: str,
    article_id: str,
    update_date: date,
    headline: str,
    sentiment_shift: str | None = None,
) -> bool:
    """Insert a new narrative_updates row linking an article to a narrative."""
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO narrative_updates
                (narrative_id, article_id, update_date, headline, sentiment_shift)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (narrative_id, article_id) DO NOTHING""",
            narrative_id,
            article_id,
            update_date,
            headline,
            sentiment_shift,
        )
        return True
    except Exception as e:
        logger.warning("Failed to add narrative update: %s", e)
        return False


async def update_narrative_on_article(
    narrative_id: str,
    new_embedding: list[float],
    article_count: int,
    source_count: int,
    avg_sentiment: float | None,
    last_seen: date,
    new_tickers: list[str] | None = None,
    new_sectors: list[str] | None = None,
    sentiment_confidence_roll: str | None = None,
) -> bool:
    """Update centroid, counts, sentiment, last_seen in a single query.

    Fix 5 (2026-04-21): `new_tickers` / `new_sectors` union-merge into
    `affected_tickers` / `affected_sectors` so mature narratives don't keep
    `tickers=[]` after 17 article attachments. Callers pass the matched
    article's ticker/sector arrays; this function dedups inline via SQL
    array_cat + ARRAY(SELECT DISTINCT UNNEST(...)).
    """
    db = await get_db()
    try:
        await db.execute(
            """UPDATE narratives
               SET centroid_embedding = $2::vector,
                   article_count = $3,
                   source_count = $4,
                   avg_sentiment = $5,
                   last_seen = $6,
                   affected_tickers = ARRAY(
                       SELECT DISTINCT UNNEST(
                           COALESCE(affected_tickers, ARRAY[]::TEXT[]) || COALESCE($7, ARRAY[]::TEXT[])
                       )
                   ),
                   affected_sectors = ARRAY(
                       SELECT DISTINCT UNNEST(
                           COALESCE(affected_sectors, ARRAY[]::TEXT[]) || COALESCE($8, ARRAY[]::TEXT[])
                       )
                   ),
                   sentiment_confidence_roll = $9::sentiment_confidence_enum,
                   updated_at = NOW()
               WHERE id = $1""",
            narrative_id,
            str(new_embedding),
            article_count,
            source_count,
            round(avg_sentiment, 3) if avg_sentiment is not None else None,
            last_seen,
            list(new_tickers or []),
            list(new_sectors or []),
            sentiment_confidence_roll,
        )
        return True
    except Exception as e:
        logger.warning("Failed to update narrative on article: %s", e)
        return False


async def refresh_all_conviction_scores() -> int:
    """Recompute conviction for all active narratives in a single SQL statement.

    Formula: exp(-ln(2)/effective_half_life * days_since) * article_weight * source_weight
    Asymmetric decay: negative sentiment narratives (avg_sentiment < -0.1) decay 2x slower.
    """
    db = await get_db()
    try:
        result = await db.execute(
            """UPDATE narratives
               SET conviction_score = ROUND(CAST(
                   EXP(-LN(2.0) / GREATEST(
                       half_life_days * CASE WHEN avg_sentiment < -0.1 THEN 2.0 ELSE 1.0 END,
                       1
                   ) * (CURRENT_DATE - last_seen))
                   * LEAST(LOG(2, article_count + 1) / 3.0, 1.0)
                   * LEAST(0.25 + 0.25 * source_count, 1.0)
               AS NUMERIC), 3),
               updated_at = NOW()
               WHERE status = 'active' AND last_seen IS NOT NULL""",
        )
        return int((result or "UPDATE 0").split()[-1])
    except Exception as e:
        logger.warning("Failed to refresh conviction scores: %s", e)
        return 0


async def mark_stale_narratives(max_age_days: int = 14) -> int:
    """Mark active narratives not seen within max_age_days as stale."""
    db = await get_db()
    try:
        result = await db.execute(
            """UPDATE narratives
               SET status = 'stale', maturity = 'stale', updated_at = NOW()
               WHERE status = 'active'
                 AND last_seen < CURRENT_DATE - $1 * INTERVAL '1 day'""",
            max_age_days,
        )
        return int((result or "UPDATE 0").split()[-1])
    except Exception as e:
        logger.warning("Failed to mark stale narratives: %s", e)
        return 0


async def mark_dead_narratives(min_age_days: int = 3, max_conviction: float = 0.10) -> int:
    """Mark single-article narratives with low conviction as stale.

    Targets narratives that never attracted a second article and have decayed
    below the display threshold — cleaning up noise without touching
    multi-article threads.
    """
    db = await get_db()
    try:
        result = await db.execute(
            """UPDATE narratives
               SET status = 'stale', maturity = 'stale', updated_at = NOW()
               WHERE status = 'active'
                 AND article_count <= 1
                 AND conviction_score < $1
                 AND first_seen < CURRENT_DATE - $2 * INTERVAL '1 day'""",
            max_conviction,
            min_age_days,
        )
        return int((result or "UPDATE 0").split()[-1])
    except Exception as e:
        logger.warning("Failed to mark dead narratives: %s", e)
        return 0


async def update_article_narrative(
    article_id: str, narrative_id: str, embedding: list[float]
) -> bool:
    """Attach a narrative and content embedding to an article."""
    db = await get_db()
    try:
        await db.execute(
            """UPDATE articles
               SET narrative_id = $2,
                   content_embedding = $3::vector
               WHERE id = $1""",
            article_id,
            narrative_id,
            str(embedding),
        )
        return True
    except Exception as e:
        logger.warning("Failed to update article narrative: %s", e)
        return False


async def refresh_narrative_maturity() -> int:
    """Recompute maturity for all active narratives. Deterministic from counts + conviction.

    Maturity hierarchy (first match wins):
      stale:      conviction < 0.10 OR no article in 14+ days
      fading:     conviction < 0.30 AND no article in 3+ days
      mature:     5+ articles AND 3+ sources
      confirmed:  2+ articles AND 2+ sources
      developing: 2+ articles
      emerging:   everything else (single-article)
    """
    db = await get_db()
    try:
        result = await db.execute(
            """UPDATE narratives SET maturity = CASE
                WHEN conviction_score < 0.10
                     OR last_seen < CURRENT_DATE - INTERVAL '14 days'
                    THEN 'stale'
                WHEN conviction_score < 0.30
                     AND last_seen < CURRENT_DATE - INTERVAL '3 days'
                    THEN 'fading'
                WHEN article_count >= 5 AND source_count >= 3
                    THEN 'mature'
                WHEN article_count >= 2 AND source_count >= 2
                    THEN 'confirmed'
                WHEN article_count >= 2
                    THEN 'developing'
                ELSE 'emerging'
            END,
            updated_at = NOW()
            WHERE status = 'active'""",
        )
        return int((result or "UPDATE 0").split()[-1])
    except Exception as e:
        logger.warning("Failed to refresh narrative maturity: %s", e)
        return 0


async def refresh_related_catalysts() -> int:
    """Auto-populate related_catalysts by joining narratives ↔ catalysts through shared articles."""
    db = await get_db()
    try:
        result = await db.execute(
            """UPDATE narratives n
               SET related_catalysts = sub.catalyst_keys,
                   updated_at = NOW()
               FROM (
                   SELECT nu.narrative_id,
                          ARRAY_AGG(DISTINCT ca.catalyst_key) AS catalyst_keys
                   FROM narrative_updates nu
                   JOIN catalyst_articles ca ON ca.article_id = nu.article_id
                   GROUP BY nu.narrative_id
               ) sub
               WHERE n.id = sub.narrative_id
                 AND n.status = 'active'""",
        )
        return int((result or "UPDATE 0").split()[-1])
    except Exception as e:
        logger.warning("Failed to refresh related catalysts: %s", e)
        return 0


async def batch_count_distinct_sources(narrative_ids: list[str]) -> dict[str, int]:
    """Batch-count distinct article sources for multiple narratives in one query.

    Returns {narrative_id: source_count}. Missing IDs default to 1.
    """
    if not narrative_ids:
        return {}
    db = await get_db()
    try:
        rows = await db.fetch_all(
            """SELECT nu.narrative_id, COUNT(DISTINCT a.domain) as cnt
               FROM narrative_updates nu
               JOIN articles a ON a.id = nu.article_id
               WHERE nu.narrative_id = ANY($1)
               GROUP BY nu.narrative_id""",
            narrative_ids,
        )
        return {str(row["narrative_id"]): int(row["cnt"]) for row in rows}
    except Exception as e:
        logger.warning("Failed to batch count distinct sources: %s", e)
        return {}
