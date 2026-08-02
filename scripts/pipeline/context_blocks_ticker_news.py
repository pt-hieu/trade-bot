"""Per-ticker article/narrative/longterm formatters and indexers.

Splits the per-ticker news/narrative/longterm rendering out of
context_blocks_ticker.format_ticker_briefing so each helper stays small and the
main briefing builder keeps its per-field decomposition.
"""

from __future__ import annotations

from shared.formatting import format_price_k


def format_longterm_line(longterm: dict) -> str:
    """One-line longterm watchlist line: conviction, sector, entry zone.

    Source: `shared.neon.watchlist.get_longterm_watchlist` — keys are
    `conviction`, `sector`, `entry_zone`. The thesis text itself lives in
    `thesis_tracker.pillars` and is pulled on demand via portfolio.get_thesis,
    not injected here.
    """
    conviction = (longterm.get("conviction") or "").strip()
    sector = (longterm.get("sector") or "").strip()
    entry_zone = longterm.get("entry_zone")
    parts = ["Longterm:"]
    if conviction:
        parts.append(f"conv={conviction}")
    if sector:
        parts.append(f"sector={sector}")
    if entry_zone:
        parts.append(f"entry≈{format_price_k(entry_zone)}")
    if len(parts) == 1:
        return ""
    return " ".join(parts)


def format_narrative_line(narratives: list[dict]) -> str:
    """Top-conviction narrative theme as a single line. Empty when nothing active."""
    if not narratives:
        return ""
    top = narratives[0]
    theme = (top.get("theme") or "").strip()
    if not theme:
        return ""
    conviction = top.get("conviction_score")
    implication = (top.get("trading_implication") or "")[:80].strip()
    parts = [f"Narrative: {theme[:80]}"]
    if conviction is not None:
        parts.append(f"conv={float(conviction):.2f}")
    if implication:
        parts.append(f"→ {implication}")
    return " | ".join(parts)


def format_article_lines(articles: list[dict], limit: int) -> list[str]:
    """Top recent articles by published_at desc, one line each.

    Filters out entries missing a title. Sentiment tag shown only when strong.
    """
    ranked = sorted(
        articles,
        key=lambda article: article.get("published_at") or "",
        reverse=True,
    )
    lines: list[str] = []
    for article in ranked:
        title = (article.get("title") or "").strip()
        if not title:
            continue
        source = (article.get("source") or article.get("domain") or "").strip()
        sentiment = article.get("sentiment_score")
        sentiment_tag = ""
        if isinstance(sentiment, int | float):
            if sentiment >= 0.3:
                sentiment_tag = " +"
            elif sentiment <= -0.3:
                sentiment_tag = " -"
        src_tag = f" ({source})" if source else ""
        lines.append(f"News:{sentiment_tag} {title[:120]}{src_tag}")
        if len(lines) >= limit:
            break
    return lines


def index_articles_by_ticker(articles: list[dict] | None) -> dict[str, list[dict]]:
    """Build {ticker: [articles]} index using affected_tickers arrays."""
    index: dict[str, list[dict]] = {}
    for article in articles or []:
        affected = article.get("affected_tickers") or []
        for ticker in affected:
            if not ticker:
                continue
            index.setdefault(str(ticker).upper(), []).append(article)
    return index


def index_narratives_by_ticker(narratives: list[dict] | None) -> dict[str, list[dict]]:
    """Build {ticker: [narratives]} index sorted by conviction desc per ticker."""
    index: dict[str, list[dict]] = {}
    for narrative in narratives or []:
        affected = narrative.get("affected_tickers") or []
        for ticker in affected:
            if not ticker:
                continue
            index.setdefault(str(ticker).upper(), []).append(narrative)
    for ticker_narratives in index.values():
        ticker_narratives.sort(
            key=lambda narrative: float(narrative.get("conviction_score") or 0),
            reverse=True,
        )
    return index
