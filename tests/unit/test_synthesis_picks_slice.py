"""Bug 3 (run2 2026-05-14): synthesis_picks CoT preamble leaked into the brief.

`_slice_to_top_picks_header` structurally enforces the invariant that
picks_text begins at the `TOP PICKS` header — dropping any chain-of-thought
preamble the LLM emitted before it. No-header input is returned unchanged
and warns (fail-loud) so genuine format drift surfaces.
"""

from __future__ import annotations

from agents.synthesis import _slice_to_top_picks_header


def test_slices_cot_preamble_before_top_picks_header():
    text = (
        "Now I have the full picture of the sector signals and holdings.\n"
        "I'll present VCB and VRE as today's picks.\n"
        "TOP PICKS\n"
        "VCB (banking) BUY\n"
        "Entry 85,500 | Stop 80,000 | Target 95,000\n"
    )
    result = _slice_to_top_picks_header(text)

    assert result.startswith("TOP PICKS")
    assert "Now I have" not in result
    assert "I'll present" not in result


def test_header_already_first_line_unchanged():
    text = "TOP PICKS\nVCB (banking) BUY\nEntry 85,500 | Stop 80,000"
    assert _slice_to_top_picks_header(text) == text


def test_defensive_header_match_casing_and_parenthetical():
    """Tolerates 'Top Picks' casing and a 'TOP PICKS (3)' parenthetical."""
    text = "some preamble line\nTop Picks (3)\nVCB BUY"
    result = _slice_to_top_picks_header(text)
    assert result.startswith("Top Picks (3)")


def test_no_header_returns_unchanged_and_warns(caplog):
    text = "VCB (banking) BUY\nEntry 85,500 | Stop 80,000"
    with caplog.at_level("WARNING"):
        result = _slice_to_top_picks_header(text)

    assert result == text  # fail-loud: keep text so format drift surfaces
    assert "no TOP PICKS header" in caplog.text
