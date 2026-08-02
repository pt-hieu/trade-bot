"""Pin the prompt↔tool prose contract for `fundamental.get_full_analysis`.

The 3 YAMLs (positions_value, positions_thesis, longterm_review) tell the LLM
to read three labeled sections — `=== VALUATION ===`, `=== EARNINGS QUALITY ===`,
`=== VALUATION HISTORY ===` — out of a single prose response. If the tool ever
reshapes its output, those prompt rules silently break. This test fails loudly
if the labels change.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _expected_sections() -> tuple[str, ...]:
    """Import header constants from fundamental.py so drift fails in ONE place."""
    from agents.tools.broker.domains.fundamental import (
        EARNINGS_QUALITY_HEADER,
        VALUATION_HEADER,
        VALUATION_HISTORY_HEADER,
    )

    return (VALUATION_HEADER, EARNINGS_QUALITY_HEADER, VALUATION_HISTORY_HEADER)


EXPECTED_SECTIONS = _expected_sections()


@pytest.fixture
def stub_sub_fetchers():
    """Patch the 3 _gather_* helpers so get_full_analysis runs without the DB/network."""
    from agents.tools.broker.domains import fundamental

    async def fake_valuation(_tickers):
        return "valuation prose"

    async def fake_eq(_tickers):
        return "earnings quality prose"

    async def fake_vh(_tickers):
        return "valuation history prose"

    with (
        patch.object(fundamental, "_gather_valuation", fake_valuation),
        patch.object(fundamental, "_gather_earnings_quality", fake_eq),
        patch.object(fundamental, "_gather_valuation_history", fake_vh),
    ):
        yield


def test_get_full_analysis_emits_three_labeled_sections(stub_sub_fetchers):
    from agents.tools.broker.domains.fundamental import get_full_analysis

    result = asyncio.run(get_full_analysis(["FPT"], _ctx={}))

    for section_header in EXPECTED_SECTIONS:
        assert section_header in result, (
            f"Missing section header {section_header!r}. Prompt rules in "
            "positions_value.yaml / positions_thesis.yaml / longterm_review.yaml "
            "reference these labels — the tool and prompt must stay in lockstep."
        )


def test_get_full_analysis_preserves_section_ordering(stub_sub_fetchers):
    """Prompt rules read sections positionally; enforce order on top of presence."""
    from agents.tools.broker.domains.fundamental import get_full_analysis

    result = asyncio.run(get_full_analysis(["FPT"], _ctx={}))
    offsets = [result.index(header) for header in EXPECTED_SECTIONS]
    assert offsets == sorted(offsets), (
        f"Section order drifted: {EXPECTED_SECTIONS} expected, "
        f"got offsets={offsets} in output:\n{result}"
    )


def test_get_full_analysis_has_supersedes_metadata():
    """Lock in the composite→atomic relationship the pre-commit hook reads."""
    from agents.tools.broker.registry import TOOL_CATALOG

    tool = TOOL_CATALOG.get("fundamental.get_full_analysis")
    assert tool is not None, "fundamental.get_full_analysis missing from registry"
    assert set(tool.supersedes) == {
        "fundamental.get_valuation",
        "fundamental.get_earnings_quality",
        "fundamental.get_valuation_history",
    }, (
        "supersedes tuple drift — update check_agent_yaml_composite_vs_atomic "
        "test expectations together with the registration."
    )
