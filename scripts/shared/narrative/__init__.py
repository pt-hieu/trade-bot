"""Narrative-truth helpers shared across agents.

Pure-Python guardrails that bind LLM prose to deterministic structural
truth. Used by retro validators (stop / entry / execution fabrication),
midday override-reason gates, and the `*_prefix` renderers that prepend
authoritative facts to LLM commentary.

The single helper `narrative_truth_check` lets every check declare
(regex, structural value, expected value) and reuse the same matching
core — that uniformity is what makes future siblings (target-hit,
trim, longterm-reduce) cheap to add (SWI-255 round-2 review Q2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.text_utils import format_kvnd

_EXECUTION_PHRASES = re.compile(
    r"executed\s+correctly"
    r"|exit\s+executed"
    r"|position\s+closed"
    r"|closed\s+at\b"
    r"|was\s+closed\b"
    r"|taken\s+at\s+stop"
    r"|stopped\s+out\s+at"
    r"|exit\s+(?:was\s+)?(?:taken|filled|completed)",
    re.IGNORECASE,
)


@dataclass
class NarrativeViolation:
    """Generic narrative-vs-truth mismatch result."""

    check: str
    severity: str
    detail: str
    suggestion: str


def narrative_truth_check(
    text: str,
    *,
    phrases: re.Pattern[str],
    structural_value: object,
    expected: object,
    check_name: str,
    severity: str = "critical",
    detail: str | None = None,
    suggestion: str | None = None,
) -> NarrativeViolation | None:
    """Flag when ``text`` makes a narrative claim contradicted by structure.

    Returns a violation when ``phrases`` matches ``text`` AND the
    structural value differs from ``expected``. Returns None otherwise.

    Generalises the regex-vs-flag pattern from `_check_stop_fabrication`
    and `_check_entry_fabrication` so additional checks (execution,
    target-hit, trim) become 3-line wrappers. See SWI-255.
    """
    if not text:
        return None
    if structural_value == expected:
        return None
    if not phrases.search(text):
        return None
    return NarrativeViolation(
        check=check_name,
        severity=severity,
        detail=detail or f"narrative matched {check_name} pattern but structural value != expected",
        suggestion=suggestion
        or "Remove the narrative claim or fix the underlying structural data.",
    )


def format_execution_prefix(eval_row: dict) -> str:
    """Authoritative one-line execution prefix for retro analyses.

    Returns ``"NOT_EXECUTED."`` when the trade did not actually close
    today; otherwise returns ``"EXECUTED: exit=<vnd>VND, pnl=<pct>%."``
    None-safe via the ``r.get(k) or default`` pattern (CLAUDE.md).
    """
    if not eval_row.get("trade_executed"):
        return "NOT_EXECUTED."

    actual_exit = eval_row.get("actual_exit_price_vnd") or 0
    actual_pl = eval_row.get("actual_pl_pct") or 0.0
    return f"EXECUTED: exit={int(actual_exit):,}VND, pnl={actual_pl:+.2f}%."


def format_price_prefix(eval_row: dict) -> str:
    """Deterministic price stamp for non-executed retro rows (SWI-255).

    Mirrors :func:`format_execution_prefix` shape but emits the EOD /
    prev-close pair instead of an exit fact. Empty string when either
    value is missing — prefix-stamping then degrades gracefully rather
    than asserting a price the agent has not been given.

    Both prices are stored in thousands-of-VND (see
    ``insert_records/_common.py:319``: ``eod_vnd = int(eod_price * 1000)``);
    we render via :func:`format_kvnd` so the agent's input never carries
    a bare ``"34"`` rounding that invites hallucinated decimals like
    ``"34,750"`` (TCB on 2026-05-13).
    """
    eod = eval_row.get("eod_price")
    prev = eval_row.get("prev_close")
    if eod is None or prev is None:
        return ""
    return f"[EOD: {format_kvnd(eod)} VND, prev close: {format_kvnd(prev)} VND]"


__all__ = [
    "_EXECUTION_PHRASES",
    "NarrativeViolation",
    "format_execution_prefix",
    "format_price_prefix",
    "narrative_truth_check",
]
