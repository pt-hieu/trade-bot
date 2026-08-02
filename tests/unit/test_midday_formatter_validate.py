"""SWI-235 midday section-count gate (`validate_midday_markdown`).

Mirrors validate_synthesis_output for the morning brief: a real midday analysis
must carry the mandatory sections, so a degenerate render is distinguishable
from a deliberate skip-stub. Advisory only (returns warnings).
"""

from __future__ import annotations

from midday.formatter import generate_midday_markdown, validate_midday_markdown


def test_blank_markdown_flagged_empty():
    warnings = validate_midday_markdown("")
    assert any("MIDDAY OUTPUT EMPTY" in w for w in warnings)


def test_missing_sections_flagged():
    warnings = validate_midday_markdown("## Trading Mode: NORMAL\n\nsome prose")
    assert any("MIDDAY SECTION GAP" in w for w in warnings)
    assert any("Morning Reflection" in w for w in warnings)
    assert any("Afternoon Plan" in w for w in warnings)


def test_complete_markdown_clean():
    # A real generate_midday_markdown output carries all required sections.
    result = {
        "trading_mode": "NORMAL",
        "capital_note": "cash ok",
        "morning_reflection": "reflection",
        "afternoon_plan": [],
        "afternoon_note": None,
    }
    markdown = generate_midday_markdown(result, "2026-05-30")
    assert validate_midday_markdown(markdown) == []
