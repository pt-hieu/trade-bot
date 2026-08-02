"""Unit tests for the time-axis reconciler.

Covers the four rules + sentinel idempotency. ``evaluate_issue`` is a pure
function over an issue snapshot + comments + ``now``, so the tests inject
fake dicts that mirror the Linear GraphQL shape rather than mocking the
client.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from linear_reconciler import (
    RECONCILER_PREFIX,
    ReconcileSummary,
    already_ran,
    evaluate_issue,
    sentinel_path,
    write_sentinel,
)

NOW = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


def _issue(
    *,
    state_name: str,
    updated_at: datetime,
    labels: list[str] | None = None,
    identifier: str = "SWI-7",
    issue_id: str = "uuid-7",
) -> dict[str, object]:
    return {
        "id": issue_id,
        "identifier": identifier,
        "title": f"[MON] dummy {identifier}",
        "updatedAt": updated_at.isoformat().replace("+00:00", "Z"),
        "state": {"name": state_name},
        "labels": {"nodes": [{"name": name} for name in (labels or [])]},
    }


def _comment(*, body: str, created_at: datetime) -> dict[str, object]:
    return {
        "id": f"comment-{created_at.timestamp()}",
        "body": body,
        "createdAt": created_at.isoformat().replace("+00:00", "Z"),
    }


class TestInProgressSilentRule:
    def test_in_progress_silent_regression_watch_returns_to_monitoring(self) -> None:
        issue = _issue(
            state_name="In Progress",
            updated_at=NOW - timedelta(days=20),
            labels=["regression-watch", "morning"],
        )
        with patch(
            "scripts.linear_migration.reconciler_rules._git_commit_in_subjects_since",
            return_value=False,
        ):
            action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is not None
        assert action.rule == "in_progress_silent"
        assert action.new_state == "Monitoring"
        assert RECONCILER_PREFIX in action.comment_body

    def test_in_progress_silent_other_category_returns_to_triage(self) -> None:
        issue = _issue(
            state_name="In Progress",
            updated_at=NOW - timedelta(days=15),
            labels=["feature"],
        )
        with patch(
            "scripts.linear_migration.reconciler_rules._git_commit_in_subjects_since",
            return_value=False,
        ):
            action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is not None
        assert action.new_state == "Triage"

    def test_in_progress_with_recent_commit_skips(self) -> None:
        issue = _issue(
            state_name="In Progress",
            updated_at=NOW - timedelta(days=20),
            labels=["regression-watch"],
        )
        with patch(
            "scripts.linear_migration.reconciler_rules._git_commit_in_subjects_since",
            return_value=True,
        ):
            action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is None

    def test_in_progress_recent_activity_skips(self) -> None:
        issue = _issue(
            state_name="In Progress",
            updated_at=NOW - timedelta(days=2),
            labels=["regression-watch"],
        )
        action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is None


class TestConfirmRegressionRule:
    def test_silent_confirm_regression_escalates(self) -> None:
        issue = _issue(
            state_name="Confirm Regression",
            updated_at=NOW - timedelta(days=20),
            labels=["regression-watch"],
        )
        action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is not None
        assert action.rule == "confirm_regression_silent"
        assert action.new_state == "Escalated"

    def test_recent_activity_skips(self) -> None:
        issue = _issue(
            state_name="Confirm Regression",
            updated_at=NOW - timedelta(days=3),
            labels=["regression-watch"],
        )
        action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is None


class TestTriagePingRule:
    def test_triage_ping_after_seven_days(self) -> None:
        issue = _issue(state_name="Triage", updated_at=NOW - timedelta(days=10), labels=["bug"])
        action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is not None
        assert action.rule == "triage_ping"
        assert action.new_state is None  # comment-only

    def test_triage_recent_skips(self) -> None:
        issue = _issue(state_name="Triage", updated_at=NOW - timedelta(days=3), labels=["bug"])
        action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is None


class TestResolvedCandidateRule:
    def test_silent_resolved_candidate_with_verified_sha_closes(self) -> None:
        issue = _issue(
            state_name="Resolved Candidate",
            updated_at=NOW - timedelta(days=20),
            labels=["regression-watch"],
        )
        comments = [
            _comment(
                body="shipped in abcdef0123456789 — `SWI-7 :bug: fix(...): ...`",
                created_at=NOW - timedelta(days=21),
            )
        ]
        with patch(
            "scripts.linear_migration.reconciler_rules.subprocess_has_commit", return_value=True
        ):
            action = evaluate_issue(issue, now=NOW, comments=comments)
        assert action is not None
        assert action.rule == "resolved_candidate_close"
        assert action.new_state == "Resolved"

    def test_silent_resolved_candidate_without_sha_skips(self) -> None:
        issue = _issue(
            state_name="Resolved Candidate",
            updated_at=NOW - timedelta(days=20),
            labels=["regression-watch"],
        )
        action = evaluate_issue(issue, now=NOW, comments=[])
        assert action is None

    def test_silent_resolved_candidate_with_unverified_sha_skips(self) -> None:
        issue = _issue(
            state_name="Resolved Candidate",
            updated_at=NOW - timedelta(days=20),
            labels=["regression-watch"],
        )
        comments = [
            _comment(
                body="shipped in 9999999 (sha not in tree)",
                created_at=NOW - timedelta(days=21),
            )
        ]
        with patch(
            "scripts.linear_migration.reconciler_rules.subprocess_has_commit", return_value=False
        ):
            action = evaluate_issue(issue, now=NOW, comments=comments)
        assert action is None


class TestSentinelIdempotency:
    def test_sentinel_round_trip(self, tmp_path: Path) -> None:
        with patch("linear_reconciler.SENTINEL_DIR", tmp_path):
            run_date = NOW.date()
            assert not already_ran(run_date)
            summary = ReconcileSummary(run_date=run_date.isoformat())
            path = write_sentinel(summary)
            assert path == sentinel_path(run_date)
            assert already_ran(run_date)
