"""Batch enrichment data loader — fetch all shared data once for context injection.

Replaces per-agent tool calls with a single parallel fetch at pipeline start.
Data stored in EnrichmentData, passed through PipelineContext, formatted by
context_blocks.py formatters.

See: .claude/skills/agent-development/instructions.md § Context Injection
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger(__name__)

# Cap concurrent API calls to avoid overwhelming vnstock API
_API_SEMAPHORE = asyncio.Semaphore(5)


@dataclass
class EnrichmentData:
    """Batch-fetched enrichment data for all pipeline tickers.

    Loaded once in Phase 0, consumed by context_blocks formatters.
    """

    ticker_flow: dict[str, dict] = field(default_factory=dict)
    ticker_insider: dict[str, list[dict]] = field(default_factory=dict)
    ticker_rs: dict[str, float] = field(default_factory=dict)
    company_profiles: dict[str, dict] = field(default_factory=dict)
    ticker_beliefs: dict[str, list[dict]] = field(default_factory=dict)
    catalyst_preview: dict = field(default_factory=dict)
    articles: list[dict] = field(default_factory=list)
    active_narratives: list[dict] = field(default_factory=list)
    longterm_config: dict[str, dict] = field(default_factory=dict)
    # Per-ticker indexes computed once in Phase 0 so format_ticker_briefings (called
    # 3+ times per agent pass) doesn't rebuild them per call.
    articles_by_ticker: dict[str, list[dict]] = field(default_factory=dict)
    narratives_by_ticker: dict[str, list[dict]] = field(default_factory=dict)
    # Pre-fetched data for inject-instead-of-tool (audit cleanup)
    belief_accuracy: dict[str, str] = field(default_factory=dict)
    learnings_cache: dict[str, dict] = field(default_factory=dict)
    recent_trades_prose: str = ""
    # Per-held-ticker thesis prose + 3-section fundamental analysis prose.
    # Eliminates the on-demand portfolio.get_thesis / fundamental.get_full_analysis
    # tool round-trips from positions_thesis / positions_value (2026-04-28 fix).
    position_thesis_prose: dict[str, str] = field(default_factory=dict)
    position_valuation_prose: dict[str, str] = field(default_factory=dict)


async def batch_fetch_enrichment(
    all_tickers: list[str],
    scan_date: date,
    holdings: list[dict] | None = None,
    longterm_tickers: list[str] | None = None,
    longterm_watchlist: dict[str, dict] | None = None,
) -> EnrichmentData:
    """Fetch all enrichment data in parallel for context injection.

    Args:
        all_tickers: All tickers to fetch data for (portfolio + watchlist + sector)
        scan_date: Analysis date
        holdings: Current list[HoldingData] slices (for catalyst preview)
        longterm_tickers: Longterm watchlist tickers (for catalyst preview)
        longterm_watchlist: Pre-loaded watchlist dict from load_db_context — avoids
            a second Neon round trip when the pipeline already has it on hand.

    Returns:
        EnrichmentData with all batch-fetched data. Missing data = empty defaults.
    """
    enrichment = EnrichmentData()
    if longterm_watchlist:
        enrichment.longterm_config = {
            ticker.upper(): entry for ticker, entry in longterm_watchlist.items()
        }

    # Agent keys that need belief accuracy pre-fetched for calibration injection
    calibration_agent_keys = [
        "positions_technical",
        "positions_thesis",
        "positions_value",
        "sector_technical",
        "sector_enrichment",
        "sector_news",
    ]
    # Fixed learnings queries to pre-fetch (query_key, kwargs)
    learnings_queries: list[tuple[str, dict]] = [
        ("summary", {"query": "summary"}),
        ("calibration", {"query": "calibration"}),
        ("macro_patterns", {"query": "macro_patterns"}),
        ("rotation_patterns", {"query": "rotation_patterns"}),
        ("midday_insights", {"query": "midday_insights"}),
        ("sector_bias", {"query": "sector_bias"}),
        ("ticker_accuracy", {"query": "ticker_accuracy"}),
    ]

    from .enrichment_position_data import (
        extract_held_tickers,
        fetch_position_thesis_prose,
        fetch_position_valuation_prose,
    )

    held_tickers = extract_held_tickers(holdings)

    results = await asyncio.gather(
        _fetch_all_flow(all_tickers, scan_date),
        _fetch_all_insider(all_tickers),
        _fetch_relative_strength(all_tickers),
        _fetch_company_profiles(all_tickers),
        _fetch_all_beliefs(all_tickers, scan_date),
        _fetch_catalyst_preview(holdings, longterm_tickers),
        _fetch_articles(scan_date),
        _fetch_belief_accuracy(calibration_agent_keys),
        _fetch_learnings_batch(learnings_queries),
        _fetch_recent_trades(),
        _fetch_active_narratives(all_tickers),
        fetch_position_thesis_prose(held_tickers),
        fetch_position_valuation_prose(held_tickers),
        return_exceptions=True,
    )

    (
        flow_result,
        insider_result,
        rs_result,
        profiles_result,
        beliefs_result,
        catalyst_result,
        articles_result,
        belief_accuracy_result,
        learnings_result,
        trades_result,
        narratives_result,
        thesis_prose_result,
        valuation_prose_result,
    ) = results

    if isinstance(flow_result, dict):
        enrichment.ticker_flow = flow_result
    elif isinstance(flow_result, Exception):
        logger.warning("Batch flow fetch failed: %s", flow_result)

    if isinstance(insider_result, dict):
        enrichment.ticker_insider = insider_result
    elif isinstance(insider_result, Exception):
        logger.warning("Batch insider fetch failed: %s", insider_result)

    if isinstance(rs_result, dict):
        enrichment.ticker_rs = {
            ticker: value for ticker, value in rs_result.items() if value is not None
        }
    elif isinstance(rs_result, Exception):
        logger.warning("Batch RS fetch failed: %s", rs_result)

    if isinstance(profiles_result, dict):
        enrichment.company_profiles = profiles_result
    elif isinstance(profiles_result, Exception):
        logger.warning("Batch profiles fetch failed: %s", profiles_result)

    if isinstance(beliefs_result, dict):
        enrichment.ticker_beliefs = beliefs_result
    elif isinstance(beliefs_result, Exception):
        logger.warning("Batch beliefs fetch failed: %s", beliefs_result)

    if isinstance(catalyst_result, dict):
        enrichment.catalyst_preview = catalyst_result
    elif isinstance(catalyst_result, Exception):
        logger.warning("Batch catalyst fetch failed: %s", catalyst_result)

    if isinstance(articles_result, list):
        enrichment.articles = articles_result
    elif isinstance(articles_result, Exception):
        logger.warning("Batch articles fetch failed: %s", articles_result)

    if isinstance(belief_accuracy_result, dict):
        enrichment.belief_accuracy = belief_accuracy_result
    elif isinstance(belief_accuracy_result, Exception):
        logger.warning("Batch belief accuracy fetch failed: %s", belief_accuracy_result)

    if isinstance(learnings_result, dict):
        enrichment.learnings_cache = learnings_result
    elif isinstance(learnings_result, Exception):
        logger.warning("Batch learnings fetch failed: %s", learnings_result)

    if isinstance(trades_result, str):
        enrichment.recent_trades_prose = trades_result
    elif isinstance(trades_result, Exception):
        logger.warning("Batch trades fetch failed: %s", trades_result)

    if isinstance(narratives_result, list):
        enrichment.active_narratives = narratives_result
    elif isinstance(narratives_result, Exception):
        logger.warning("Batch narratives fetch failed: %s", narratives_result)

    if isinstance(thesis_prose_result, dict):
        enrichment.position_thesis_prose = thesis_prose_result
    elif isinstance(thesis_prose_result, Exception):
        logger.warning("Batch position thesis fetch failed: %s", thesis_prose_result)

    if isinstance(valuation_prose_result, dict):
        enrichment.position_valuation_prose = valuation_prose_result
    elif isinstance(valuation_prose_result, Exception):
        logger.warning("Batch position valuation fetch failed: %s", valuation_prose_result)

    # Build per-ticker indexes once here so format_ticker_briefings callers (which
    # run many times per pipeline) don't rebuild them on every call.
    from .context_blocks_ticker_news import (
        index_articles_by_ticker,
        index_narratives_by_ticker,
    )

    enrichment.articles_by_ticker = index_articles_by_ticker(enrichment.articles)
    enrichment.narratives_by_ticker = index_narratives_by_ticker(enrichment.active_narratives)

    fetched_counts = (
        f"flow={len(enrichment.ticker_flow)}, "
        f"insider={len(enrichment.ticker_insider)}, "
        f"rs={len(enrichment.ticker_rs)}, "
        f"profiles={len(enrichment.company_profiles)}, "
        f"beliefs={len(enrichment.ticker_beliefs)}, "
        f"catalysts={len(enrichment.catalyst_preview.get('upcoming_week', []))}, "
        f"articles={len(enrichment.articles)}, "
        f"narratives={len(enrichment.active_narratives)}, "
        f"longterm={len(enrichment.longterm_config)}, "
        f"belief_accuracy={len(enrichment.belief_accuracy)}, "
        f"learnings={len(enrichment.learnings_cache)}, "
        f"trades={'yes' if enrichment.recent_trades_prose else 'no'}"
    )
    logger.info(
        "Enrichment batch fetch complete for %d tickers: %s", len(all_tickers), fetched_counts
    )

    return enrichment


# ── Per-Data-Type Fetchers ───────────────────────────────────────────────


async def _fetch_with_semaphore(coro):
    """Run a coroutine with rate-limiting semaphore."""
    async with _API_SEMAPHORE:
        return await coro


async def _fetch_all_flow(tickers: list[str], scan_date: date) -> dict[str, dict]:
    """Fetch daily flow for all tickers in one batch API call."""
    from shared.api.enrichment import get_daily_flow_batch

    batch = await get_daily_flow_batch(tickers, scan_date)
    return {ticker: flow for ticker, flow in batch.items() if flow}


async def _fetch_all_insider(tickers: list[str]) -> dict[str, list[dict]]:
    """Fetch insider transactions for all tickers in one batch API call."""
    from shared.api.enrichment import get_recent_insider_transactions_batch

    batch = await get_recent_insider_transactions_batch(tickers)
    return {ticker: txs for ticker, txs in batch.items() if txs}


async def _fetch_relative_strength(tickers: list[str]) -> dict[str, float | None]:
    """Fetch 20d relative strength for all tickers (batch-capable)."""
    from shared.api.prices import compute_relative_strength

    return await compute_relative_strength(tickers, window=20)


async def _fetch_company_profiles(tickers: list[str]) -> dict[str, dict]:
    """Fetch company profiles from DB in one query."""
    from shared.neon.company_profiles import get_profiles_batch

    profiles_list = await get_profiles_batch(tickers)
    return {profile["ticker"]: profile for profile in profiles_list if profile.get("ticker")}


async def _fetch_all_beliefs(tickers: list[str], scan_date: date) -> dict[str, list[dict]]:
    """Fetch prior beliefs for all tickers across all agents (one DB query)."""
    from shared.neon.beliefs import get_all_prior_beliefs_by_ticker

    return await get_all_prior_beliefs_by_ticker(scan_date, tickers)


async def _fetch_catalyst_preview(
    holdings: list[dict] | None, longterm_tickers: list[str] | None
) -> dict:
    """Fetch catalyst preview cross-referenced with holdings."""
    from agents.tools.catalyst_preview import compute_catalyst_preview

    return await compute_catalyst_preview(
        holdings=holdings or [],
        lt_tickers=longterm_tickers or [],
    )


async def _fetch_articles(scan_date: date) -> list[dict]:
    """Fetch article summaries for the scan date.

    Uses list_articles_range so the payload includes affected_tickers, summary,
    and sentiment_score — enabling per-ticker filtering in format_ticker_briefing.
    Summaries are truncated at fetch time so the enrichment payload doesn't balloon.
    """
    from datetime import timedelta

    from shared.neon.articles import list_articles_range

    start = scan_date - timedelta(days=7)
    try:
        articles = await list_articles_range(start, scan_date)
    except Exception as error:
        logger.warning("Article range fetch failed %s..%s: %s", start, scan_date, error)
        return []

    trimmed: list[dict] = []
    for article in articles:
        if "error" in article:
            continue
        summary = article.get("summary")
        if isinstance(summary, str) and len(summary) > 200:
            article = {**article, "summary": summary[:200]}
        trimmed.append(article)
    return trimmed


# ── Inject-instead-of-tool Fetchers (audit cleanup) ──────────────────────


async def _fetch_belief_accuracy(agent_keys: list[str]) -> dict[str, str]:
    """Pre-fetch belief accuracy for agents that need calibration injection.

    Returns dict mapping agent_key to accuracy prose string.
    """
    from agents.tools.beliefs import tool_get_belief_accuracy

    async def _fetch_one(agent_key: str) -> tuple[str, str]:
        try:
            result = await tool_get_belief_accuracy(agent_key, perspective="self")
            return (agent_key, result)
        except Exception as error:
            logger.warning("Belief accuracy fetch failed for %s: %s", agent_key, error)
            return (agent_key, "Belief accuracy data unavailable. Use your best judgment.")

    results = await asyncio.gather(*[_fetch_one(key) for key in agent_keys])
    return dict(results)


async def _fetch_learnings_batch(
    queries: list[tuple[str, dict]],
) -> dict[str, dict]:
    """Pre-fetch learnings for known fixed-query params.

    Args:
        queries: List of (query_key, kwargs) pairs for get_learnings_async.

    Returns dict mapping query_key to learnings result dict.
    """
    from agents.tools.portfolio_learnings import get_learnings_async

    async def _fetch_one(query_key: str, kwargs: dict) -> tuple[str, dict]:
        try:
            result = await get_learnings_async(**kwargs)
            return (query_key, result)
        except Exception as error:
            logger.warning("Learnings fetch failed for %s: %s", query_key, error)
            return (query_key, {"error": str(error)})

    results = await asyncio.gather(*[_fetch_one(key, kw) for key, kw in queries])
    return dict(results)


async def _fetch_recent_trades(limit: int = 5) -> str:
    """Pre-fetch recent trades as prose string."""
    from agents.tools.portfolio import get_recent_trades_async

    result = await get_recent_trades_async(limit=limit)
    return result.get("prose") or str(result)


async def _fetch_active_narratives(tickers: list[str]) -> list[dict]:
    """Pre-fetch mature active narratives scoped to pipeline tickers.

    Applies the same maturity filter as `agents.tools.narratives.get_active_narratives_async`
    so developing / single-article noise doesn't leak into per-ticker briefings.
    """
    from shared.neon.narratives import get_active_narratives

    narratives = await get_active_narratives(tickers or None)
    return [
        narrative
        for narrative in narratives
        if (narrative.get("maturity") or "").lower() in ("confirmed", "mature")
    ]
