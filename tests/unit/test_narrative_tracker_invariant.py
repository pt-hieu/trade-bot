"""Tests for the silent-failure invariants in data.narrative_tracker.

Covers AUDIT-2026-04-24-001 / ISSUE-2026-04-24-003: the narrative-tracker used
to swallow every labeler error inside `except Exception`, masking outages. The
invariants now raise `NarrativeTrackerSilentFailure` on high-volume zero-output
days and weekend-shape days must still pass silently.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest

from data import narrative_mutations, narrative_tracker


def _make_articles(count: int) -> list[dict]:
    return [
        {
            "id": f"art-{idx:04d}",
            "title": f"Synthetic headline {idx}",
            "summary": "x" * 80,
            "sentiment_score": 0.1,
        }
        for idx in range(count)
    ]


@pytest.mark.asyncio
async def test_silent_failure_raises_on_zero_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """200 articles + zero output → must raise NarrativeTrackerSilentFailure."""
    scan_date = date(2026, 4, 24)
    articles = _make_articles(200)

    # Patch everything that hits external state.
    async def _list_articles_range(*_args: Any, **_kwargs: Any) -> list[dict]:
        return articles

    async def _get_all_active_with_embeddings() -> list[dict]:
        return []

    def _embed_articles(arts: list[dict]) -> dict[str, list[float]]:
        return {str(a["id"]): [0.1, 0.2, 0.3] for a in arts}

    def _build_centroid_index(_narratives: list[dict]) -> dict[str, dict]:
        return {}

    def _match_existing_narrative(*_args: Any, **_kwargs: Any) -> str | None:
        return None

    async def _label_narrative_raises(*_args: Any, **_kwargs: Any) -> Any:
        raise TimeoutError("synthetic provider hang")

    # Stub agent module so _create_narrative's inner import succeeds.
    import sys
    import types

    stub_module = types.ModuleType("agents.narrative_labeler")
    stub_module.label_narrative = _label_narrative_raises  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agents.narrative_labeler", stub_module)

    monkeypatch.setattr(narrative_tracker, "list_articles_range", _list_articles_range)
    monkeypatch.setattr(
        narrative_tracker, "get_all_active_with_embeddings", _get_all_active_with_embeddings
    )
    monkeypatch.setattr(narrative_tracker, "embed_articles", _embed_articles)
    monkeypatch.setattr(narrative_tracker, "build_centroid_index", _build_centroid_index)
    monkeypatch.setattr(narrative_tracker, "match_existing_narrative", _match_existing_narrative)
    # Anything below is not reached when the invariant fires, but monkey-patch
    # to keep the test hermetic if the guard ever shifts.
    monkeypatch.setattr(
        narrative_tracker, "refresh_all_conviction_scores", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(narrative_tracker, "refresh_narrative_maturity", AsyncMock(return_value=0))
    monkeypatch.setattr(narrative_tracker, "mark_stale_narratives", AsyncMock(return_value=0))
    monkeypatch.setattr(narrative_tracker, "mark_dead_narratives", AsyncMock(return_value=0))
    monkeypatch.setattr(
        narrative_tracker, "batch_count_distinct_sources", AsyncMock(return_value={})
    )
    monkeypatch.setattr(narrative_tracker, "update_article_narrative", AsyncMock(return_value=None))

    with pytest.raises(narrative_tracker.NarrativeTrackerSilentFailure) as excinfo:
        await narrative_tracker.track_narratives(scan_date)

    assert excinfo.value.article_count == 200
    assert excinfo.value.scan_date == scan_date


@pytest.mark.asyncio
async def test_happy_path_below_threshold_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """30 articles + 1 successful creation → invariant must stay quiet (weekend-shape day)."""
    scan_date = date(2026, 4, 26)  # Sunday
    articles = _make_articles(30)

    async def _list_articles_range(*_args: Any, **_kwargs: Any) -> list[dict]:
        return articles

    async def _get_all_active_with_embeddings() -> list[dict]:
        return []

    def _embed_articles(arts: list[dict]) -> dict[str, list[float]]:
        return {str(a["id"]): [0.1, 0.2, 0.3] for a in arts}

    def _build_centroid_index(_narratives: list[dict]) -> dict[str, dict]:
        return {}

    match_calls = {"count": 0}

    def _match_existing_narrative(*_args: Any, **_kwargs: Any) -> str | None:
        match_calls["count"] += 1
        return None

    class _Label:
        narrative_key = "weekend_noise"
        theme = "Weekend news noise"
        narrative_type = "general"
        affected_tickers: list[str] = []
        affected_sectors = ["general"]
        trading_implication = "No direct impact"
        half_life_days = 3

    narrative_created = {"count": 0}

    async def _label_narrative(*_args: Any, **_kwargs: Any) -> _Label:
        narrative_created["count"] += 1
        if narrative_created["count"] == 1:
            return _Label()
        raise TimeoutError("synthetic")

    import sys
    import types

    stub_module = types.ModuleType("agents.narrative_labeler")
    stub_module.label_narrative = _label_narrative  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agents.narrative_labeler", stub_module)

    async def _upsert_narrative(_data: dict) -> str:
        return "narr-123"

    monkeypatch.setattr(narrative_mutations, "upsert_narrative", _upsert_narrative)
    monkeypatch.setattr(narrative_mutations, "add_narrative_update", AsyncMock(return_value=None))

    monkeypatch.setattr(narrative_tracker, "list_articles_range", _list_articles_range)
    monkeypatch.setattr(
        narrative_tracker, "get_all_active_with_embeddings", _get_all_active_with_embeddings
    )
    monkeypatch.setattr(narrative_tracker, "embed_articles", _embed_articles)
    monkeypatch.setattr(narrative_tracker, "build_centroid_index", _build_centroid_index)
    monkeypatch.setattr(narrative_tracker, "match_existing_narrative", _match_existing_narrative)
    monkeypatch.setattr(narrative_tracker, "update_article_narrative", AsyncMock(return_value=None))
    monkeypatch.setattr(
        narrative_tracker, "refresh_all_conviction_scores", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(narrative_tracker, "refresh_narrative_maturity", AsyncMock(return_value=0))
    monkeypatch.setattr(narrative_tracker, "mark_stale_narratives", AsyncMock(return_value=0))
    monkeypatch.setattr(narrative_tracker, "mark_dead_narratives", AsyncMock(return_value=0))
    monkeypatch.setattr(
        narrative_tracker, "batch_count_distinct_sources", AsyncMock(return_value={})
    )

    result = await narrative_tracker.track_narratives(scan_date)
    # 30 < SILENT_FAILURE_MIN_ARTICLES=40, so invariant doesn't fire even if ratio low.
    assert isinstance(result, dict)
    assert "assigned" in result and "created" in result
