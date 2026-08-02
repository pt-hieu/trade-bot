"""Unit tests for the write-back dedup sentinel bookkeeping."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from linear_migration import dedup


@pytest.fixture
def sentinel_tmpdir(tmp_path, monkeypatch):
    """Redirect SENTINEL_DIR to a tmp path for isolation."""
    monkeypatch.setattr(dedup, "SENTINEL_DIR", tmp_path / "sentinels")
    return tmp_path / "sentinels"


class TestComputeReportId:
    def test_same_text_same_id(self):
        text = "# Report\n\nSome content."
        assert dedup.compute_report_id(text) == dedup.compute_report_id(text)

    def test_different_text_different_id(self):
        a = dedup.compute_report_id("report A")
        b = dedup.compute_report_id("report B")
        assert a != b

    def test_id_is_12_hex_chars(self):
        report_id = dedup.compute_report_id("anything")
        assert len(report_id) == 12
        assert all(c in "0123456789abcdef" for c in report_id)


class TestSentinelLifecycle:
    def test_not_processed_initially(self, sentinel_tmpdir: Path):
        assert dedup.is_already_processed("abcdef123456") is False

    def test_record_then_detected(self, sentinel_tmpdir: Path):
        dedup.record_sentinel(
            "abcdef123456",
            source_kind="pipeline-review",
            touched_linear_ids=["SWY-1", "SWY-2"],
            created_linear_ids=["SWY-3"],
            note="smoke test",
        )
        assert dedup.is_already_processed("abcdef123456") is True
        loaded = dedup.load_sentinel("abcdef123456")
        assert loaded is not None
        assert loaded.source_kind == "pipeline-review"
        assert loaded.touched_linear_ids == ["SWY-1", "SWY-2"]
        assert loaded.created_linear_ids == ["SWY-3"]
        assert loaded.note == "smoke test"

    def test_load_missing_returns_none(self, sentinel_tmpdir: Path):
        assert dedup.load_sentinel("000000000000") is None

    def test_sentinel_path_matches_dir(self, sentinel_tmpdir: Path):
        path = dedup.sentinel_path("feedfacefeed")
        assert path.parent == sentinel_tmpdir
        assert path.name == "feedfacefeed.json"

    def test_sentinel_is_valid_json(self, sentinel_tmpdir: Path):
        path = dedup.record_sentinel(
            "beadfeedbead",
            source_kind="audit",
            touched_linear_ids=[],
            created_linear_ids=["SWY-99"],
        )
        raw = json.loads(path.read_text())
        assert raw["report_id"] == "beadfeedbead"
        assert raw["source_kind"] == "audit"
        assert "processed_at" in raw
