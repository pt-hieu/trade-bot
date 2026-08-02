"""Unit tests for the Linear -> markdown export renderers.

Covers the pure render functions (now in
``scripts/linear_migration/export_render.py``) and the resolved-window
filter that still lives in ``scripts/export_issues.py``. Live Linear
fetching is exercised in dogfood runs, not here.
"""

import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from export_issues import (
    LinearIssue,
    _as_rendered,
    filter_recent_resolved,
)
from linear_migration.export_render import (
    extract_evidence_fingerprint,
    extract_legacy_id,
    render_monitoring_items,
    render_resolved_items,
    split_title_tag,
)


def _issue(**overrides) -> LinearIssue:
    defaults = {
        "linear_id": "0000-aaaa",
        "identifier": "SWI-1",
        "title": "[MON] Null-token aggregator hang",
        "description": (
            "**Legacy ID:** `MON-2026-04-13-002`\n\n"
            "## Evidence\n\n2026-04-13: ACB/STB flagged with null-token hang on "
            "sector_aggregator.\n\n## Hypothesis\n\nQueue fetcher returns empty list "
            "when provider 429s."
        ),
        "state_type": "started",
        "state_name": "In Progress",
        "labels": ["regression-watch", "critical", "morning", "reasoning-and-output"],
        "updated_at": "2026-04-24T10:00:00Z",
        "completed_at": None,
    }
    defaults.update(overrides)
    return LinearIssue(**defaults)


class TestSplitTitleTag:
    def test_extracts_category_tag_and_body(self):
        tag, body = split_title_tag("[MON] Null-token aggregator hang")
        assert tag == "MON"
        assert body == "Null-token aggregator hang"

    def test_missing_prefix_yields_empty_tag(self):
        tag, body = split_title_tag("Plain title without prefix")
        assert tag == ""
        assert body == "Plain title without prefix"

    def test_accepts_all_known_prefixes(self):
        for prefix in ("MON", "DEF", "AUDIT", "ISSUE", "FEAT", "DEC"):
            tag, _ = split_title_tag(f"[{prefix}] title")
            assert tag == prefix


class TestExtractLegacyId:
    def test_extracts_legacy_id_from_description(self):
        legacy = extract_legacy_id("**Legacy ID:** `MON-2026-04-13-002`\nrest")
        assert legacy == "MON-2026-04-13-002"

    def test_missing_returns_empty(self):
        assert extract_legacy_id("no legacy id here") == ""


class TestEvidenceFingerprint:
    def test_extracts_evidence_section(self):
        description = "## Evidence\n\n2026-04-13: ACB flagged.\n\n## Hypothesis\n\nsomething"
        fingerprint = extract_evidence_fingerprint(description)
        assert "ACB flagged" in fingerprint
        assert "something" not in fingerprint

    def test_falls_back_to_full_text_when_no_evidence_heading(self):
        description = "No evidence section, just prose about the issue."
        fingerprint = extract_evidence_fingerprint(description)
        assert "No evidence section" in fingerprint

    def test_truncates_to_fingerprint_cap(self):
        long_description = "## Evidence\n\n" + ("x" * 1000)
        fingerprint = extract_evidence_fingerprint(long_description)
        assert len(fingerprint) <= 320


class TestRenderMonitoringItems:
    def test_includes_linear_and_legacy_id_header(self):
        markdown = render_monitoring_items([_as_rendered(_issue())])
        assert "## SWI-1 (MON-2026-04-13-002) — Null-token aggregator hang" in markdown

    def test_falls_back_to_linear_identifier_when_no_legacy_id(self):
        issue = _issue(title="Raw title", description="no legacy here")
        markdown = render_monitoring_items([_as_rendered(issue)])
        assert "## SWI-1 — Raw title" in markdown

    def test_includes_status_labels_last_updated(self):
        markdown = render_monitoring_items([_as_rendered(_issue())])
        assert "**Status:** In Progress" in markdown
        assert "critical" in markdown
        assert "2026-04-24T10:00:00Z" in markdown

    def test_sorts_by_updated_at_descending(self):
        older = _as_rendered(
            _issue(identifier="SWI-1", updated_at="2026-04-20T10:00:00Z", title="[MON] first")
        )
        newer = _as_rendered(
            _issue(identifier="SWI-2", updated_at="2026-04-24T10:00:00Z", title="[MON] second")
        )
        markdown = render_monitoring_items([older, newer])
        assert markdown.index("SWI-2") < markdown.index("SWI-1")


class TestRenderResolvedItems:
    def test_includes_fingerprint_and_resolved_date(self):
        resolved = _as_rendered(
            _issue(
                state_name="Done",
                state_type="completed",
                completed_at="2026-04-22T09:00:00Z",
            )
        )
        markdown = render_resolved_items([resolved], window_days=90)
        assert "Evidence fingerprint" in markdown
        assert "ACB/STB flagged" in markdown
        assert "2026-04-22T09:00:00Z" in markdown


class TestFilterRecentResolved:
    def test_drops_items_older_than_window(self):
        now = datetime.now(UTC)
        old_stamp = (now - timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_stamp = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = _issue(completed_at=old_stamp)
        recent = _issue(completed_at=recent_stamp)
        kept = filter_recent_resolved([old, recent])
        assert recent in kept
        assert old not in kept

    def test_drops_items_missing_timestamps(self):
        missing = _issue(completed_at=None, updated_at="")
        kept = filter_recent_resolved([missing])
        assert kept == []
