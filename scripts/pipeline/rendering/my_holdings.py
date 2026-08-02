"""Deterministic MY HOLDINGS renderer.

Historically the MY HOLDINGS section was authored as free-text LLM prose
and regularly hallucinated structural facts — ``GEO_BENEFICIARY`` on
tickers outside the impacted set, trailing stops equal to the entry
price, and so on. This renderer produces the section from the same
authoritative ``list[HoldingAction]`` that drives ``render_what_to_do_today``.
The LLM only contributes a qualitative thesis paragraph per ticker;
every structural field (stop prices, P/L, geo badges) comes from Python.

Output contract: plain ASCII, no markdown, no emojis. Section header
``MY HOLDINGS`` on its own line, one stanza per holding ordered by
urgency then ticker.
"""

from __future__ import annotations

from datetime import datetime

from shared.formatting import format_snapshot_header
from shared.rules.audit_tags import strip_audit_tags
from shared.text_utils import split_first_sentence, truncate_with_ellipsis

from .models import HoldingAction

_URGENCY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _format_vnd(value: int | None) -> str:
    return f"{value:,}" if value is not None else "N/A"


def _format_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.1f}%"


def _stanza_header(action: HoldingAction) -> str:
    verb = action.bullet_verb()  # includes ticker and qty%
    if action.urgency and action.urgency != "MEDIUM":
        return f"{verb} [{action.urgency}]"
    return verb


def _position_line(action: HoldingAction) -> str | None:
    """Return the `Entry | Current | P/L` line, or None if nothing known."""
    if (
        action.entry_price_vnd is None
        and action.current_price_vnd is None
        and action.pnl_pct is None
    ):
        return None
    return (
        f"  Entry: {_format_vnd(action.entry_price_vnd)} | "
        f"Current: {_format_vnd(action.current_price_vnd)} | "
        f"P/L: {_format_pct(action.pnl_pct)}"
    )


def _stop_line(action: HoldingAction) -> str | None:
    """Return the consolidated stop line, or None if nothing known.

    Rendered as three `label: value` clauses joined with ` | `; clauses
    whose value is missing are omitted. A trailing stop is deliberately
    *only* printed when `trailing_stop_vnd` is set — preventing the
    MON-17-003 "Trailing stop: 84.5k" misrender where the LLM wrote the
    entry price into that field.
    """
    clauses: list[str] = []
    if action.catastrophic_floor_vnd is not None:
        clauses.append(f"Catastrophic floor: {action.catastrophic_floor_vnd:,}")
    elif action.stop_price_vnd is not None:
        clauses.append(f"Stop: {action.stop_price_vnd:,}")
    if action.breakeven_stop_vnd is not None:
        clauses.append(f"Breakeven: {action.breakeven_stop_vnd:,}")
    if action.trailing_stop_vnd is not None:
        clauses.append(f"Trailing stop: {action.trailing_stop_vnd:,}")
    if not clauses:
        return None
    return "  " + " | ".join(clauses)


def _badge_line(action: HoldingAction) -> str | None:
    return "  GEO_VICTIM" if action.geo_badge == "VICTIM" else None


def _thesis_line(thesis: str | None) -> str | None:
    if not thesis:
        return None
    # SWI-121: raise the cap to 600 chars and use truncate_with_ellipsis so
    # mid-word truncation ("...the GEO_BENEFICIARY catalyst remains") is
    # replaced with a visible "..." boundary. Pairs with the synthesis_holdings
    # YAML conciseness rule (target 2-3 sentences, ~500 chars).
    cleaned = truncate_with_ellipsis(thesis.replace("\n", " "), 600)
    if not cleaned:
        return None
    return f"  {cleaned}"


def render_my_holdings(
    actions: list[HoldingAction],
    llm_thesis_by_ticker: dict[str, str] | None = None,
    *,
    snapshot_at: datetime | None = None,
) -> str:
    """Render MY HOLDINGS as plain ASCII.

    Each stanza:
      <TICKER> <VERB>[<QTY_PCT>%] [urgency]
        Entry: X | Current: Y | P/L: Z%
        Catastrophic floor: F | Breakeven: B | Trailing stop: T
        GEO_VICTIM
        <llm thesis paragraph>

    Missing fields collapse silently — producing the safest brief we
    can without fabricating data.
    """
    theses = llm_thesis_by_ticker or {}
    lines: list[str] = ["MY HOLDINGS"]
    snapshot_header = format_snapshot_header(snapshot_at)
    if snapshot_header:
        lines.append(f"  {snapshot_header}")
    if not actions:
        lines.append("  No open positions today.")
        return "\n".join(lines)

    sorted_actions = sorted(
        actions,
        key=lambda a: (_URGENCY_RANK.get(a.urgency, 3), a.ticker),
    )

    for action in sorted_actions:
        lines.append("")
        lines.append(_stanza_header(action))
        position_line = _position_line(action)
        if position_line:
            lines.append(position_line)
        stop_line = _stop_line(action)
        if stop_line:
            lines.append(stop_line)
        badge_line = _badge_line(action)
        if badge_line:
            lines.append(badge_line)
        thesis_line = _thesis_line(theses.get(action.ticker) or theses.get(action.ticker.upper()))
        if thesis_line:
            lines.append(thesis_line)
        # Always surface the structural rationale from the alert — the
        # LLM thesis is optional flavor, the canonical "why" is this line.
        rationale = strip_audit_tags(action.rationale)
        if rationale and rationale != "No action required today":
            rationale_snippet = split_first_sentence(rationale, max_len=200)
            if rationale_snippet:
                lines.append(f"  Why: {rationale_snippet}")

    return "\n".join(lines).rstrip() + "\n"
