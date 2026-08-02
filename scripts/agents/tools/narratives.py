"""Narrative thread tools for LLM agents."""

import logging
from datetime import date

from shared.neon.narrative_summaries import _momentum_label

logger = logging.getLogger(__name__)


def _format_narratives_prose(narratives: list[dict], ref_date: date) -> str:
    if not narratives:
        return "Active Narratives: none found."

    lines = [f"Active Narratives ({len(narratives)} threads):"]
    for narrative in narratives:
        score = narrative.get("conviction_score") or 0.0
        theme = narrative.get("theme") or "Unknown"
        maturity = narrative.get("maturity") or "emerging"
        article_count = narrative.get("article_count") or 0
        source_count = narrative.get("source_count") or 0
        tickers = narrative.get("affected_tickers") or []
        momentum = _momentum_label(narrative, ref_date)
        ticker_str = ", ".join(tickers[:5]) if tickers else "—"

        implication = narrative.get("trading_implication") or ""
        implication_suffix = f" — {implication[:80]}" if implication else ""

        lines.append(
            f'[{score:.2f}] "{theme}" ({maturity}, {momentum}, {article_count} articles,'
            f" {source_count} sources) → {ticker_str}{implication_suffix}"
        )
    return "\n".join(lines)


async def get_active_narratives_async(
    tickers: list[str] | None = None, scan_date: date | None = None
) -> dict:
    """Get active narratives, optionally filtered by ticker list. Only confirmed+ maturity shown.

    Passes the full ticker list to `get_active_narratives` which uses
    `WHERE affected_tickers && $1` (array overlap) — single SQL query regardless
    of how many tickers are requested. No fan-out.
    """
    from shared.neon import get_active_narratives

    ref_date = scan_date or date.today()

    try:
        narratives = await get_active_narratives(tickers=tickers)
        # Agents only see confirmed or mature narratives (hide single-article noise)
        visible = [
            narrative
            for narrative in narratives
            if narrative.get("maturity") in ("confirmed", "mature")
        ]
        return {
            "narratives": visible,
            "prose": _format_narratives_prose(visible, ref_date),
        }
    except Exception as error:
        logger.warning("Failed to get active narratives: %s", error)
        return {
            "narratives": [],
            "error": f"Failed to get narratives: {error}",
            "prose": f"Active Narratives: failed to load — {error}",
        }


async def tool_get_active_narratives(
    tickers: list[str] | None = None, scan_date: date | None = None
) -> str:
    """Get developing news story threads with conviction scores and momentum."""
    result = await get_active_narratives_async(tickers, scan_date)
    return result.get("prose") or str(result)
