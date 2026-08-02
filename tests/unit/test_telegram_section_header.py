"""Section-header matcher rejects verb/prose-prefixed lines (SWI-281 / SWI-127).

Lenient ``startswith`` matching once promoted critic citations like
``MY HOLDINGS / FPT: [...]`` into real section headers, corrupting downstream
renders. ``_match_section_header`` is exact-line equality (SWI-127, dad89a6c).
This pins that contract — re-run after any SWI-361 brief-format change.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from telegram_notify import _match_section_header


def test_verb_prefixed_header_not_matched():
    assert _match_section_header("MY HOLDINGS / FPT: [some content]") is None


def test_exact_header_still_matched():
    assert _match_section_header("MY HOLDINGS") == "MY HOLDINGS"
