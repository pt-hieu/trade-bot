"""SWI-195: macro/geopolitical narratives collapse to ["VN-INDEX"].

Deterministic backstop to the narrative_labeler prompt rule: a mislabeled
multi-ticker macro/geopolitical narrative must not over-attribute to specific
names. Other narrative types keep their LLM-assigned tickers unchanged.
"""

from __future__ import annotations

import pytest

from agents.narrative_labeler import NarrativeLabel, collapse_macro_narrative_scope


def _label(narrative_type: str, tickers: list[str]) -> NarrativeLabel:
    return NarrativeLabel(
        narrative_key="k",
        theme="t",
        narrative_type=narrative_type,  # type: ignore[arg-type]
        affected_tickers=tickers,
        affected_sectors=["banking"],
        trading_implication="x",
        half_life_days=14,
    )


@pytest.mark.parametrize("narrative_type", ["geopolitical", "macro"])
def test_macro_narrative_collapses_to_vn_index(narrative_type: str):
    label = _label(narrative_type, ["FPT", "VIC", "MWG"])
    collapse_macro_narrative_scope(label)
    assert label.affected_tickers == ["VN-INDEX"]


def test_macro_already_vn_index_unchanged():
    label = _label("macro", ["VN-INDEX"])
    collapse_macro_narrative_scope(label)
    assert label.affected_tickers == ["VN-INDEX"]


def test_non_macro_narrative_keeps_tickers():
    label = _label("earnings", ["FPT", "VIC"])
    collapse_macro_narrative_scope(label)
    assert label.affected_tickers == ["FPT", "VIC"]
