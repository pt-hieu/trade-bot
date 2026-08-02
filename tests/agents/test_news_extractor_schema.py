"""Schema-shape guard for ``news_extractor``.

The MiniMax fallback hangs on nested-``BaseModel`` schemas (provider quirk —
SWI: pipeline review 2026-05-07). When the news_extractor schema is flat,
``disable_fallback`` can stay false; when a nested ``BaseModel`` field is
introduced, the fallback must be turned off again with a rationale.

This test fails loudly if anyone adds a nested ``BaseModel`` field to
``NewsExtractionRaw`` without updating the config — preventing a silent
regression where MiniMax handles every fallback by hanging.
"""

from __future__ import annotations

from typing import Union, get_args, get_origin

import pytest
from pydantic import BaseModel


def test_news_extraction_raw_no_nested_basemodel():
    """Walk every field annotation and assert no inner type is a BaseModel."""
    from agents.news_extractor import NewsExtractionRaw

    for name, field in NewsExtractionRaw.model_fields.items():
        candidates: list[object] = [field.annotation]
        while candidates:
            candidate = candidates.pop()
            origin = get_origin(candidate)
            if origin in (Union, list, tuple, set, frozenset, dict):
                candidates.extend(get_args(candidate))
                continue
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                pytest.fail(
                    f"NewsExtractionRaw.{name} has nested BaseModel "
                    f"{candidate.__name__}; MiniMax fallback will hang. "
                    "If nested model is required, set disable_fallback: true "
                    "in news_extractor.yaml with rationale."
                )


def test_news_extractor_fallback_enabled():
    """Guard against accidental disable_fallback flip without schema review."""
    from pathlib import Path

    import yaml

    config_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "agents"
        / "configs"
        / "news_extractor.yaml"
    )
    config = yaml.safe_load(config_path.read_text())
    assert config.get("disable_fallback") is False, (
        "news_extractor.yaml should have disable_fallback: false because the "
        "schema is flat. If you set it back to true, document the new nested "
        "schema in the config rationale."
    )
