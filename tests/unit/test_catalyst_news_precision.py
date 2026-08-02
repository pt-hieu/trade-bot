"""Precision guards for shared.rules.catalyst_news match_articles_to_catalysts.

Targets DEF-2026-04-16-201:
  - Structured VN-relevance via `article.affected_tickers` (per-ticker
    catalysts only match VN-tagged articles; macro-blanket bypasses).
  - 2-hit fallback when a catalyst has no explicit `detection_keywords`.
  - Schema-boundary validation of `CatalystAddition.detection_keywords`
    (min 3 chars per item, 2-6 items, whitespace-only rejected).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.catalysts import CatalystAddition
from shared.rules.catalyst_news import match_articles_to_catalysts


def _article(
    *,
    title: str = "",
    short_description: str = "",
    affected_tickers: list[str] | None = None,
) -> dict:
    return {
        "title": title,
        "short_description": short_description,
        "affected_tickers": affected_tickers or [],
    }


def _per_ticker_catalyst(
    *,
    catalyst_key: str = "c1",
    event: str = "FPT power center decree signed",
    detection_keywords: list[str] | None = None,
    affected_tickers: list[str] | None = None,
) -> dict:
    payload: dict = {
        "catalyst_key": catalyst_key,
        "event": event,
        "catalyst_type": "regulatory",
        "affected_tickers": affected_tickers or ["FPT"],
    }
    if detection_keywords is not None:
        payload["detection_keywords"] = detection_keywords
    return payload


def _macro_blanket_catalyst(
    *,
    catalyst_key: str = "hormuz_closure_2026",
    event: str = "Strait of Hormuz closure escalation",
    detection_keywords: list[str] | None = None,
) -> dict:
    payload: dict = {
        "catalyst_key": catalyst_key,
        "event": event,
        "catalyst_type": "geopolitical",
        "affected_tickers": ["VN-INDEX"],
    }
    if detection_keywords is not None:
        payload["detection_keywords"] = detection_keywords
    return payload


class TestFallbackPath:
    def test_fallback_path_one_hit_no_match(self) -> None:
        # One keyword ('power center') hits the article body, but the
        # catalyst has no detection_keywords → 2-hit required.
        article = _article(
            title="FPT wins power center contract",
            affected_tickers=["FPT"],
        )
        catalyst = _per_ticker_catalyst(event="FPT power center decree signed")
        result = match_articles_to_catalysts([article], [catalyst])
        assert result == {}

    def test_per_ticker_article_without_affected_tickers_is_blocked_by_vn_gate(
        self,
    ) -> None:
        # Per-ticker catalysts (non-macro-blanket) require a structured
        # VN signal. An article without affected_tickers fails the gate
        # even when 2+ keywords hit — this is the precision floor for
        # untagged articles.
        article = _article(
            title="FPT power center decree signed by government",
            affected_tickers=[],
        )
        catalyst = _per_ticker_catalyst(event="FPT power center decree signed")
        result = match_articles_to_catalysts([article], [catalyst])
        assert result == {}

    def test_same_keyword_twice_in_article_counts_once(self) -> None:
        # Build a catalyst whose keyword list contains substrings — if one
        # matches, it must NOT double-count as two distinct hits.
        article = _article(
            title="russia russia russia",
            affected_tickers=["PLX"],
        )
        catalyst = _per_ticker_catalyst(
            event="russia",
            detection_keywords=None,
            affected_tickers=["PLX"],
        )
        # Only one keyword ('russia') in the catalyst after bigram extract.
        # Substring occurrences don't create new distinct hits.
        result = match_articles_to_catalysts([article], [catalyst])
        assert result == {}


class TestExplicitDetectionKeywords:
    def test_explicit_detection_keywords_single_hit_matches(self) -> None:
        article = _article(
            title="Strait of Hormuz closure",
            affected_tickers=["PLX"],
        )
        catalyst = _per_ticker_catalyst(
            detection_keywords=["strait of hormuz", "oil embargo"],
            affected_tickers=["PLX"],
        )
        result = match_articles_to_catalysts([article], [catalyst])
        assert catalyst["catalyst_key"] in result


class TestVnRelevanceGate:
    def test_per_ticker_catalyst_article_with_affected_tickers_passes(self) -> None:
        # Non-empty affected_tickers satisfies VN signal; 2-hit still needed.
        article = _article(
            title="FPT power center decree signed today",
            affected_tickers=["FPT"],
        )
        catalyst = _per_ticker_catalyst(event="FPT power center decree signed")
        result = match_articles_to_catalysts([article], [catalyst])
        assert catalyst["catalyst_key"] in result

    def test_macro_blanket_catalyst_foreign_article_allowed(self) -> None:
        # VN-INDEX macro-blanket catalyst matches Hormuz article even with
        # empty affected_tickers (global trigger, bypasses VN signal).
        article = _article(
            title="Strait of Hormuz blockade oil tanker strike",
            affected_tickers=[],
        )
        catalyst = _macro_blanket_catalyst(
            detection_keywords=["strait of hormuz"],
        )
        result = match_articles_to_catalysts([article], [catalyst])
        assert catalyst["catalyst_key"] in result


class TestDetectionKeywordsSchema:
    def test_detection_keywords_whitespace_only_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CatalystAddition(
                event="test",
                affected=["FPT"],
                expected="Q2 2026",
                impact="POSITIVE",
                confidence="HIGH",
                source="test",
                catalyst_type="regulatory",
                driver="regulator",
                detection_keywords=["  ", "valid keyword"],
            )

    def test_detection_keywords_single_char_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CatalystAddition(
                event="test",
                affected=["FPT"],
                expected="Q2 2026",
                impact="POSITIVE",
                confidence="HIGH",
                source="test",
                catalyst_type="regulatory",
                driver="regulator",
                detection_keywords=["a", "bc"],
            )

    def test_detection_keywords_empty_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CatalystAddition(
                event="test",
                affected=["FPT"],
                expected="Q2 2026",
                impact="POSITIVE",
                confidence="HIGH",
                source="test",
                catalyst_type="regulatory",
                driver="regulator",
                detection_keywords=[],
            )

    def test_detection_keywords_too_many_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CatalystAddition(
                event="test",
                affected=["FPT"],
                expected="Q2 2026",
                impact="POSITIVE",
                confidence="HIGH",
                source="test",
                catalyst_type="regulatory",
                driver="regulator",
                detection_keywords=["one", "two", "three", "four", "five", "six", "seven"],
            )

    def test_detection_keywords_lowercased_and_stripped(self) -> None:
        addition = CatalystAddition(
            event="test",
            affected=["FPT"],
            expected="Q2 2026",
            impact="POSITIVE",
            confidence="HIGH",
            source="test",
            catalyst_type="regulatory",
            driver="regulator",
            detection_keywords=["  STRAIT OF HORMUZ  ", "oil embargo"],
        )
        assert addition.detection_keywords == ["strait of hormuz", "oil embargo"]
