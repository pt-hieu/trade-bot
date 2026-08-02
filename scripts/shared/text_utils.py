"""Shared text extraction utilities.

Centralizes the first-sentence extraction pattern used across agent
fallbacks and rendering, replacing scattered ``split('.', 1)[0]`` calls
that corrupt decimals like ``RSI 55.3`` and ``Entry 32.5k``.
"""

from __future__ import annotations

import re

# Sentence boundary: a period followed by whitespace or end-of-string.
# Avoids splitting on decimal points in numbers.
_SENTENCE_BOUNDARY = re.compile(r"\.(?:\s|$)")

# Bare 3-letter VN ticker token, word-boundary anchored. Shared by LLM-output
# scanners in synthesis_picks_writer (ticker-drop detection) and
# afternoon_ticker_reconciler (ticker promotion from reason text).
TICKER_TOKEN_RE = re.compile(r"\b([A-Z]{3})\b")


def split_first_sentence(text: str | None, max_len: int = 180) -> str:
    """Return the first sentence of `text`, truncated to `max_len`.

    Splits on a period followed by whitespace (or end of string). Decimals
    like "RSI 55.3" and "Entry 32.5k" stay intact because the period is
    followed by a digit, not whitespace.

    When no sentence boundary is found, returns the whole (trimmed) text
    truncated to `max_len`. Empty / None input returns ''.

    Truncation backtracks to the last full word so the cut never lands
    mid-word (SWI-119). Best-effort: a single token longer than `max_len`
    (no internal space) still hard-cuts. The sentence-boundary regex runs
    before the slice, and `rsplit(" ", 1)` cannot re-break a decimal
    (decimals carry no internal space) — so "RSI 55.3" stays intact.
    """
    if not text:
        return ""
    stripped = text.strip()
    if not stripped:
        return ""
    parts = _SENTENCE_BOUNDARY.split(stripped, maxsplit=1)
    first = parts[0].strip() if parts else stripped
    if len(first) <= max_len:
        return first
    return first[:max_len].rsplit(" ", 1)[0]


def format_kvnd(value: float | int) -> str:
    """Render a thousands-of-VND price for narrative input (SWI-255).

    Thin wrapper over :func:`shared.formatting.format_price_k` (which takes
    raw VND); accepts the kVND units already used in retro evaluation rows
    (``eod_price``, ``prev_close``, ``entry_price`` are stored as
    thousands-of-VND, see ``insert_records/_common.py:319``).
    ``33.6 -> "33.6k"``; ``0 -> "N/A"`` (inherits format_price_k semantics).

    Single canonical shape — never mix with bare VND integers in the same
    formatter line. Three drifted shapes in retro_commentary inputs (``:,.0f``
    truncation, ``:,.1f`` with suffix, full ``:,VND`` integer) gave the LLM
    a precision gap; agent invented ``34,750`` for TCB on 2026-05-13.
    """
    from shared.formatting import format_price_k

    return format_price_k(value * 1000)


def truncate_with_ellipsis(text: str, max_len: int) -> str:
    """Hard-cap ``text`` at ``max_len``; append ``"..."`` if cut.

    Backtracks to the last full word so the cut never lands inside a word
    (SWI-121). Used by MY HOLDINGS thesis rendering to replace the silent
    ``[:280]`` slice that left sentences truncated mid-word. Best-effort:
    a single token longer than ``max_len`` (no internal space) still
    hard-cuts.
    """
    cleaned = text.strip()
    if len(cleaned) <= max_len:
        return cleaned
    head = cleaned[: max_len - 3].rsplit(" ", 1)[0]
    return head + "..."
