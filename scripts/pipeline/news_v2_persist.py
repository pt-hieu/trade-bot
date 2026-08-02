"""News v2 persistence helpers + paging (SWI-244, SWI-245).

Lives in `pipeline/` so both the morning orchestrator
(`scripts/news_pipeline_v2.py`) and the intraday catalyst-check entry
point (`scripts/catalyst_check.py`) share the same Stage 2 → DB writer
without leaking through private-prefix imports.

Two responsibility groups:
  * **Candidate resolution** — `build_alias_index` and
    `resolve_candidates` map raw Stage 1 entity tokens to
    `company_profiles` rows so Stage 2 receives a candidates-only block.
  * **Extraction persistence + paging** — `persist_extractions` walks
    Stage 2 outputs and writes article + narrative + catalyst rows;
    `emit_zero_row_alerts` and `emit_stage1_pass_rate_alert` page on
    suspicious pipeline shapes (replaces the eval gate per the
    ship-fast directive in the design-challenge review).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from shared.database import get_db
from shared.rules.catalyst_key import compose_catalyst_key
from shared.telegram import send_telegram_error

if TYPE_CHECKING:
    from agents.news_extractor import NewsExtraction

logger = logging.getLogger(__name__)

ZERO_ROW_ALERT_THRESHOLD = 5


# ── Candidate resolution ───────────────────────────────────────────────────


def build_alias_index(universe_rows: list[dict]) -> dict[str, dict]:
    """Build a `{lowered_alias_or_ticker: row}` index for fast resolution."""
    index: dict[str, dict] = {}
    for row in universe_rows:
        ticker = row["ticker"]
        index[ticker.lower()] = row
        for alias in row.get("aliases") or []:
            alias_l = alias.strip().lower()
            if alias_l and alias_l not in index:
                index[alias_l] = row
    return index


def resolve_candidates(
    raw_entities: list[str],
    alias_index: dict[str, dict],
) -> list[dict]:
    """Map Stage 1 raw entity tokens to company_profiles rows.

    Tokens that don't resolve are silently dropped — Stage 2 receives only
    what we can ground.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for raw in raw_entities or []:
        token = (raw or "").strip().lower()
        if not token:
            continue
        row = alias_index.get(token) or alias_index.get(token.upper().lower())
        if row is None:
            # Substring fallback for Vietnamese trailing-word phrasing.
            for alias, candidate in alias_index.items():
                if len(alias) >= 4 and alias in token:
                    row = candidate
                    break
        if row is None:
            continue
        ticker = row["ticker"]
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append({**row, "raw_entity": raw})
    return out


# ── Extraction persistence ────────────────────────────────────────────────


async def persist_extractions(
    scan_date: date,
    extractions: Sequence[tuple[dict, NewsExtraction | None]],
) -> dict[str, int]:
    """Write Stage 2 outputs to articles + narratives + catalysts.

    Returns counters used by the run summary + paging.
    """
    from shared.neon import upsert_catalyst, upsert_narrative
    from shared.neon.catalysts import link_catalyst_articles

    db = await get_db()
    counts = Counter[str]()

    active_rows = await db.fetch_all(
        "SELECT id, narrative_key FROM narratives "
        "WHERE status = 'active' AND pipeline_version = 'v2'"
    )
    narrative_id_by_key: dict[str, str] = {r["narrative_key"]: str(r["id"]) for r in active_rows}

    for article, extraction in extractions:
        article_id = article.get("id")
        if not article_id:
            continue
        if extraction is None:
            counts["stage2_shape_fail"] += 1
            continue
        if extraction.abstain:  # type: ignore[union-attr]
            counts["stage2_abstain"] += 1
            continue

        await db.execute(
            """UPDATE articles
                  SET affected_tickers = $2,
                      sentiment_score = $3,
                      sentiment_tickers = $4,
                      sentiment_confidence = NULLIF($5, 'unclassified')::sentiment_confidence_enum
                WHERE id = $1""",
            article_id,
            extraction.affected_tickers,  # type: ignore[union-attr]
            extraction.sentiment_score,  # type: ignore[union-attr]
            extraction.affected_tickers,  # type: ignore[union-attr]
            extraction.sentiment_confidence.lower(),  # type: ignore[union-attr]
        )
        counts["articles_updated"] += 1

        if (
            extraction.narrative_link_kind in ("EXISTING", "NEW")  # type: ignore[union-attr]
            and extraction.narrative_match_key  # type: ignore[union-attr]
        ):
            narrative_key = extraction.narrative_match_key  # type: ignore[union-attr]
            narrative_id = narrative_id_by_key.get(narrative_key)
            if narrative_id is None:
                narrative_id = await upsert_narrative(
                    {
                        "narrative_key": narrative_key,
                        "theme": (article.get("title") or narrative_key)[:200],
                        "narrative_type": extraction.narrative_type or "unclassified",  # type: ignore[union-attr]
                        "affected_tickers": extraction.affected_tickers,  # type: ignore[union-attr]
                        "first_seen": scan_date,
                        "last_seen": scan_date,
                        "summary": (article.get("summary") or "")[:500],
                        "sentiment_confidence_roll": (
                            extraction.sentiment_confidence.lower()  # type: ignore[union-attr]
                            if extraction.sentiment_confidence != "unclassified"  # type: ignore[union-attr]
                            else None
                        ),
                    }
                )
                if narrative_id:
                    narrative_id_by_key[narrative_key] = narrative_id
                    counts["narratives_created"] += 1
            else:
                counts["narratives_attached"] += 1
            if narrative_id:
                await db.execute(
                    "UPDATE articles SET narrative_id = $2 WHERE id = $1",
                    article_id,
                    narrative_id,
                )

        if (
            extraction.catalyst_link_kind in ("EXISTING", "NEW")  # type: ignore[union-attr]
            and extraction.catalyst_event_phrase  # type: ignore[union-attr]
        ):
            catalyst_key = compose_catalyst_key(extraction.catalyst_event_phrase)  # type: ignore[union-attr]
            await upsert_catalyst(
                {
                    "catalyst_key": catalyst_key,
                    "event": extraction.catalyst_event_phrase,  # type: ignore[union-attr]
                    "expected": "ongoing",
                    "affected_tickers": extraction.affected_tickers,  # type: ignore[union-attr]
                    "impact": (
                        extraction.catalyst_impact  # type: ignore[union-attr]
                        if extraction.catalyst_impact != "unclassified"  # type: ignore[union-attr]
                        else "NEUTRAL"
                    ),
                    "confidence": (
                        extraction.catalyst_confidence  # type: ignore[union-attr]
                        if extraction.catalyst_confidence != "unclassified"  # type: ignore[union-attr]
                        else "LOW"
                    ),
                    "catalyst_type": (
                        extraction.catalyst_type  # type: ignore[union-attr]
                        if extraction.catalyst_type != "unclassified"  # type: ignore[union-attr]
                        else None
                    ),
                    "added_date": scan_date,
                }
            )
            await link_catalyst_articles(catalyst_key, [article_id])
            counts["catalysts_upserted"] += 1

    return dict(counts)


# ── Paging ─────────────────────────────────────────────────────────────────


async def emit_zero_row_alerts() -> None:
    """Page when v2 produced no narratives/catalysts in the last 24h."""
    db = await get_db()
    rows = await db.fetch_one(
        """SELECT
             (SELECT COUNT(*) FROM narratives
                WHERE pipeline_version = 'v2'
                  AND created_at > NOW() - INTERVAL '24 hours') AS n_narratives,
             (SELECT COUNT(*) FROM catalysts
                WHERE pipeline_version = 'v2'
                  AND created_at > NOW() - INTERVAL '24 hours') AS n_catalysts"""
    )
    if not rows:
        return
    n_narratives = int(rows.get("n_narratives") or 0)
    n_catalysts = int(rows.get("n_catalysts") or 0)
    if n_narratives < ZERO_ROW_ALERT_THRESHOLD or n_catalysts < ZERO_ROW_ALERT_THRESHOLD:
        send_telegram_error(
            f"⚠️ news_v2 zero-row alert: 24h narratives={n_narratives}, "
            f"catalysts={n_catalysts}. Stage 1/2 may be silently failing."
        )


async def emit_stage1_pass_rate_alert(passed: int, total: int) -> None:
    """Page when Stage 1 pass-rate falls outside the [20%, 95%] band."""
    if total < 20:
        return
    rate = passed / total
    if rate < 0.20 or rate > 0.95:
        send_telegram_error(
            f"⚠️ news_v2 Stage 1 pass-rate {rate:.0%} ({passed}/{total}) "
            f"outside [20%, 95%] band — relevance gate may be drifting."
        )


# ── High-level v2 pass — used by intraday catalyst_check ──────────────────


async def run_news_v2_pass(scan_date: date, articles: list[dict]) -> int:
    """Run Stage 1 + Stage 2 over rehydrated articles and persist via the
    shared writer.

    Caller passes a flat id-bearing list (shape: ``RehydratedArticle`` from
    ``pipeline.types``). Missing ``id`` is a hard failure — the prior
    dict-of-queries shape silently no-op'd Stage 1 verdict UPDATEs when
    the dicts came from RSS fetches without DB ids.

    Returns the count of Stage 2 extractions that produced a non-abstain
    update. Other side effects — narrative + catalyst attach, ticker tag,
    stage1_verdict — go through ``persist_extractions``.
    """
    from agents.news_extractor import extract_articles
    from agents.news_relevance import (
        drop_bucket,
        routes_to_stage_two,
        score_relevance,
        select_candidate_entities,
        verdict_to_jsonb,
    )
    from pipeline.context_blocks_news_v2 import (
        build_resolved_candidates_block,
        build_stage_one_payload,
        build_stage_two_static_payload,
    )
    from shared.neon import get_universe_with_aliases
    from shared.vn_universe import load_vn_universe_async

    if not articles:
        return 0
    missing_id_indexes = [i for i, article in enumerate(articles) if not article.get("id")]
    if missing_id_indexes:
        raise ValueError(
            f"run_news_v2_pass: {len(missing_id_indexes)} articles missing id "
            f"(first indexes: {missing_id_indexes[:3]}); rehydration must populate id"
        )

    await load_vn_universe_async()
    universe_rows = await get_universe_with_aliases(limit=2000)
    stage_one = await build_stage_one_payload(universe_limit=200, universe_rows=universe_rows)
    stage_two_payload, _, _ = await build_stage_two_static_payload(universe_rows=universe_rows)
    alias_index = build_alias_index(universe_rows)

    stage1_results = await score_relevance(articles, stage_one["universe_block"])
    db = await get_db()
    drops: Counter[str] = Counter()
    routed_jobs: list[dict] = []
    for article, verdict in stage1_results:
        await db.execute(
            "UPDATE articles SET stage1_verdict = $2::jsonb WHERE id = $1",
            article.get("id"),
            verdict_to_jsonb(verdict),
        )
        if not routes_to_stage_two(verdict):
            drops[drop_bucket(verdict)] += 1
            continue
        candidates = resolve_candidates(select_candidate_entities(verdict), alias_index)
        candidate_tickers = frozenset(c["ticker"] for c in candidates)
        routed_jobs.append(
            {
                "article": article,
                "candidates_block": build_resolved_candidates_block(candidates),
                "active_narratives_block": stage_two_payload["active_narratives_block"],
                "active_catalysts_block": stage_two_payload["active_catalysts_block"],
                "candidate_tickers": candidate_tickers,
            }
        )

    if not routed_jobs:
        return 0

    extractions = await extract_articles(
        routed_jobs, universe_tickers=stage_two_payload["universe_tickers"]
    )
    counts = await persist_extractions(scan_date, extractions)
    return int(counts.get("articles_updated") or 0)


__all__ = [
    "ZERO_ROW_ALERT_THRESHOLD",
    "build_alias_index",
    "emit_stage1_pass_rate_alert",
    "emit_zero_row_alerts",
    "persist_extractions",
    "resolve_candidates",
    "run_news_v2_pass",
]
