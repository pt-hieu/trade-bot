"""Narrative domain tools."""

from datetime import date

from ..helpers import cached_tool_call
from ..registry import ToolDomain, register_domain_tool


async def _fetch_narratives(tickers: list[str] | None, scan_date: date | None) -> str:
    from ...narratives import get_active_narratives_async

    result = await get_active_narratives_async(tickers=tickers, scan_date=scan_date)
    return result.get("prose") or str(result)


async def get_active(tickers: list[str] | None = None, *, _ctx: dict) -> str:
    """Get confirmed news story threads with conviction scores and momentum.
    Only shows narratives corroborated by 2+ sources (hides single-article noise).
    Pass tickers list to filter, or omit for all.

    Returns:
        Prose listing each confirmed narrative with title, affected
        tickers, conviction score, momentum direction, and a short
        summary. Falls back to the stringified dict if the underlying
        helper omits the `prose` key.
    """
    scan_date = _ctx.get("scan_date")
    cache = _ctx.get("_tool_cache")

    if not tickers:
        cache_key = f"active_narratives:{scan_date}:all"
    else:
        ticker_part = ",".join(sorted(t.upper() for t in tickers))
        cache_key = f"active_narratives:{scan_date}:{ticker_part}"

    return await cached_tool_call(
        cache,
        cache_key,
        lambda: _fetch_narratives(tickers, scan_date),
    )


register_domain_tool(
    "narrative.get_active",
    ToolDomain.NARRATIVE,
    get_active,
    context_keys=("scan_date", "_tool_cache"),
    accepts_tickers=True,
    returns_hint="prose — confirmed narratives + conviction",
)
