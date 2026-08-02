"""
Tests for data.articles_intl — international RSS feed processing.

Run: uv run pytest tests/unit/test_articles_intl.py -v --tb=short
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Pre-filter tests
# ---------------------------------------------------------------------------


class TestIntlBlocklist:
    """English blocklist removes sports, entertainment, lifestyle."""

    def test_blocks_nfl(self):
        from data.articles_intl import intl_pre_filter

        articles = [
            {"title": "NFL draft picks revealed", "short_description": "", "publish_time": None}
        ]
        assert intl_pre_filter(articles) == []

    def test_blocks_nba(self):
        from data.articles_intl import intl_pre_filter

        articles = [{"title": "NBA finals game 7", "short_description": "", "publish_time": None}]
        assert intl_pre_filter(articles) == []

    def test_blocks_celebrity(self):
        from data.articles_intl import intl_pre_filter

        articles = [
            {"title": "Celebrity bankruptcy filing", "short_description": "", "publish_time": None}
        ]
        assert intl_pre_filter(articles) == []

    def test_blocks_recipe(self):
        from data.articles_intl import intl_pre_filter

        articles = [
            {"title": "Best recipe for pasta", "short_description": "", "publish_time": None}
        ]
        assert intl_pre_filter(articles) == []


class TestIntlAllowlist:
    """Macro keyword allowlist keeps only relevant articles."""

    def test_passes_fed_rate_decision(self):
        from data.articles_intl import intl_pre_filter

        articles = [
            {
                "title": "Fed holds interest rate steady",
                "short_description": "Federal Reserve keeps rates unchanged",
                "publish_time": None,
            }
        ]
        result = intl_pre_filter(articles)
        assert len(result) == 1

    def test_passes_oil_price(self):
        from data.articles_intl import intl_pre_filter

        articles = [
            {
                "title": "Oil price surges on OPEC cuts",
                "short_description": "Crude oil rises 5%",
                "publish_time": None,
            }
        ]
        result = intl_pre_filter(articles)
        assert len(result) == 1

    def test_blocks_irrelevant_non_macro(self):
        from data.articles_intl import intl_pre_filter

        articles = [
            {
                "title": "New smartphone features announced",
                "short_description": "Latest phone specs revealed",
                "publish_time": None,
            }
        ]
        assert intl_pre_filter(articles) == []

    def test_passes_tariff_article(self):
        from data.articles_intl import intl_pre_filter

        articles = [
            {
                "title": "US imposes new tariff on imports",
                "short_description": "Trade tensions escalate",
                "publish_time": None,
            }
        ]
        result = intl_pre_filter(articles)
        assert len(result) == 1


class TestAgeFilter:
    """Articles older than 36 hours are filtered out."""

    def test_drops_stale_article(self):
        from data.articles_intl import intl_pre_filter

        stale_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        articles = [
            {
                "title": "Fed rate decision",
                "short_description": "Interest rate held",
                "publish_time": stale_time,
            }
        ]
        assert intl_pre_filter(articles) == []

    def test_keeps_fresh_article(self):
        from data.articles_intl import intl_pre_filter

        fresh_time = (datetime.now(UTC) - timedelta(hours=12)).isoformat()
        articles = [
            {
                "title": "Fed rate decision",
                "short_description": "Interest rate held",
                "publish_time": fresh_time,
            }
        ]
        assert len(intl_pre_filter(articles)) == 1

    def test_keeps_unknown_publish_time(self):
        from data.articles_intl import intl_pre_filter

        articles = [
            {
                "title": "Oil price update",
                "short_description": "Crude oil rises",
                "publish_time": None,
            }
        ]
        assert len(intl_pre_filter(articles)) == 1


# ---------------------------------------------------------------------------
# Title dedup tests
# ---------------------------------------------------------------------------


class TestTitleDedup:
    """Cross-domain wire story deduplication via Jaccard similarity."""

    def test_catches_identical_titles(self):
        from data.articles_intl import title_dedup

        articles = [
            {"title": "Fed holds rates steady in March meeting", "site": "cnbc"},
            {"title": "Fed holds rates steady in March meeting", "site": "marketwatch"},
        ]
        result = title_dedup(articles)
        assert len(result) == 1

    def test_catches_near_identical_wire_stories(self):
        from data.articles_intl import title_dedup

        articles = [
            {"title": "Federal Reserve holds interest rates steady", "site": "cnbc"},
            {
                "title": "Federal Reserve holds interest rates steady at meeting",
                "site": "marketwatch",
            },
        ]
        result = title_dedup(articles)
        # Jaccard similarity > 0.8 — should dedup
        assert len(result) == 1

    def test_keeps_different_articles(self):
        from data.articles_intl import title_dedup

        articles = [
            {"title": "Fed holds rates steady", "site": "cnbc"},
            {"title": "Oil prices surge on OPEC production cuts", "site": "oilprice"},
        ]
        result = title_dedup(articles)
        assert len(result) == 2

    def test_handles_empty_title(self):
        from data.articles_intl import title_dedup

        articles = [
            {"title": "", "site": "cnbc"},
            {"title": "Fed holds rates", "site": "marketwatch"},
        ]
        result = title_dedup(articles)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Published date parsing
# ---------------------------------------------------------------------------


class TestParsePublished:
    """RSS date format parsing (RFC 822 and ISO 8601)."""

    def test_rfc822_format(self):
        from data.articles_intl import _parse_published

        result = _parse_published("Wed, 01 Apr 2026 10:30:00 +0000")
        assert result is not None
        assert "2026-04-01" in result

    def test_iso8601_format(self):
        from data.articles_intl import _parse_published

        result = _parse_published("2026-04-01T10:30:00Z")
        assert result is not None
        assert "2026-04-01" in result

    def test_none_input(self):
        from data.articles_intl import _parse_published

        assert _parse_published(None) is None

    def test_empty_string(self):
        from data.articles_intl import _parse_published

        assert _parse_published("") is None

    def test_invalid_format(self):
        from data.articles_intl import _parse_published

        assert _parse_published("not a date") is None


# ---------------------------------------------------------------------------
# Search results shape
# ---------------------------------------------------------------------------


class TestSearchResultsShape:
    """Verify output format matches insert_articles() contract."""

    @pytest.mark.asyncio
    async def test_output_shape(self, tmp_path):
        from data.articles_intl import fetch_international_articles

        mock_articles = [
            {
                "title": "Fed holds rates",
                "url": "https://example.com/fed-holds",
                "short_description": "Federal Reserve keeps rates steady",
                "publish_time": datetime.now(UTC).isoformat(),
                "site": "fed-press",
                "category": "monetary",
            },
        ]

        with (
            patch("data.articles_intl.fetch_all_feeds", new_callable=AsyncMock) as mock_fetch,
            patch("data.articles_intl._score_intl_relevance") as mock_score,
        ):
            mock_fetch.return_value = (mock_articles, [])
            mock_score.return_value = {0: 8}

            result = await fetch_international_articles(tmp_path)

        assert isinstance(result, dict)
        for query_name, data in result.items():
            assert query_name.startswith("rss-intl-")
            assert "query" in data
            assert "status" in data
            assert "count" in data
            assert "articles" in data
            for article in data["articles"]:
                assert "title" in article
                assert "url" in article
                assert "summary" in article
                assert "domain" in article


# Sentiment-keyword tests retired (SWI-103) — keyword scorer replaced by
# LLM agent. The 4 macro headlines (rally / recession / hawkish / rate cut)
# moved to tests/agents/test_article_sentiment.py as eval cases.
