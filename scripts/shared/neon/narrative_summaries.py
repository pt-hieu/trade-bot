"""Formatted narrative summaries for morning brief context."""

from datetime import date

from .narratives import get_active_narratives


def _momentum_label(narrative: dict, today: date | None = None) -> str:
    """Derive momentum from conviction score and recency. Pure deterministic."""
    today = today or date.today()
    conviction = narrative.get("conviction_score") or 0
    last_seen = narrative.get("last_seen")

    if conviction < 0.1:
        return "DEAD"
    if conviction < 0.3:
        return "FADING"

    if last_seen and last_seen == today and conviction >= 0.5:
        return "BUILDING"

    if last_seen and (today - last_seen).days <= 3 and conviction >= 0.3:
        return "STEADY"

    return "FADING"


def _format_narrative_line(n: dict, today: date | None = None) -> str:
    """Format a single narrative as a brief line."""
    today = today or date.today()
    conviction = n.get("conviction_score") or 0
    theme = n.get("theme") or "Unknown"
    momentum = _momentum_label(n, today)
    article_count = n.get("article_count") or 0
    source_count = n.get("source_count") or 0
    tickers = n.get("affected_tickers") or []
    ticker_str = ", ".join(tickers[:5]) if tickers else "broad market"

    implication = n.get("trading_implication") or ""
    impl_suffix = f" — {implication[:80]}" if implication else ""

    return (
        f'[{conviction:.2f}] "{theme}" ({momentum}, '
        f"{article_count} articles, {source_count} sources) "
        f"→ {ticker_str}{impl_suffix}"
    )


async def get_narrative_summary(tickers: list[str] | None = None) -> str:
    """Formatted narrative summary for morning brief deterministic sections."""
    narratives = await get_active_narratives(tickers)

    if not narratives:
        return ""

    # Only show narratives with meaningful conviction AND maturity (hide single-article noise)
    active = [
        n
        for n in narratives
        if (n.get("conviction_score") or 0) >= 0.15
        and n.get("maturity") in ("developing", "confirmed", "mature")
    ]
    if not active:
        return ""

    today = date.today()
    lines = []
    for n in active[:8]:  # Cap at 8 for readability
        lines.append(f"- {_format_narrative_line(n, today)}")

    return "\n".join(lines)
