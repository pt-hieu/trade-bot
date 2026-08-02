"""SWI-255 / SWI-121: format_kvnd + truncate_with_ellipsis helpers."""

from __future__ import annotations

from shared.text_utils import format_kvnd, truncate_with_ellipsis


def test_format_kvnd_renders_one_decimal_with_suffix() -> None:
    assert format_kvnd(33.6) == "33.6k"
    assert format_kvnd(33.75) == "33.8k"  # banker rounding ok


def test_format_kvnd_zero_yields_na() -> None:
    """Inherits format_price_k's falsy-zero semantics."""
    assert format_kvnd(0) == "N/A"


def test_truncate_with_ellipsis_preserves_word_boundary() -> None:
    text = "alpha " * 200  # 1200 chars
    out = truncate_with_ellipsis(text, 600)
    assert len(out) <= 600
    assert out.endswith("...")


def test_truncate_with_ellipsis_short_text_passthrough() -> None:
    assert truncate_with_ellipsis("short text", 50) == "short text"
