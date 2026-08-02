#!/usr/bin/env python3
"""SWI-103: re-tag legacy articles with the LLM sentiment scorer.

Two re-score cohorts (symmetric — keyword regex would re-introduce the
SWI-103 bug it is meant to fix):
  1. Articles in the magnitude band that drives `narrative_matching`
     opposite-sign rejects: ABS(sentiment_score) >= 0.5.
  2. Articles linked to the known narrative offenders, regardless of
     magnitude.

After articles are re-scored, recomputes `narratives.avg_sentiment` and
`sentiment_confidence_roll` for every affected narrative using only
`is_trusted` contributors. Empty-trusted-set narratives get NULL/NULL
with the narrative_key printed for manual review.

Usage:
    SWINGY_ENV=production uv run python scripts/db/backfill_article_sentiment.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.article_sentiment_runner import score_articles_under_semaphore  # noqa: E402
from shared.database import Database, close_db  # noqa: E402
from shared.env import load_env  # noqa: E402
from shared.neon.update_content import write_article_sentiments  # noqa: E402
from shared.rules.sentiment_confidence import is_trusted, max_confidence  # noqa: E402

load_env()

KNOWN_OFFENDERS: list[str] = [
    "fuel_tax_reduction_policy",
    "gasoline_price_cut_april_2026",
    "admin_procedure_cut_apr20",
    "deputy_pm_business_conditions_reform",
    "regulatory_reform_suggestion",
]


async def _select_articles(db) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT a.id, a.url, a.title, a.summary
        FROM articles a
        WHERE a.summary IS NOT NULL AND a.summary != ''
          AND (
            ABS(a.sentiment_score) >= 0.5
            OR a.id IN (
              SELECT nu.article_id
              FROM narrative_updates nu
              JOIN narratives n ON n.id = nu.narrative_id
              WHERE n.narrative_key = ANY($1::text[])
            )
          )
        ORDER BY a.id
        """,
        KNOWN_OFFENDERS,
    )
    return [dict(r) for r in rows]


async def _recompute_affected_narratives(db, dry_run: bool) -> None:
    """Recompute avg_sentiment + sentiment_confidence_roll in two queries.

    Replaces the per-narrative N+1 by joining narrative_updates → articles
    once, then folding contributors in Python.
    """
    rows = await db.fetch_all(
        """
        SELECT n.id AS narrative_id,
               n.narrative_key,
               a.sentiment_score,
               a.sentiment_confidence
        FROM narratives n
        JOIN narrative_updates nu ON nu.narrative_id = n.id
        JOIN articles a ON a.id = nu.article_id
        WHERE n.pipeline_version = 'v2'
          AND n.id IN (
            SELECT DISTINCT nu2.narrative_id
            FROM narrative_updates nu2
            JOIN articles a2 ON a2.id = nu2.article_id
            WHERE ABS(a2.sentiment_score) >= 0.5
               OR n.narrative_key = ANY($1::text[])
        )
        """,
        KNOWN_OFFENDERS,
    )

    grouped: dict[str, dict] = defaultdict(
        lambda: {"narrative_key": None, "scores": [], "confs": []}
    )
    for r in rows:
        nid = str(r["narrative_id"])
        grouped[nid]["narrative_key"] = r["narrative_key"]
        grouped[nid]["confs"].append(r.get("sentiment_confidence"))
        if is_trusted(r.get("sentiment_confidence")) and r.get("sentiment_score") is not None:
            grouped[nid]["scores"].append(float(r["sentiment_score"]))

    if not grouped:
        return

    ids: list[str] = []
    avgs: list[float | None] = []
    rolls: list[str | None] = []
    for nid, g in grouped.items():
        avg = round(sum(g["scores"]) / len(g["scores"]), 3) if g["scores"] else None
        roll = max_confidence(g["confs"])
        if avg is None:
            print(f"  [empty-trusted-set] narrative_key={g['narrative_key']} — writing NULL/NULL")
        if dry_run:
            print(
                f"  [dry-run] narrative_key={g['narrative_key']} avg={avg} "
                f"conf_roll={roll} trusted_n={len(g['scores'])}/{len(g['confs'])}"
            )
            continue
        ids.append(nid)
        avgs.append(avg)
        rolls.append(roll)

    if dry_run or not ids:
        return

    await db.execute(
        """UPDATE narratives n
           SET avg_sentiment = u.avg,
               sentiment_confidence_roll = u.roll::sentiment_confidence_enum,
               updated_at = NOW()
           FROM (
               SELECT * FROM UNNEST($1::uuid[], $2::float8[], $3::text[])
               AS t(id, avg, roll)
           ) u
           WHERE n.id = u.id""",
        ids,
        avgs,
        rolls,
    )


async def backfill_sentiment(dry_run: bool) -> None:
    async with Database():
        from shared.database import get_db

        db = await get_db()
        articles = await _select_articles(db)
        print(f"Selected {len(articles)} articles for re-scoring (dry_run={dry_run})")

        rows = await score_articles_under_semaphore(articles)

        if dry_run:
            for url, score, conf in rows[:20]:
                print(f"  [dry-run] {url[:60]} -> score={score} conf={conf}")
        else:
            updated = await write_article_sentiments(rows)
            print(f"Re-scored {updated} articles")

        await _recompute_affected_narratives(db, dry_run)

    await close_db()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    asyncio.run(backfill_sentiment(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
