"""Catalyst-news matching and spike detection — pure deterministic Python.

No async, no DB, no LLM. Matches articles against catalyst keywords
and detects volume spikes that signal catalyst resolution.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, TypedDict

MacroCatalystScope = Literal["macro_blanket", "per_ticker"]

# Catalyst types that can legitimately carry the VN-INDEX placeholder
# because their transmission path is market-wide. Per-ticker catalysts
# (corporate_action, earnings, legal, rating) must always name explicit
# VN-listed tickers even when the LLM tries to use VN-INDEX shorthand.
MACRO_BLANKET_ELIGIBLE_TYPES: frozenset[str] = frozenset({"macro", "geopolitical", "commodity"})


def classify_macro_catalyst_scope(catalyst: dict) -> MacroCatalystScope:
    """Classify whether a catalyst's impact is market-wide or ticker-specific.

    A catalyst is ``macro_blanket`` only when it carries the reserved
    VN-INDEX placeholder AND its type is in the macro/geopolitical/
    commodity bucket. Everything else is ``per_ticker`` — corporate
    actions, earnings, ratings, and legal events always need explicit
    ticker lists regardless of what the LLM returned.
    """
    # Local import to avoid shared.rules -> shared.vn_universe -> DB dep cycle.
    from shared.vn_universe import VN_INDEX_PLACEHOLDER

    affected = catalyst.get("affected_tickers") or catalyst.get("affected") or []
    catalyst_type = (catalyst.get("catalyst_type") or "").lower()
    is_vn_index_only = (
        isinstance(affected, list)
        and len(affected) == 1
        and str(affected[0]).upper() == VN_INDEX_PLACEHOLDER
    )
    if is_vn_index_only and catalyst_type in MACRO_BLANKET_ELIGIBLE_TYPES:
        return "macro_blanket"
    return "per_ticker"


class CatalystNewsSignal(TypedDict):
    """Signal from matching news articles to a catalyst.

    SWI-201: ``unique_article_count`` reflects deduped (normalized-title)
    counts. Spike detection downstream consumes this value, not
    ``article_count``, so recycled headlines don't suppress a real spike.
    """

    catalyst_key: str
    catalyst_event: str
    article_count: int
    unique_article_count: int
    is_spike: bool
    sample_titles: list[str]


STOP_WORDS = frozenset(
    {
        "the",
        "of",
        "for",
        "and",
        "in",
        "to",
        "from",
        "with",
        "a",
        "an",
        "is",
        "on",
        "at",
        "by",
        "as",
        "or",
        "vietnam",
        "vietnamese",
    }
)


# Single source of truth for geopolitical trigger words. Consumed by:
#   - `agents.catalysts._find_duplicate_catalyst` (keyword overlap for
#     duplicate detection on geopolitical-type candidates).
#   - `shared.rules.catalyst_classifier` (builds regex patterns from this
#     set plus a few multi-word phrases for classification).
# Keep both consumers in sync by extending this set rather than editing
# either consumer's local copy.
GEOPOLITICAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "hormuz",
        "strait",
        "blockade",
        "sanction",
        "sanctions",
        "war",
        "invasion",
        "tariff",
        "tariffs",
        "opec",
        "embargo",
        "missile",
        "strike",
        "military",
        "conflict",
        "ceasefire",
        "pipeline",
        "tanker",
        "iran",
        "russia",
        "taiwan",
    }
)

# Parallel pattern set for the classifier (AUDIT-2026-04-24-001 /
# ISSUE-2026-04-24-004). `GEOPOLITICAL_KEYWORDS` stays untouched because
# `agents.catalysts._find_duplicate_catalyst` uses `in` set membership;
# adding morphology variants there would poison dedup. This tuple covers
# ``Iranian``, ``Russian oil``, ``QatarEnergy`` etc. so the Iran-proxy
# shocks that slipped through as 'macro' get reclassified as geopolitical
# with phases required.
GEOPOLITICAL_KEYWORD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"iran(?:ian)?", re.IGNORECASE),
    re.compile(r"russia(?:n)?", re.IGNORECASE),
    re.compile(r"kuwait(?:i)?", re.IGNORECASE),
    re.compile(r"qatar(?:i)?", re.IGNORECASE),
    re.compile(r"qatarenergy", re.IGNORECASE),
    re.compile(r"stockpile\s+drawdown", re.IGNORECASE),
    re.compile(r"jones\s+act(?:\s+waiver)?", re.IGNORECASE),
    re.compile(r"gulf\s+blockade", re.IGNORECASE),
    re.compile(r"russia(?:n)?\s+oil", re.IGNORECASE),
    re.compile(r"marine\s+fuel", re.IGNORECASE),
    re.compile(r"(?:strait\s+of\s+)?hormuz", re.IGNORECASE),
    re.compile(r"taiwan(?:ese)?", re.IGNORECASE),
    re.compile(r"ukrain(?:e|ian)", re.IGNORECASE),
    re.compile(r"houthi", re.IGNORECASE),
    re.compile(r"bab[-\s]?el[-\s]?mandeb", re.IGNORECASE),
    # Forward-defensive (SWI-63): events whose primary keywords lack
    # iran/russia/qatar/hormuz attribution but still describe geopolitically
    # driven supply disruptions or sanctions policy.
    re.compile(
        r"(?:drawing\s+down|drawdown\s+of)\s+(?:oil\s+|crude\s+|fuel\s+)?stockpiles?", re.IGNORECASE
    ),
    re.compile(
        r"(?:sanctions?\s+waiver|policy\s+exemption|extend(?:ing)?\s+(?:waiver|exemption))",
        re.IGNORECASE,
    ),
)


def normalize_text(text: str) -> str:
    """Lowercase and strip diacritics for fuzzy matching."""
    text = text.lower()
    # Decompose unicode, strip combining characters (diacritics)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _has_explicit_detection_keywords(catalyst: dict) -> bool:
    """True when the catalyst carries a non-empty `detection_keywords` list."""
    explicit = catalyst.get("detection_keywords")
    return bool(explicit) and isinstance(explicit, list) and any(k for k in explicit)


def build_catalyst_keywords(catalyst: dict) -> list[str]:
    """Extract searchable keywords from a catalyst dict.

    Combines event name, notes, and catalyst_key to produce
    keywords for article matching.

    Args:
        catalyst: Dict with at least 'event', optionally 'notes', 'catalyst_key',
                  'detection_keywords' (list[str] override).

    Returns:
        List of normalized keyword strings (lowercase, no diacritics).
    """
    if _has_explicit_detection_keywords(catalyst):
        explicit = catalyst["detection_keywords"]
        return [normalize_text(keyword) for keyword in explicit if keyword]

    keywords: list[str] = []
    event = catalyst.get("event") or ""

    # Extract meaningful phrases from event name
    # Split on common delimiters and filter short/common words
    words = re.split(r"[\s\-—/]+", event.lower())
    meaningful = [word for word in words if len(word) > 3 and word not in STOP_WORDS]

    # Take key bigrams from event name
    if len(meaningful) >= 2:
        for i in range(len(meaningful) - 1):
            bigram = f"{meaningful[i]} {meaningful[i + 1]}"
            keywords.append(normalize_text(bigram))

    # Add the full event as a keyword (normalized)
    if event:
        keywords.append(normalize_text(event))

    # Add notes keywords if present
    notes = catalyst.get("notes") or ""
    if notes:
        keywords.append(normalize_text(notes[:100]))

    # Add catalyst_key as a keyword
    catalyst_key = catalyst.get("catalyst_key") or ""
    if catalyst_key:
        # Convert snake_case to words
        key_words = catalyst_key.replace("_", " ")
        keywords.append(normalize_text(key_words))

    return [keyword for keyword in keywords if keyword]


def _article_is_vn_relevant_for_catalyst(article: dict) -> bool:
    """Per-ticker catalyst articles must carry a non-empty affected_tickers list.

    Structured signal from the news_v2 Stage-2 extractor + the VN whitelist
    validator shipped under DEF-2026-04-24-002. Empty/missing falls through
    to the match loop without the VN pre-filter — the 2-hit rule catches
    most noise for untagged articles, and the news_v2 Stage-2 extractor
    coverage gap is tracked separately under AUDIT-2026-04-24-001.
    """
    affected = article.get("affected_tickers") or []
    return bool(affected)


def match_articles_to_catalysts(
    articles: list[dict],
    catalysts: list[dict],
) -> dict[str, list[int]]:
    """Match articles against catalyst keywords.

    Pure string matching — no LLM involved. Two precision upgrades over
    the legacy single-hit bigram match (DEF-2026-04-16-201):

    1. Per-ticker catalysts only match articles with non-empty
       ``affected_tickers`` (structured VN signal). Macro-blanket
       catalysts (VN-INDEX + macro/geopolitical/commodity type) bypass
       the gate so global triggers like Hormuz/Fed/OPEC still match.
    2. When a catalyst has no explicit ``detection_keywords``, at least
       two distinct keywords must hit the article. Substring hits of the
       same keyword count once.

    Args:
        articles: List of article dicts with 'title' and optionally
            'short_description' and optionally 'affected_tickers'.
        catalysts: List of catalyst dicts (passed to build_catalyst_keywords).

    Returns:
        {catalyst_key: [article_indices]} mapping.
    """
    result: dict[str, list[int]] = {}

    # Pre-normalize article text + pre-compute VN signal per article.
    article_texts: list[str] = []
    article_vn_signal: list[bool] = []
    for article in articles:
        title = normalize_text(article.get("title") or "")
        description = normalize_text(article.get("short_description") or "")
        article_texts.append(f"{title} {description}")
        article_vn_signal.append(_article_is_vn_relevant_for_catalyst(article))

    for catalyst in catalysts:
        catalyst_key = catalyst.get("catalyst_key") or catalyst.get("id") or ""
        if not catalyst_key:
            continue

        keywords = build_catalyst_keywords(catalyst)
        if not keywords:
            continue

        min_hits = 1 if _has_explicit_detection_keywords(catalyst) else 2
        is_macro_blanket = classify_macro_catalyst_scope(catalyst) == "macro_blanket"

        matched_indices: list[int] = []
        for article_index, article_text in enumerate(article_texts):
            # Per-ticker catalysts require the structured VN signal;
            # macro-blanket catalysts bypass (global triggers).
            if not is_macro_blanket and not article_vn_signal[article_index]:
                continue

            matched_kw: set[str] = set()
            for keyword in keywords:
                if keyword in article_text:
                    matched_kw.add(keyword)
                    if len(matched_kw) >= min_hits:
                        break

            if len(matched_kw) >= min_hits:
                matched_indices.append(article_index)

        if matched_indices:
            result[catalyst_key] = matched_indices

    return result


def detect_article_spike(
    current_count: int,
    baseline_count: float,
    threshold: float = 2.0,
) -> bool:
    """Detect if current article count is a spike vs baseline.

    Args:
        current_count: Articles matched in current check window.
        baseline_count: Average articles per check over baseline period.
        threshold: Spike multiplier (default 2x baseline).

    Returns:
        True if current_count exceeds threshold * baseline.
    """
    if current_count == 0:
        return False
    if baseline_count <= 0:
        # No baseline — any match counts as spike
        return current_count >= 2
    return current_count >= threshold * baseline_count


def build_signals(
    matches: dict[str, list[int]],
    articles: list[dict],
    catalysts: list[dict],
    baselines: dict[str, float] | None = None,
) -> list[CatalystNewsSignal]:
    """Build CatalystNewsSignal list from match results.

    Args:
        matches: Output of match_articles_to_catalysts.
        articles: Original articles list (for sample titles).
        catalysts: Original catalysts list (for event names).
        baselines: {catalyst_key: avg_article_count} from history. None = no baseline.

    Returns:
        List of CatalystNewsSignal for catalysts with matches.
    """
    catalyst_events = {
        (catalyst.get("catalyst_key") or catalyst.get("id") or ""): catalyst.get("event", "")
        for catalyst in catalysts
    }
    baselines = baselines or {}

    signals: list[CatalystNewsSignal] = []
    for catalyst_key, article_indices in matches.items():
        article_count = len(article_indices)
        # SWI-201: dedup recycled headlines via normalized title.
        unique_article_count = _count_unique_titles(articles, article_indices)
        baseline = baselines.get(catalyst_key, 0.0)
        # Spike detection consumes the deduped count so a single news event
        # repeated 12× across feeds doesn't suppress a real spike against the
        # 7-day baseline. ``article_count`` is retained for backward-compat
        # readers (existing dashboards / retro joins).
        is_spike = detect_article_spike(unique_article_count, baseline)

        sample_titles = [
            (articles[index].get("title") or "Untitled")[:100] for index in article_indices[:5]
        ]

        signals.append(
            CatalystNewsSignal(
                catalyst_key=catalyst_key,
                catalyst_event=catalyst_events.get(catalyst_key, ""),
                article_count=article_count,
                unique_article_count=unique_article_count,
                is_spike=is_spike,
                sample_titles=sample_titles,
            )
        )

    return signals


def _count_unique_titles(articles: list[dict], indices: list[int]) -> int:
    """Count distinct articles by normalized title (SWI-201).

    Normalization strips non-alphanumeric chars and lowercases — "Trump
    threatens Hormuz blockade." and "Trump-threatens-Hormuz-blockade!"
    collapse to one. Empty/missing titles each count as one unique entry
    so the function never returns 0 when ``indices`` is non-empty.
    """
    import re

    seen: set[str] = set()
    fallback_unique = 0
    for index in indices:
        if index < 0 or index >= len(articles):
            continue
        title = (articles[index].get("title") or "").strip()
        if not title:
            fallback_unique += 1
            continue
        norm = re.sub(r"[^a-z0-9]+", "", title.lower())
        if norm:
            seen.add(norm)
        else:
            fallback_unique += 1
    return len(seen) + fallback_unique
