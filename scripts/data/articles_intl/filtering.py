"""Pre-filter (blocklist + macro allowlist + age) + Jaccard title dedup."""

from __future__ import annotations

import re

from shared.macro_factors import KEYWORD_TO_FACTOR

from .feeds import _is_stale

_INTL_BLOCKLIST = re.compile(
    r"|".join(
        [
            r"\bnfl\b",
            r"\bnba\b",
            r"\bmlb\b",
            r"\bnhl\b",
            r"\bsuper bowl\b",
            r"\bworld series\b",
            r"\bolympic\b",
            r"\bfifa\b",
            r"\bworld cup\b",
            r"\bhollywood\b",
            r"\bcelebrit",
            r"\bgrammy\b",
            r"\boscar\b",
            r"\bemmy\b",
            r"\brecipe\b",
            r"\bcooking\b",
            r"\bfitness tip\b",
            r"\bweight loss\b",
            r"\bhoroscope\b",
            r"\bweather forecast\b",
            r"\bserial killer\b",
            r"\bhomicide\b",
            r"\bmurder suspect\b",
        ]
    ),
    re.IGNORECASE,
)

# Build allowlist from macro factor English keywords + supplementary terms
_MACRO_ALLOWLIST: set[str] = {kw for kw in KEYWORD_TO_FACTOR if kw.isascii()}
_MACRO_ALLOWLIST.update(
    [
        "rate cut",
        "rate hike",
        "rate decision",
        "rate hold",
        "inflation",
        "recession",
        "employment",
        "jobs report",
        "central bank",
        "monetary policy",
        "quantitative",
        "trade war",
        "tariff",
        "sanctions",
        "embargo",
        "commodity",
        "commodities",
        "crude",
        "brent",
        "natural gas",
        "supply chain",
        "semiconductor",
        "chip shortage",
        "emerging market",
        "asia",
        "vietnam",
        "asean",
        "southeast asia",
        "china",
        "beijing",
        "yuan",
        "renminbi",
        "dollar",
        "forex",
        "currency",
        "exchange rate",
        "oil price",
        "oil production",
        "opec",
        "energy",
        "geopolitical",
        "conflict",
        "war",
        "middle east",
        "iran",
        "hormuz",
        "fed",
        "fomc",
        "powell",
        "ecb",
        "lagarde",
        "stock market",
        "equities",
        "bond",
        "treasury",
        "yield",
    ]
)


def _matches_macro_allowlist(text: str) -> bool:
    """Check if text contains any macro-relevant keyword."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in _MACRO_ALLOWLIST)


def intl_pre_filter(articles: list[dict]) -> list[dict]:
    """Remove noise via blocklist, keep only macro-relevant via allowlist, drop stale."""
    kept = []
    for article in articles:
        text = f"{article.get('title') or ''} {article.get('short_description') or ''}"
        if _INTL_BLOCKLIST.search(text):
            continue
        if not _matches_macro_allowlist(text):
            continue
        if _is_stale(article.get("publish_time")):
            continue
        kept.append(article)
    return kept


def title_dedup(articles: list[dict], threshold: float = 0.7) -> list[dict]:
    """Remove cross-domain wire duplicates via Jaccard title similarity."""
    kept: list[dict] = []
    kept_token_sets: list[set[str]] = []

    for article in articles:
        tokens = set(re.findall(r"\w+", (article.get("title") or "").lower()))
        if not tokens:
            kept.append(article)
            continue
        is_duplicate = False
        for existing_tokens in kept_token_sets:
            if not existing_tokens:
                continue
            intersection = tokens & existing_tokens
            union = tokens | existing_tokens
            if len(intersection) / len(union) > threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(article)
            kept_token_sets.append(tokens)

    return kept
