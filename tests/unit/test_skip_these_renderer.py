"""Bug 6 (run2 2026-05-14): PLX SKIP entry shipped literal [DERIVED_FROM_BELIEFS].

`_skip_bullet` now calls `strip_audit_tags` BEFORE sentence-splitting so a
leading provenance tag doesn't consume the first sentence — mirroring the
sibling renderers (my_holdings.py, what_to_do_today.py). max_len=200 covers
full DB rationales (114-194 chars).
"""

from __future__ import annotations

from pipeline.rendering.skip_these import _skip_bullet, render_skip_these


def test_strips_leading_audit_tag_keeps_full_first_sentence():
    entry = {
        "ticker": "PLX",
        "reason": (
            "[DERIVED_FROM_BELIEFS] Sustained underperformance vs sector "
            "with persistent net-negative foreign flow."
        ),
    }
    bullet = _skip_bullet(entry)

    assert "[DERIVED_FROM_BELIEFS]" not in bullet
    # Strip ran before the split, so the first real sentence is intact —
    # not eaten as if the tag were the first "sentence".
    assert "Sustained underperformance vs sector" in bullet


def test_full_db_rationale_renders_without_midword_cut():
    """A real-length DB rationale (no period) renders complete — max_len=200
    plus the word-boundary guard means no mid-word truncation."""
    reason = (
        "Insider selling accelerated over the past five sessions while "
        "institutional flow turned net-negative across the window here"
    )
    bullet = _skip_bullet({"ticker": "VIX", "reason": reason})

    assert bullet.endswith("here")  # full final word, no mid-word slice


def test_render_skip_these_strips_tags_in_section():
    out = render_skip_these(
        [{"ticker": "PLX", "reason": "[DERIVED_FROM_BELIEFS] Weak flow, distribution."}]
    )

    assert "SKIP THESE" in out
    assert "[DERIVED_FROM_BELIEFS]" not in out
    assert "PLX" in out


def test_missing_reason_renders_bare_ticker():
    assert _skip_bullet({"ticker": "PLX", "reason": None}) == "- PLX"
