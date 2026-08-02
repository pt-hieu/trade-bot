"""LLM relevance scoring (macro/geo focused — no summarization)."""

from __future__ import annotations

import logging

from shared.config import LLM_MODEL
from shared.llm import call_llm_with_json_parse

from ..articles_vn import RELEVANCE_SCHEMA

logger = logging.getLogger(__name__)


def _score_intl_relevance(articles: list[dict], min_score: int = 5) -> dict[int, int]:
    """Batch score international articles for macro/geopolitical relevance."""
    scored: dict[int, int] = {}
    batch_size = 20

    for batch_start in range(0, len(articles), batch_size):
        batch = articles[batch_start : batch_start + batch_size]
        article_lines = []
        for i, article in enumerate(batch):
            idx = batch_start + i
            title = (article.get("title") or "")[:120]
            description = (article.get("short_description") or "")[:200]
            article_lines.append(f"[{idx}] {title} | {description}")

        prompt = f"""Score these international news articles for relevance to Vietnamese stock trading (0-10).
Focus on MACRO IMPACT — how would this news affect Vietnamese equities, commodities, or currency?

Scoring guide:
- 8-10: Direct commodity price impact (oil, steel, copper), Fed/ECB rate decision, trade sanctions affecting Vietnam/ASEAN
- 6-7: USD/DXY moves, China economic data, OPEC decisions, global supply chain disruption
- 4-5: US economic data (jobs, CPI, GDP), emerging market trends, EU trade policy
- 2-3: US domestic policy with no Asia/trade angle, general business profiles
- 0-1: NOT macro-relevant — sports, celebrities, local news, weather, entertainment

Articles:
{chr(10).join(article_lines)}

Return scores for each article index."""

        try:
            data = call_llm_with_json_parse(
                "Score international articles for macro relevance to Vietnamese stocks. Return JSON only.",
                prompt,
                json_schema=RELEVANCE_SCHEMA,
                model=LLM_MODEL,
                max_attempts=2,
                backoff_seconds=5,
                on_attempt_error=lambda attempt, error, batch_start=batch_start: logger.warning(
                    "Intl scoring batch %d failed (attempt %d): %s",
                    batch_start,
                    attempt + 1,
                    error,
                ),
            )
            for item in data.get("scores", []):
                scored[item["index"]] = item["score"]
        except Exception as scoring_error:
            logger.warning(
                "Intl scoring batch %d failed after 2 attempts: %s",
                batch_start,
                scoring_error,
            )
            for i in range(batch_start, batch_start + len(batch)):
                scored.setdefault(i, min_score)

    return scored
