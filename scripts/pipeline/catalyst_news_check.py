"""Catalyst news check — evaluator that matches recent articles to catalysts.

Pipeline layer (not data layer): fetches catalysts + articles from DB,
runs LLM-based matching (keyword fallback on failure), detects spikes,
and persists signals to catalyst_news_signals table.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date

from shared.database import get_db
from shared.neon.articles import list_articles
from shared.neon.catalysts import get_active_catalysts_db
from shared.observability import log_warn
from shared.rules.catalyst_news import (
    CatalystNewsSignal,
    build_signals,
    match_articles_to_catalysts,
)

logger = logging.getLogger(__name__)

_MATCH_MODEL = "google/gemma-4-26b-a4b-it"

_MATCH_SYSTEM_PROMPT = """\
Vietnamese stock market catalyst news matcher.

You receive a list of CATALYSTS (events being tracked) and a batch of NEWS ARTICLES.
Match ONLY articles that are specifically about the catalyst event itself.
Keyword overlap alone is insufficient — the article must discuss the actual event.

Return JSON: {"matches": [{"catalyst_key": "<key>", "article_indices": [<int>, ...]}]}
Only include catalysts that have at least one matching article.
If no articles match any catalyst, return {"matches": []}.
"""

_MATCH_JSON_SCHEMA: dict[str, object] = {
    "type": "json_schema",
    "json_schema": {
        "name": "catalyst_matches",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "catalyst_key": {"type": "string"},
                            "article_indices": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        },
                        "required": ["catalyst_key", "article_indices"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["matches"],
            "additionalProperties": False,
        },
    },
}


async def _match_articles_llm(
    articles: list[dict],
    catalysts: list[dict],
    batch_size: int = 15,
) -> tuple[dict[str, list[int]], str]:
    """LLM-based article-catalyst matching.

    Batches articles (default 15 per call), sends ALL catalysts in each batch.
    Falls back to keyword matching on any LLM failure.

    Returns:
        (matches_dict, method) where method is "llm" or "keyword_fallback".
    """
    from shared.llm import call_llm

    # Build catalyst reference block (sent in every batch)
    catalyst_lines: list[str] = []
    catalyst_key_set: set[str] = set()
    for catalyst in catalysts:
        catalyst_key = catalyst.get("catalyst_key") or catalyst.get("id") or ""
        if not catalyst_key:
            continue
        catalyst_key_set.add(catalyst_key)
        event = catalyst.get("event") or ""
        affected = catalyst.get("affected_tickers") or catalyst.get("affected") or []
        catalyst_lines.append(
            f"- key={catalyst_key} | event={event} | tickers={','.join(affected)}"
        )

    if not catalyst_lines:
        return {}, "llm"

    catalyst_block = "CATALYSTS:\n" + "\n".join(catalyst_lines)
    article_count = len(articles)

    async def _process_batch(batch_start: int) -> dict[str, list[int]]:
        """Process a single batch of articles against all catalysts."""
        batch = articles[batch_start : batch_start + batch_size]
        article_lines: list[str] = []
        for local_index, article in enumerate(batch):
            global_index = batch_start + local_index
            title = article.get("title") or ""
            description = article.get("short_description") or ""
            article_lines.append(f"[{global_index}] {title} — {description[:120]}")

        article_block = "ARTICLES:\n" + "\n".join(article_lines)
        user_prompt = f"{catalyst_block}\n\n{article_block}"

        raw_response = await asyncio.to_thread(
            call_llm,
            system_prompt=_MATCH_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_schema=_MATCH_JSON_SCHEMA,
            model=_MATCH_MODEL,
            max_tokens=2000,
        )

        batch_matches: dict[str, list[int]] = {}
        parsed = json.loads(raw_response)
        for match in parsed.get("matches") or []:
            matched_key = match.get("catalyst_key") or ""
            indices = match.get("article_indices") or []
            if matched_key not in catalyst_key_set:
                continue
            valid_indices = [
                idx for idx in indices if isinstance(idx, int) and 0 <= idx < article_count
            ]
            if valid_indices:
                batch_matches.setdefault(matched_key, []).extend(valid_indices)
        return batch_matches

    try:
        batch_starts = list(range(0, article_count, batch_size))
        batch_results = await asyncio.gather(*[_process_batch(start) for start in batch_starts])

        all_matches: dict[str, list[int]] = {}
        for batch_matches in batch_results:
            for catalyst_key, indices in batch_matches.items():
                all_matches.setdefault(catalyst_key, []).extend(indices)

        logger.info(
            "LLM matching: %d catalysts matched across %d articles (%d batches)",
            len(all_matches),
            article_count,
            len(batch_starts),
        )
        return all_matches, "llm"

    except Exception:
        logger.warning("LLM matching failed — falling back to keyword matching", exc_info=True)
        keyword_matches = match_articles_to_catalysts(articles, catalysts)
        return keyword_matches, "keyword_fallback"


async def _get_baselines(catalyst_keys: list[str]) -> dict[str, float]:
    """Load average article counts per catalyst from recent signal history.

    Returns {catalyst_key: avg_article_count} over last 7 days.
    """
    if not catalyst_keys:
        return {}
    db = await get_db()
    placeholders = ", ".join(f"${i + 1}" for i in range(len(catalyst_keys)))
    # SWI-201: baseline averages deduped (normalized-title) counts so the
    # spike threshold isn't inflated by a single recycled headline.
    # COALESCE(unique_article_count, article_count) covers historic rows
    # that pre-date the new column.
    rows = await db.fetch_all(
        f"""SELECT catalyst_key,
                   AVG(COALESCE(unique_article_count, article_count)) as avg_count
            FROM catalyst_news_signals
            WHERE catalyst_key IN ({placeholders})
              AND signal_date >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY catalyst_key""",
        *catalyst_keys,
    )
    return {row["catalyst_key"]: float(row["avg_count"] or 0) for row in rows}


async def check_catalyst_news(
    scan_date: date | None = None,
) -> tuple[list[CatalystNewsSignal], str, list[str]]:
    """Match recent articles to active catalysts and detect spikes.

    Returns (signals, match_method, checked_keys) — ``checked_keys`` is
    every active-catalyst key the run inspected, regardless of whether
    it produced an article hit. SWI-64: callers thread this into
    ``save_catalyst_news_signals`` so ``last_updated`` advances on
    zero-hit-but-checked rows too (otherwise the freshness monitor
    paints them permanently stale).
    """
    if scan_date is None:
        scan_date = date.today()

    # Load catalysts and articles in parallel
    catalysts_raw, articles = await asyncio.gather(
        get_active_catalysts_db(None),
        list_articles(scan_date),
    )
    checked_keys = [
        catalyst["catalyst_key"] for catalyst in catalysts_raw if catalyst.get("catalyst_key")
    ]

    if not catalysts_raw or not articles:
        logger.info(
            "Catalyst news check: %d catalysts, %d articles — nothing to match",
            len(catalysts_raw),
            len(articles),
        )
        return [], "llm", checked_keys

    # Run LLM matching (keyword fallback on failure)
    matches, match_method = await _match_articles_llm(articles, catalysts_raw)
    if not matches:
        logger.info("No catalyst-article matches found (method=%s)", match_method)
        return [], match_method, checked_keys

    # Load baselines for spike detection
    matched_keys = list(matches.keys())
    baselines = await _get_baselines(matched_keys)

    # Build signals with spike detection
    signals = build_signals(matches, articles, catalysts_raw, baselines)

    spike_count = sum(1 for signal in signals if signal["is_spike"])
    logger.info(
        "Catalyst news check: %d signals (%d spikes) from %d articles [%s]",
        len(signals),
        spike_count,
        len(articles),
        match_method,
    )

    return signals, match_method, checked_keys


async def save_catalyst_news_signals(
    signals: list[CatalystNewsSignal] | list[dict],
    scan_date: date | None = None,
    match_method: str = "keyword",
    checked_keys: list[str] | None = None,
) -> int:
    """Batch upsert catalyst news signals to DB. Returns count saved.

    SWI-64: ``checked_keys`` is the full set of catalysts the news-check
    run inspected. ``last_updated`` is refreshed for every checked key
    (signal-producing AND zero-hit), so the freshness monitor doesn't
    paint silently-checked rows permanently stale. When omitted, we
    fall back to the legacy behaviour (refresh signal-producers only).
    """
    signal_date = scan_date or date.today()
    db = await get_db()

    refresh_keys: list[str] = (
        list(checked_keys)
        if checked_keys is not None
        else [signal["catalyst_key"] for signal in signals]
    )

    rows = [
        (
            signal["catalyst_key"],
            signal_date,
            signal["article_count"],
            # SWI-201: deduped count for spike detection. Falls back to
            # raw article_count for older signals that pre-date the field.
            signal.get("unique_article_count", signal["article_count"]),
            signal["is_spike"],
            signal["sample_titles"],
            match_method,
        )
        for signal in signals
    ]

    try:
        if rows:
            await db.execute_many(
                """INSERT INTO catalyst_news_signals
                       (catalyst_key, signal_date, article_count, unique_article_count,
                        is_spike, sample_titles, match_method)
                   VALUES ($1, $2, $3, $4, $5, $6::text[], $7)
                   ON CONFLICT (catalyst_key, signal_date) DO UPDATE SET
                       article_count = EXCLUDED.article_count,
                       unique_article_count = EXCLUDED.unique_article_count,
                       is_spike = EXCLUDED.is_spike,
                       sample_titles = EXCLUDED.sample_titles,
                       match_method = EXCLUDED.match_method,
                       checked_at = NOW()""",
                rows,
            )
        # SWI-64: advance catalysts.last_updated for all checked keys, not
        # just signal-producers. Idempotent guard prevents clock-skew
        # rollback. AUDIT-2026-04-24-001 § 'Supporting — catalyst_news_signals
        # writeback'.
        if refresh_keys:
            await db.execute(
                """UPDATE catalysts
                       SET last_updated = $1
                     WHERE catalyst_key = ANY($2::text[])
                       AND (last_updated IS NULL OR last_updated < $1)""",
                signal_date,
                refresh_keys,
            )
        return len(rows)
    except Exception as exc:
        logger.warning("Failed to batch save %d signals: %s", len(rows), exc)
        log_warn(
            "CATALYST_SIGNAL_BATCH_SAVE_FAILED",
            scope="catalyst_news_check",
            row_count=len(rows),
            error=str(exc),
        )
        return 0
