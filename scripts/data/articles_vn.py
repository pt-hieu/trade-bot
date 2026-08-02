"""
Vietnamese article pipeline via vnstock_news RSS feeds.

Pipeline:
1. Fetch RSS articles from Lightsail API (vnstock_news)
2. Deduplicate by URL
3. Keyword pre-filter (remove obviously irrelevant: sports, health, etc.)
4. LLM relevance scoring (batch, light model)
5. LLM summarization of relevant articles (~500 chars)
6. Return search_results dict for DB insertion
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from shared.config import LLM_MODEL
from shared.llm import call_llm_with_json_parse
from shared.vnstock_client import fetch_news_articles

logger = logging.getLogger(__name__)


def _title_from_url(url: str) -> str:
    """Extract a readable title from URL slug when RSS title is missing."""
    path = urlparse(url).path
    slug = path.rsplit("/", 1)[-1] if "/" in path else path
    slug = re.sub(r"-d\d+\.html?$", "", slug)  # baodautu pattern
    slug = re.sub(r"-\d+-\d+\.htm$", "", slug)  # vietstock pattern
    slug = re.sub(r"\.htm[l]?$", "", slug)
    return slug.replace("-", " ").strip()[:200]


# Stock-news sites. Dropped 2026-04-30: vneconomy + baodautu — upstream RSS broken (404 / empty channel) → Lightsail emits empty-title shells.
DEFAULT_SITES = ["cafebiz", "vietstock", "vnexpress"]

# Keyword blocklist — articles matching these are never finance-relevant.
# Checked against lowercase title + short_description.
_BLOCKLIST_PATTERNS = re.compile(
    r"|".join(
        [
            # Sports (Vietnamese + English)
            r"bóng đá",
            r"thể thao",
            r"world cup",
            r"fifa",
            r"la liga",
            r"premier league",
            r"champions league",
            r"serie a",
            r"bundesliga",
            r"barca",
            r"barcelona",
            r"real madrid",
            r"man city",
            r"man utd",
            r"chelsea",
            r"arsenal",
            r"liverpool",
            r"ngoại hạng anh",
            r"v-league",
            r"đội tuyển",
            r"huấn luyện viên",
            r"cầu thủ",
            r"trượt băng",
            r"quần vợt",
            r"tennis",
            r"olympic",
            r"sea games",
            r"nba",
            r"f1\b",
            # Health / Lifestyle
            r"giảm cân",
            r"sức khỏe",
            r"thói quen.*lành mạnh",
            r"tập thể dục",
            r"dinh dưỡng",
            r"vitamin",
            r"bệnh viện",
            r"triệu chứng",
            r"thuốc chữa",
            # Education
            r"thủ khoa",
            r"tuyển sinh",
            r"đại học.*điểm",
            r"điểm tuyệt đối",
            r"kỳ thi",
            r"sinh viên.*đạt",
            # Traffic / Accidents
            r"tai nạn giao thông",
            r"xe ba gác",
            r"xe tải.*lật",
            r"đâm.*xe",
            r"vượt ẩu",
            r"va chạm.*giao thông",
            # Entertainment / Celebrities
            r"nghệ sĩ",
            r"ca sĩ",
            r"diễn viên",
            r"phim.*chiếu",
            r"gameshow",
            r"truyền hình thực tế",
            # Lifestyle / Tech tips (non-finance)
            r"dán màn hình",
            r"mẹo.*laptop",
            r"điện thoại.*mẹo",
            r"công thức nấu",
            r"món ăn.*ngon",
            r"du lịch.*check.?in",
            # Weather / Nature
            r"dự báo thời tiết",
            r"bão số",
            r"lũ lụt",
            # Crime (non-financial)
            r"phạm nhân",
            r"tù nhân",
            r"trại giam",
        ]
    ),
    re.IGNORECASE,
)

RELEVANCE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "relevance_scores",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "score": {"type": "integer"},
                        },
                        "required": ["index", "score"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["scores"],
            "additionalProperties": False,
        },
    },
}

SUMMARY_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "summaries",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "summaries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "summary": {"type": "string"},
                        },
                        "required": ["index", "summary"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["summaries"],
            "additionalProperties": False,
        },
    },
}


def pre_filter(articles: list[dict]) -> list[dict]:
    """Remove obviously irrelevant articles via keyword blocklist.

    Saves LLM tokens by filtering sports, health, education, traffic, etc.
    before sending to LLM scoring.
    """
    kept = []
    for a in articles:
        text = ((a.get("title") or "") + " " + (a.get("short_description") or "")).lower()
        if _BLOCKLIST_PATTERNS.search(text):
            continue
        kept.append(a)
    return kept


def extract_domain(url: str) -> str:
    """Extract domain from URL, stripping 'www.' prefix."""
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def deduplicate_by_url(articles: list[dict]) -> list[dict]:
    """Deduplicate articles by URL. Preserves first occurrence."""
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for article in articles:
        url = article.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(article)
    return unique


def _score_relevance(
    articles: list[dict],
    watchlist: dict,
    holdings: list,
    min_score: int = 6,
) -> dict[int, int]:
    """Batch score articles for trading relevance. Returns {index: score}."""
    all_tickers = [t for sector in watchlist.values() for t in sector]
    seen_holding: list[str] = []
    for slice_row in holdings or []:
        ticker = slice_row.get("ticker")
        if ticker and ticker not in seen_holding:
            seen_holding.append(ticker)
    holding_tickers = seen_holding

    scored = {}
    batch_size = 20

    for batch_start in range(0, len(articles), batch_size):
        batch = articles[batch_start : batch_start + batch_size]
        article_lines = []
        for i, a in enumerate(batch):
            idx = batch_start + i
            title = (a.get("title") or "")[:100]
            desc = (a.get("short_description") or "")[:150]
            article_lines.append(f"[{idx}] {title} | {desc}")

        prompt = f"""Score these Vietnamese news articles for stock trading relevance (0-10).
Be STRICT — only finance, stock market, and economy news should score 6+.

Holdings: {", ".join(holding_tickers)}
Watchlist: {", ".join(all_tickers)}
Sectors: {", ".join(watchlist.keys())}

Scoring guide:
- 8-10: Directly mentions watchlist stocks, their earnings, dividends, or price targets
- 6-7: Specific sector policy/regulation affecting watchlist sectors (banking, real estate, tech, steel, infrastructure)
- 4-5: General Vietnam economy, interest rates, FDI, trade policy, stock market overview
- 2-3: Tangentially related (general business, non-VN markets, broad macro)
- 0-1: NOT finance — sports, health, education, traffic, entertainment, lifestyle, food, weather, crime

IMPORTANT: Score 0 for anything about sports teams, athletes, health tips, traffic accidents, school exams, celebrities, recipes, or travel. These are NEVER relevant to stock trading.

Articles:
{chr(10).join(article_lines)}

Return scores for each article index."""

        try:
            data = call_llm_with_json_parse(
                "Score articles for Vietnamese stock trading relevance. Return JSON only.",
                prompt,
                json_schema=RELEVANCE_SCHEMA,
                model=LLM_MODEL,
                max_attempts=2,
                backoff_seconds=5,
                on_attempt_error=lambda attempt, error, batch_start=batch_start: logger.warning(
                    "Relevance scoring batch %d failed (attempt %d): %s",
                    batch_start,
                    attempt + 1,
                    error,
                ),
            )
            for item in data.get("scores", []):
                scored[item["index"]] = item["score"]
        except Exception as scoring_error:
            logger.warning(
                "Relevance scoring batch %d failed after 2 attempts: %s "
                "— defaulting to pass-through (score=%d)",
                batch_start,
                scoring_error,
                min_score,
            )
            # Pass-through: default to min_score so articles survive to DB
            for i in range(batch_start, batch_start + len(batch)):
                scored.setdefault(i, min_score)

    return scored


def _summarize_articles(articles: list[tuple[int, dict]]) -> dict[int, str]:
    """Batch summarize article content to ~500 chars. Returns {index: summary}."""
    summaries = {}
    batch_size = 5  # Smaller batches for summarization (content is longer)

    for batch_start in range(0, len(articles), batch_size):
        batch = articles[batch_start : batch_start + batch_size]
        article_blocks = []
        for _i, (idx, a) in enumerate(batch):
            content = (
                a.get("markdown_content")
                or a.get("content")
                or a.get("short_description")
                or a.get("description")
                or ""
            )[:2000]
            title = a.get("title") or ""
            if len(content) < 30:
                logger.warning(
                    "Short content (%d chars) for '%s', using title as summary",
                    len(content),
                    title[:60],
                )
                summaries[idx] = title
                continue
            article_blocks.append(f"[{idx}] Title: {title}\nContent: {content}")

        prompt = f"""Summarize each article in ~500 characters (Vietnamese or English, match source language).
Focus on: stock impact, numbers, dates, companies mentioned.

{chr(10).join(article_blocks)}

Return a summary for each article index."""

        try:
            data = call_llm_with_json_parse(
                "Summarize financial news articles concisely. Return JSON only.",
                prompt,
                json_schema=SUMMARY_SCHEMA,
                model=LLM_MODEL,
                max_attempts=2,
                backoff_seconds=5,
                on_attempt_error=lambda attempt, error, batch_start=batch_start: logger.warning(
                    "Summarization batch %d failed (attempt %d): %s",
                    batch_start,
                    attempt + 1,
                    error,
                ),
            )
            for item in data.get("summaries", []):
                summaries[item["index"]] = item["summary"]
        except Exception as summarization_error:
            logger.warning(
                "Summarization batch %d failed after 2 attempts: %s — using titles as fallback",
                batch_start,
                summarization_error,
            )
            for idx, article in batch:
                summaries.setdefault(idx, article.get("title") or "")

    return summaries


async def fetch_vietnamese_articles(
    watchlist: dict,
    holdings: list,
    output_dir: Path,
    min_score: int = 6,
) -> dict:
    """Fetch and process Vietnamese RSS articles.

    Returns:
        Dict matching insert_articles() format:
        {query_name: {query, status, count, skipped, articles: [...]}}
    """
    print("Fetching Vietnamese articles via RSS...")

    # Step 1: Fetch raw RSS — re-raise so news_pipeline_v2.py can alert via Telegram
    raw_articles = await fetch_news_articles(sites=DEFAULT_SITES, limit=20)

    print(f"  Fetched {len(raw_articles)} raw articles from {len(DEFAULT_SITES)} sites")

    # Step 2: Deduplicate by URL
    unique = deduplicate_by_url(raw_articles)
    print(f"  {len(unique)} unique articles after dedup")

    # Step 3: Keyword pre-filter (remove obviously irrelevant)
    filtered = pre_filter(unique)
    pre_filtered = len(unique) - len(filtered)
    if pre_filtered:
        print(f"  {pre_filtered} articles removed by keyword pre-filter")
    unique = filtered

    # Step 4: LLM relevance scoring (offload sync LLM calls to thread)
    print("  Scoring relevance...")
    scores = await asyncio.to_thread(_score_relevance, unique, watchlist, holdings, min_score)

    # Step 5: Filter by score
    relevant = [(i, a) for i, a in enumerate(unique) if scores.get(i, 0) >= min_score]
    skipped_total = len(unique) - len(relevant)
    print(f"  {len(relevant)} relevant (score >= {min_score}), {skipped_total} skipped")

    # Step 6: LLM summarize relevant articles (offload sync LLM calls to thread)
    print("  Summarizing relevant articles...")
    summaries = await asyncio.to_thread(_summarize_articles, relevant)

    # Step 7: Build search_results dict grouped by site
    search_results = {}

    for idx, article in relevant:
        site = article.get("site", "unknown")
        query_name = f"rss-{site}"
        domain = extract_domain(article.get("url", ""))
        summary = summaries.get(idx, (article.get("short_description") or "")[:500])

        if query_name not in search_results:
            search_results[query_name] = {
                "query": f"RSS feed: {domain or site}",
                "status": "success",
                "count": 0,
                "skipped": 0,
                "articles": [],
            }

        title = article.get("title") or _title_from_url(article.get("url", ""))
        search_results[query_name]["articles"].append(
            {
                "title": title,
                "url": article.get("url", ""),
                "source": domain,
                "domain": domain,
                "summary": summary,
                "summary_length": len(summary),
                "description": article.get("short_description", ""),
                "publish_time": article.get("publish_time") or article.get("lastmod"),
            }
        )
        search_results[query_name]["count"] += 1

    # Distribute skipped counts proportionally
    for qn in search_results:
        site = qn.replace("rss-", "")
        site_total = sum(1 for a in unique if a.get("site") == site)
        site_kept = search_results[qn]["count"]
        search_results[qn]["skipped"] = site_total - site_kept

    total = sum(r["count"] for r in search_results.values())
    print(f"  Processed {total} relevant articles")

    # Save search results metadata
    output_file = output_dir / "search-results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(search_results, f, indent=2, ensure_ascii=False)

    return search_results
