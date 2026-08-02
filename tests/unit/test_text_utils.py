"""Tests for shared.text_utils.split_first_sentence."""

from __future__ import annotations

import pytest

from shared.text_utils import split_first_sentence, truncate_with_ellipsis


def test_empty_input_returns_empty_string():
    assert split_first_sentence(None) == ""
    assert split_first_sentence("") == ""
    assert split_first_sentence("   ") == ""


def test_first_sentence_only():
    assert split_first_sentence("First sentence. Second sentence. Third.") == "First sentence"


def test_preserves_decimals_trailed_by_digit():
    """The 2026-04-17 leak — naive split('.',1) on 'RSI 55.3' corrupts the number."""
    text = "Entry 32.5k. Stop 25k."
    assert split_first_sentence(text) == "Entry 32.5k"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("RSI 55.3 indicates overbought. Wait.", "RSI 55.3 indicates overbought"),
        ("Beta 0.9 and P/E 15.2. Cheap.", "Beta 0.9 and P/E 15.2"),
        ("Stop-loss at 92.5k", "Stop-loss at 92.5k"),
    ],
)
def test_decimals_preserved(text, expected):
    assert split_first_sentence(text) == expected


def test_no_period_returns_whole_text_trimmed():
    assert split_first_sentence("No period here") == "No period here"
    assert split_first_sentence("  trimmed  ") == "trimmed"


def test_max_len_single_token_hard_cuts():
    """A single no-space token longer than max_len still hard-cuts —
    documented best-effort limitation, not a regression."""
    long = "a" * 300 + ". short"
    result = split_first_sentence(long, max_len=50)
    assert len(result) == 50
    assert result == "a" * 50


def test_trailing_period_no_second_sentence():
    """Period at end-of-string — first sentence is everything up to it."""
    assert split_first_sentence("Done.") == "Done"


# ── Bug 5 (run2 2026-05-14): word-boundary backtrack defect class ─────────
# split_first_sentence + truncate_with_ellipsis previously hard-sliced
# mid-word. The fix backtracks to the last full word WHEN a space exists
# within range. This is the shared-utility test gating 5 call sites.


@pytest.mark.parametrize("max_len", [120, 140, 200, 240, 300])
def test_split_first_sentence_backtracks_to_full_word(max_len):
    """An over-length no-boundary string ends on a full word, never mid-word."""
    text = " ".join(["sustained"] * 60)  # well over every max_len, spaces present
    result = split_first_sentence(text, max_len=max_len)
    assert len(result) <= max_len
    # No partial trailing token: every space-delimited piece is the full word.
    assert all(piece == "sustained" for piece in result.split())
    assert not result.endswith(" ")


def test_split_first_sentence_stays_decimal_safe_after_backtrack():
    """The sentence-boundary regex runs before the slice; rsplit on space
    cannot re-break a decimal (decimals carry no internal space)."""
    text = "RSI 55.3 indicates a stretched but still climbing momentum profile here"
    result = split_first_sentence(text, max_len=20)
    assert "55.3" in result
    assert ".3" not in result.replace("55.3", "")  # decimal not severed


def test_split_first_sentence_short_multiword_unchanged():
    """A multi-word string under max_len is returned whole — the backtrack
    must NOT fire when no truncation happened."""
    assert split_first_sentence("Banking strength intact", max_len=180) == (
        "Banking strength intact"
    )


@pytest.mark.parametrize("max_len", [120, 140, 200, 240, 300])
def test_truncate_with_ellipsis_backtracks_to_full_word(max_len):
    text = " ".join(["momentum"] * 60)
    result = truncate_with_ellipsis(text, max_len)
    assert result.endswith("...")
    assert len(result) <= max_len
    body = result[:-3]
    assert all(piece == "momentum" for piece in body.split())
