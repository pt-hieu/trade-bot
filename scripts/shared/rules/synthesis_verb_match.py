"""Verb-match validator for synthesis_holdings paragraphs.

The deterministic header rendered by ``HoldingAction.bullet_verb()`` is the
authoritative verb for a holding. The LLM-emitted thesis paragraph must
START with the same verb token; any divergence is a brief-shipping defect
(FPT 2026-05-07: header rendered "HOLD FPT" while paragraph started with
"TRIM — thesis intact...").

Pure function so both the pydantic_ai output_validator path and unit tests
share the same regex. Regex is driven by ``typing.get_args(HoldingVerb)`` so
adding a new verb (e.g. REBALANCE) cannot drift the validator out of sync.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol, get_args

from shared.types.holding_verb import HoldingVerb

_VERB_PATTERN = re.compile(
    rf"^\s*({'|'.join(re.escape(v) for v in get_args(HoldingVerb))})\b",
    re.IGNORECASE,
)


class _ThesisLike(Protocol):
    @property
    def ticker(self) -> str: ...
    @property
    def paragraph(self) -> str: ...


def verb_mismatches(
    theses: Iterable[_ThesisLike],
    expected_verbs: dict[str, str],
) -> list[tuple[str, str, str]]:
    """Return list of ``(ticker, actual_verb, expected_verb)`` for mismatches.

    Skips theses whose paragraph does not start with a recognized verb (no
    expected verb on file, or unknown leading word). The caller is responsible
    for raising a retry / fallback when the returned list is non-empty.
    """
    mismatches: list[tuple[str, str, str]] = []
    for thesis in theses:
        match = _VERB_PATTERN.match(thesis.paragraph)
        if not match:
            continue
        actual = match.group(1).upper()
        expected = expected_verbs.get(thesis.ticker.upper())
        if expected and actual != expected.upper():
            mismatches.append((thesis.ticker, actual, expected))
    return mismatches
