"""Unit — run_news_v2_pass must reject articles missing DB id.

SWI-C (2026-05-06): the legacy intraday flow passed RSS-fetched dicts
(no ``id``) to the persistence path; the Stage 1 ``UPDATE articles ...
WHERE id = $1`` silently no-op'd because $1 was None. The new contract
takes a flat ``list[RehydratedArticle]`` and raises ValueError if any
element is missing ``id`` — fail-loud at the seam between rehydration
and the LLM call.
"""

from __future__ import annotations

from datetime import date

import pytest


@pytest.mark.asyncio
async def test_raises_on_missing_id():
    from pipeline.news_v2_persist import run_news_v2_pass

    articles = [
        {"id": "uuid-1", "url": "https://a"},
        {"id": None, "url": "https://b"},
    ]
    with pytest.raises(ValueError, match="missing id"):
        await run_news_v2_pass(date(2026, 5, 6), articles)


@pytest.mark.asyncio
async def test_returns_zero_on_empty_list():
    from pipeline.news_v2_persist import run_news_v2_pass

    assert await run_news_v2_pass(date(2026, 5, 6), []) == 0


@pytest.mark.asyncio
async def test_raises_on_empty_id_string():
    from pipeline.news_v2_persist import run_news_v2_pass

    articles = [{"id": "", "url": "https://a"}]
    with pytest.raises(ValueError, match="missing id"):
        await run_news_v2_pass(date(2026, 5, 6), articles)
