"""SWI-127 — exact-match section headers + first-occurrence-wins guard.

Critic citations like `MY HOLDINGS / FPT: [verb_plan_mismatch]` previously
matched lenient `startswith("MY HOLDINGS ")`, then last-write-wins
overwrote the real MY HOLDINGS stanza with a sentinel-only continuation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def test_critic_citation_does_not_shadow_real_section():
    """A NARRATIVE REVIEW critic note that cites 'MY HOLDINGS / FPT:' must
    NOT shadow the real MY HOLDINGS stanza in the on-disk brief."""
    from shared.brief_parser import ALL_BRIEF_SECTIONS, extract_actionable_sections

    brief = "\n".join(
        [
            "MY HOLDINGS",
            "FPT: HOLD — thesis intact, no adverse catalyst.",
            "ACV: TRIM 200 — RSI 76 + foreign sell pressure.",
            "",
            "TOP PICKS",
            "GVR: BUY 300 @ 35.5k — breakout confirmed.",
            "",
            "WHAT TO DO TODAY",
            "1. Place GVR limit order",
            "2. Watch ACV intraday for trim trigger",
            "",
            "NARRATIVE REVIEW",
            "MY HOLDINGS / FPT: [verb_plan_mismatch] HOLD verb but no plan articulated.",
            "<!-- MORNING_COMPLETE: target_date=2026-05-11 -->",
        ]
    )
    sections = extract_actionable_sections(brief, section_names=ALL_BRIEF_SECTIONS)
    mh = sections.get("MY HOLDINGS", "")
    assert "FPT: HOLD" in mh
    assert "ACV: TRIM" in mh
    assert "verb_plan_mismatch" not in mh
    assert not mh.strip().endswith("-->")


def test_inline_split_isolates_sentence_glued_headers():
    """The genuine 'LLM glues a header to the end of a prose sentence'
    failure mode the original `_split_inline_sections` exists to handle:
    a sentence preceding a header on the same line must still let the
    parser recognise the header. Exact-match `_match_header` works
    because `_split_inline_sections` inserts `\\n` before the bare header
    and the rest of its body falls on subsequent lines."""
    from shared.brief_parser import ALL_BRIEF_SECTIONS, extract_actionable_sections

    text = "Preamble closing sentence. MY HOLDINGS\nFPT: HOLD\n\nTOP PICKS\nGVR: BUY"
    sections = extract_actionable_sections(text, section_names=ALL_BRIEF_SECTIONS)
    assert "FPT: HOLD" in sections.get("MY HOLDINGS", "")
    assert "GVR: BUY" in sections.get("TOP PICKS", "")


def test_prose_citation_does_not_create_phantom_section():
    """A prose mention like 'Today's NEWS THAT MATTERS shows ...' must NOT
    be promoted to a NEWS THAT MATTERS section header."""
    from shared.brief_parser import ALL_BRIEF_SECTIONS, extract_actionable_sections

    brief = "\n".join(
        [
            "MY HOLDINGS",
            "FPT: HOLD — Today's NEWS THAT MATTERS shows favorable IT-sector news.",
            "",
            "TOP PICKS",
            "GVR: BUY",
        ]
    )
    sections = extract_actionable_sections(brief, section_names=ALL_BRIEF_SECTIONS)
    mh = sections.get("MY HOLDINGS", "")
    assert "FPT: HOLD" in mh
    # The prose phrase stays inside MY HOLDINGS; no phantom NEWS THAT MATTERS
    # stanza pulls the prose away.
    nm = sections.get("NEWS THAT MATTERS", "")
    assert "favorable IT-sector news" not in nm


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
