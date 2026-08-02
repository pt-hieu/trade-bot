"""
Shared formatting utilities for display output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


def format_vnd(amount, suffix: bool = False) -> str:
    """Format VND amount to human-readable string.

    Args:
        amount: Numeric amount in VND. None returns "N/A".
        suffix: If True, appends " VND" to output (e.g., "125.3M VND").

    Examples:
        format_vnd(1_500_000_000_000) → "1.5T"
        format_vnd(125_000_000) → "125.0M"
        format_vnd(85_500) → "85.5k"
        format_vnd(None) → "N/A"
        format_vnd(125_000_000, suffix=True) → "125.0M VND"
    """
    if amount is None:
        return "N/A"
    try:
        v = float(amount)
    except (ValueError, TypeError):
        return str(amount)

    sign = "-" if v < 0 else ""
    av = abs(v)
    sfx = " VND" if suffix else ""

    if av >= 1e12:
        return f"{sign}{av / 1e12:.1f}T{sfx}"
    if av >= 1e9:
        return f"{sign}{av / 1e9:.1f}B{sfx}"
    if av >= 1e6:
        return f"{sign}{av / 1e6:.1f}M{sfx}"
    if av >= 1e3:
        return f"{sign}{av / 1e3:.1f}k{sfx}"
    return f"{sign}{int(av)}{sfx}"


def format_price_k(price: float) -> str:
    """Format VND price as 'Xk' display string (e.g., 93000 -> '93.0k')."""
    if not price:
        return "N/A"
    return f"{price / 1000:.1f}k"


def format_snapshot_header(snapshot_at: datetime | None) -> str | None:
    """Canonical "Prices last written" header for MY HOLDINGS / portfolio block.

    Returns ``None`` when ``snapshot_at`` is missing — renderers default-tolerate
    via ``if header: lines.append(header)``. SWI-121.

    The label is intentionally NOT "as of": ``portfolio_holdings.updated_at`` is
    a row-mutation timestamp, not a market observation timestamp. Honest labeling
    so operators are not gaslit on stale-data days.
    """
    if snapshot_at is None:
        return None
    return f"Prices last written: {snapshot_at:%Y-%m-%d %H:%M UTC}"


def format_pct(value: float) -> str:
    """Format percentage with sign (e.g., 4.3 -> '+4.3%')."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def format_belief_lines(
    beliefs: list[dict],
    max_narrative: int = 100,
) -> list[str]:
    """Format belief dicts into compact one-line-per-ticker strings for LLM context.

    Used by position_strategist, entry_strategist, and synthesis_writers to inject
    belief consensus into agent prompts.

    Args:
        beliefs: List of belief dicts with ticker, direction, conviction, belief_narrative.
        max_narrative: Max characters for narrative truncation.

    Returns:
        List of formatted strings like "  TCB: BULLISH (80%) — credit growth accelerating"
    """
    lines = []
    for belief in beliefs:
        ticker = belief.get("ticker") or "?"
        direction = belief.get("direction") or "NEUTRAL"
        conviction = float(belief.get("conviction") or 0)
        narrative = (belief.get("belief_narrative") or "")[:max_narrative]
        lines.append(f"  {ticker}: {direction} ({conviction:.0%}) — {narrative}")
    return lines
