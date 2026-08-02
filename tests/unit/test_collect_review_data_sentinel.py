"""SWI-134: collector sentinel + freshness + atomic save tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from collect_review_data import _COMPLETION_SENTINEL_RE, fetch_markdown_briefs
from retro.data import save_quarantined_retrospective, save_retrospective


@pytest.fixture
def research_root(tmp_path, monkeypatch):
    """Point RESEARCH_ROOT at a temp dir for test isolation."""
    target = tmp_path / "research"
    target.mkdir()
    monkeypatch.setattr("collect_review_data.RESEARCH_ROOT", target)
    return target


def _seed(research_root: Path, target_date: str, filename: str, body: str) -> Path:
    day_dir = research_root / target_date
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_marks_complete_when_sentinel_present(research_root):
    body = (
        "# brief\n\n## SECTION ONE\nbody\n\n"
        "<!-- RETRO_COMPLETE: target_date=2026-05-05 run_id=abc ts=2026-05-05T08:30:00Z -->\n"
    )
    _seed(research_root, "2026-05-05", "retrospective.md", body)
    briefs = fetch_markdown_briefs("2026-05-05")
    assert briefs["retrospective"]["complete"] is True
    assert briefs["retrospective"]["fresh"] is True


def test_marks_incomplete_when_sentinel_absent(research_root):
    _seed(research_root, "2026-05-05", "retrospective.md", "# stale draft no sentinel\n")
    briefs = fetch_markdown_briefs("2026-05-05")
    assert briefs["retrospective"]["complete"] is False
    assert briefs["retrospective"]["fresh"] is False


def test_marks_stale_when_target_date_mismatches(research_root):
    body = (
        "# yesterday\n\n"
        "<!-- RETRO_COMPLETE: target_date=2026-05-04 run_id=abc ts=2026-05-04T08:00:00Z -->\n"
    )
    _seed(research_root, "2026-05-05", "retrospective.md", body)
    briefs = fetch_markdown_briefs("2026-05-05")
    assert briefs["retrospective"]["complete"] is True
    assert briefs["retrospective"]["fresh"] is False
    assert briefs["retrospective"]["sentinel_target_date"] == "2026-05-04"


def test_save_retrospective_atomic_rename(tmp_path):
    save_retrospective("body content here\n", "2026-05-05", tmp_path)
    out = tmp_path / "2026-05-05" / "retrospective.md"
    assert out.exists()
    assert not (tmp_path / "2026-05-05" / "retrospective.md.tmp").exists()
    text = out.read_text(encoding="utf-8")
    assert "RETRO_COMPLETE: target_date=2026-05-05" in text
    assert _COMPLETION_SENTINEL_RE.search(text) is not None


def test_save_quarantined_retrospective_includes_violations(tmp_path):
    save_quarantined_retrospective(
        date="2026-05-05",
        research_dir=tmp_path,
        deterministic_prefixes="## DETERMINISTIC PREFIXES\n- ACV: NOT_EXECUTED.",
        violations=["[EXECUTION_FABRICATION] ACV: outcome verb in prose"],
        rejected_draft="bad LLM draft text",
    )
    out = tmp_path / "2026-05-05" / "retrospective.md"
    text = out.read_text(encoding="utf-8")
    assert "QUARANTINED" in text
    assert "## VIOLATIONS" in text
    assert "EXECUTION_FABRICATION" in text
    assert "QUARANTINED LLM DRAFT" in text
    assert "RETRO_QUARANTINED: target_date=2026-05-05" in text
