#!/usr/bin/env python3
"""News Pipeline v2 — two-stage retrieval-grounded extractor (SWI-241).

Replaces the broken 5-stage chain (filter → tag → sentiment → examiner →
narrative_labeler) with a tight two-stage flow:

* Stage 1 (``minimax/minimax-m2.7``) — relevance gate + entity-candidate
  spotter. Drops obvious non-VN articles and emits raw entity tokens.
* Stage 2 (``z-ai/glm-5``) — extractor + classifier. Receives candidates-
  only context (≤10 rows resolved against ``company_profiles.aliases``)
  plus active narratives + active catalysts (last 14 days). Outputs
  affected_tickers + narrative attachment + catalyst attachment +
  sentiment + capital_event in one call.

Persistence + paging live in ``pipeline/news_v2_persist.py`` so the
intraday catalyst-check entry point reuses the same writer.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import logfire

sys.path.insert(0, str(Path(__file__).parent))

from data.articles_intl import INTL_QUERY_PREFIX  # noqa: E402
from shared.database import Database, close_db, get_db  # noqa: E402
from shared.market_calendar import is_trading_day  # noqa: E402
from shared.observability import (  # noqa: E402
    configure_observability,
    shutdown_observability,
    span,
)
from shared.session import init_session  # noqa: E402
from shared.telegram import send_telegram_error  # noqa: E402
from shared.vn_universe import load_vn_universe_async  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_args() -> date:
    parser = argparse.ArgumentParser(description="News Pipeline v2: two-stage extractor")
    parser.add_argument("--date", type=str, help="Scan date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    if args.date:
        return datetime.strptime(args.date, "%Y-%m-%d").date()
    return date.today()


async def _phase_zero_ingest(scan_date: date) -> list[dict]:
    """Fetch missing articles, then rehydrate the full set from the DB.

    The disk-cache short-circuit was load-bearing on the GH Actions runner
    only when a previous commit had landed ``research/{date}/*.json``; on a
    fresh runner those files don't exist and the v1 path returned ``{}``.
    Always rehydrating from the DB drops that dependency and gives every
    article its canonical UUID — Stage 1 verdict UPDATEs need a non-None id.
    """
    from data.articles import articles_exist_in_db, search_articles
    from data.articles_intl import fetch_international_articles
    from shared.neon import (
        get_portfolio_holdings,
        get_swing_watchlist,
        insert_articles,
        load_articles_for_scan_date,
    )

    research_base = Path(__file__).parent.parent / "research"
    output_dir = research_base / str(scan_date)
    output_dir.mkdir(parents=True, exist_ok=True)

    watchlist, holdings = await asyncio.gather(get_swing_watchlist(), get_portfolio_holdings())

    vn_in_db, intl_in_db = await asyncio.gather(
        articles_exist_in_db(scan_date, min_count=5),
        articles_exist_in_db(scan_date, query_prefix=INTL_QUERY_PREFIX, min_count=2),
    )

    if vn_in_db and not intl_in_db:
        intl_results = await fetch_international_articles(output_dir)
        if intl_results:
            await insert_articles(scan_date, intl_results)
    elif intl_in_db and not vn_in_db:
        from data.articles_vn import fetch_vietnamese_articles

        vn_results = await fetch_vietnamese_articles(watchlist, holdings, output_dir)
        if vn_results:
            await insert_articles(scan_date, vn_results)
    elif not vn_in_db and not intl_in_db:
        search_results = await search_articles(watchlist, holdings, output_dir)
        await insert_articles(scan_date, search_results)

    return await load_articles_for_scan_date(scan_date)


async def _run_pipeline(scan_date: date) -> None:
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
    from pipeline.news_v2_persist import (
        build_alias_index,
        emit_stage1_pass_rate_alert,
        emit_zero_row_alerts,
        persist_extractions,
        resolve_candidates,
    )
    from shared.neon import get_universe_with_aliases

    print(f"\n{'=' * 60}\nNews Pipeline v2 — {scan_date}\n{'=' * 60}\n")

    with span("news_pipeline_v2", scan_date=str(scan_date)):
        await load_vn_universe_async()
        articles = await _phase_zero_ingest(scan_date)
        logfire.info(
            "news_pipeline_v2_phase_zero_complete",
            scan_date=str(scan_date),
            article_count=len(articles),
        )
        if not articles:
            if not is_trading_day(scan_date):
                logfire.info("news_pipeline_v2_holiday_skip_phase_zero", scan_date=str(scan_date))
                return
            logfire.warning(
                "news_pipeline_v2_zero_articles",
                scan_date=str(scan_date),
                phase="phase_zero",
            )
            raise RuntimeError(f"news_pipeline_v2: 0 articles after Phase 0 ingest for {scan_date}")

        # Single universe fetch sliced for Stage 1 (top 200) + Stage 2
        # alias index + universe-membership set.
        universe_rows = await get_universe_with_aliases(limit=2000)
        stage_one = await build_stage_one_payload(universe_limit=200, universe_rows=universe_rows)
        stage_two_payload, _, _ = await build_stage_two_static_payload(universe_rows=universe_rows)
        alias_index = build_alias_index(universe_rows)
        print(
            f"Phase 0: {len(articles)} articles, "
            f"{stage_one['universe_size']} universe entries, "
            f"{len(alias_index)} alias keys."
        )

        with span("news_v2_stage1"):
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

        passed = len(routed_jobs)
        print(f"Stage 1: {passed}/{len(articles)} routed to Stage 2; drops={dict(drops)}")
        await emit_stage1_pass_rate_alert(passed, len(articles))
        logfire.info(
            "news_pipeline_v2_stage1_complete",
            scan_date=str(scan_date),
            article_count=len(articles),
            routed=passed,
            drops=dict(drops),
        )

        if not routed_jobs:
            if not is_trading_day(scan_date):
                logfire.info("news_pipeline_v2_holiday_skip_stage1", scan_date=str(scan_date))
                return
            pass_rate = float(passed) / max(len(articles), 1)
            logfire.warning(
                "news_pipeline_v2_zero_stage1_routed",
                scan_date=str(scan_date),
                articles=len(articles),
                pass_rate=pass_rate,
            )
            if len(articles) >= 20:
                # 0/20+ is a regression, not a quiet news day.
                raise RuntimeError(
                    f"news_pipeline_v2: 0/{len(articles)} articles passed Stage 1 for {scan_date}"
                )
            return

        with span("news_v2_stage2"):
            extractions = await extract_articles(
                routed_jobs, universe_tickers=stage_two_payload["universe_tickers"]
            )
        logfire.info(
            "news_pipeline_v2_stage2_complete",
            scan_date=str(scan_date),
            extraction_count=len(extractions),
        )

        with span("news_v2_persist"):
            counts = await persist_extractions(scan_date, extractions)
        print(f"Stage 2: {counts}")

        empty_rate = await db.fetch_val(
            "SELECT AVG(CASE WHEN array_length(affected_tickers, 1) IS NULL THEN 1.0 ELSE 0 END) "
            "FROM articles WHERE search_id IN (SELECT id FROM article_searches WHERE scan_date = $1)",
            scan_date,
        )
        if empty_rate is not None and float(empty_rate) > 0.7:
            logfire.warning(
                "news_v2_high_empty_tickers_rate",
                scan_date=str(scan_date),
                rate=float(empty_rate),
            )

        logfire.info(
            "news_pipeline_v2_persist_complete",
            scan_date=str(scan_date),
            counts=dict(counts),
        )

        # Lifecycle refreshes — operate on v2 rows via the read-side filter.
        from shared.neon.catalysts import refresh_catalyst_lifecycle
        from shared.neon.narratives import (
            refresh_all_conviction_scores,
            refresh_narrative_maturity,
            refresh_related_catalysts,
        )

        await asyncio.gather(
            refresh_catalyst_lifecycle(),
            refresh_all_conviction_scores(),
            refresh_narrative_maturity(),
            refresh_related_catalysts(),
        )

        # Zero-row alert MUST propagate — _main_async wraps with
        # send_telegram_error + raise. A silent swallow here is what hid
        # the 10-day outage that prompted this rewrite.
        await emit_zero_row_alerts()

        print(f"\n{'=' * 60}\nNews Pipeline v2 — Complete\n{'=' * 60}\n")


async def _main_async() -> None:
    scan_date = _parse_args()
    try:
        async with Database():
            from shared.trading_config import init_trading_config

            await init_trading_config()
            await _run_pipeline(scan_date)
    except Exception as exc:
        error_msg = f"News Pipeline v2 failed: {exc}"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    finally:
        await close_db()
        shutdown_observability()


def main() -> None:
    configure_observability()
    init_session("news_v2")
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
