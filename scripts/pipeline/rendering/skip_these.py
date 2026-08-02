"""Deterministic SKIP THESE renderer.

Before MON-2026-04-23-001, synthesis_picks LLM authored this section as free
prose derived from compressed sector text + gated_tickers list. The LLM
drifted — VPB/SZC/VRE rendered as SKIP while the daily_recommendations DB
had MBB/NLG/PVI/TPB/VIX. Fix: render SKIP THESE deterministically from the
same `skip_selector.select_skip_tickers` call the rec-builder uses.

Matches the pattern established by ``render_what_to_do_today``
(MON-2026-04-16-002).
"""

from __future__ import annotations

from shared.rules.audit_tags import strip_audit_tags
from shared.rules.skip_selector import SkipEntry
from shared.text_utils import split_first_sentence


def _skip_bullet(entry: SkipEntry) -> str:
    ticker = entry["ticker"]
    # Strip audit tags BEFORE sentence-splitting so a leading provenance
    # tag (e.g. [DERIVED_FROM_BELIEFS]) doesn't consume the first sentence.
    # max_len=200 covers full DB rationales (114-194 chars); the word-
    # boundary guard in split_first_sentence handles any overflow.
    reason = split_first_sentence(strip_audit_tags(entry.get("reason") or ""), max_len=200)
    if reason:
        return f"- {ticker} — {reason}"
    return f"- {ticker}"


def render_skip_these(skip_entries: list[SkipEntry]) -> str:
    """Render SKIP THESE section as plain ASCII bullets.

    Returns the section header even when the list is empty so readers see an
    explicit "no skips today" acknowledgement rather than a missing section.
    """
    lines: list[str] = ["SKIP THESE"]
    if not skip_entries:
        lines.append("- No sector or advocate-gated skips today.")
        return "\n".join(lines)
    for entry in skip_entries:
        lines.append(_skip_bullet(entry))
    return "\n".join(lines)
