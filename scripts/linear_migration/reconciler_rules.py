"""Pure-function rule layer for the time-axis reconciler.

Lifted out of ``scripts/linear_reconciler.py`` so the runner stays under the
350-line cap. ``evaluate_issue`` is the only public entrypoint — given an
issue snapshot + its comments + ``now``, it returns the proposed
``ReconcileAction`` or ``None`` when no rule fires. All four rules live here
so the unit tests can exercise them without an MCP client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from scripts.linear_migration.auto_promote import parse_iso_datetime
from scripts.linear_migration.findings_schema import FindingCategory
from scripts.linear_migration.git_utils import (
    commit_subject_references,
    commits_grep_since,
)

IN_PROGRESS_SILENCE_DAYS = 14
CONFIRM_REGRESSION_SILENCE_DAYS = 14
TRIAGE_PING_DAYS = 7
RESOLVED_CANDIDATE_SILENCE_DAYS = 14

RECONCILER_PREFIX = "RECONCILED:"
SHA_PATTERN = re.compile(r"\b([0-9a-f]{7,40})\b")
SWI_PATTERN = re.compile(r"\bSWI-\d+\b")

# Source vocabulary from FindingCategory + the legacy 'Bug' label name (the
# workspace 'Bug' label predates the cutover and is mapped via labels.json).
_CATEGORY_LABELS: tuple[str, ...] = tuple(c.value for c in FindingCategory) + ("Bug",)


@dataclass
class ReconcileAction:
    """One transition or comment proposal. ``execute`` records what shipped."""

    swi_id: str
    rule: str
    new_state: str | None  # None = comment-only ping
    comment_body: str
    executed: bool = False


def _git_commit_in_subjects_since(swi_id: str, since: datetime) -> bool:
    """Soft "developer is working on it" signal — wraps git_utils."""
    return commits_grep_since(swi_id, since.isoformat())


def subprocess_has_commit(sha: str, swi_id: str) -> bool:
    """Wrapper kept so tests/external callers can monkeypatch this name."""
    return commit_subject_references(sha, swi_id)


def _category_label(labels: set[str]) -> str | None:
    """Resolve the issue's category label name (e.g. ``regression-watch``)."""
    for candidate in _CATEGORY_LABELS:
        if candidate in labels:
            return candidate
    return None


def _last_activity(issue: dict[str, object], comments: list[dict[str, object]]) -> datetime:
    """Latest timestamp across the issue's ``updatedAt`` and any comment."""
    candidates: list[datetime] = [parse_iso_datetime(cast(str, issue["updatedAt"]))]
    for comment in comments:
        created = comment.get("createdAt")
        if isinstance(created, str):
            candidates.append(parse_iso_datetime(created))
    return max(candidates)


def _closing_commit_in_comments(swi_id: str, comments: list[dict[str, object]]) -> str | None:
    """Find the most recent commit-sha reference in any comment. Looks for
    ``shipped in <sha>`` (post-commit hook) or any 7–40 hex token mentioned
    near a SWI reference. Returns the sha string or None.
    """
    for comment in reversed(comments):  # newest first
        body = cast(str, comment.get("body") or "")
        if "shipped in" not in body and "closing_commit" not in body:
            # Only examine comments that look commit-related to avoid grabbing
            # random hex from JSON dumps.
            continue
        # Dedup shas within a comment so quoting twice (narrative + backtick
        # block) only triggers one subprocess check.
        for sha in {match.group(1) for match in SHA_PATTERN.finditer(body)}:
            if subprocess_has_commit(sha, swi_id):
                return sha
    return None


def evaluate_issue(
    issue: dict[str, object],
    *,
    now: datetime,
    comments: list[dict[str, object]],
) -> ReconcileAction | None:
    """Apply the four rules to a single issue snapshot. Returns the proposed
    action or None when no rule fires."""
    swi_id = cast(str, issue.get("identifier") or "")
    state_obj = cast(dict[str, object], issue.get("state") or {})
    state_name = cast(str, state_obj.get("name") or "")
    label_nodes = cast(
        list[dict[str, object]],
        cast(dict[str, object], issue.get("labels") or {}).get("nodes") or [],
    )
    label_names = {cast(str, n["name"]) for n in label_nodes if n.get("name")}
    last_activity = _last_activity(issue, comments)
    silent_for = now - last_activity

    if state_name == "In Progress" and silent_for >= timedelta(days=IN_PROGRESS_SILENCE_DAYS):
        if _git_commit_in_subjects_since(swi_id, now - timedelta(days=IN_PROGRESS_SILENCE_DAYS)):
            return None
        category = _category_label(label_names)
        target = "Monitoring" if category == "regression-watch" else "Triage"
        body = (
            f"{RECONCILER_PREFIX} in-progress-silent — no commit reference in "
            f"{IN_PROGRESS_SILENCE_DAYS} days, returning to {target}."
        )
        return ReconcileAction(swi_id, "in_progress_silent", target, body)

    if state_name == "Confirm Regression" and silent_for >= timedelta(
        days=CONFIRM_REGRESSION_SILENCE_DAYS
    ):
        body = (
            f"{RECONCILER_PREFIX} confirm-regression-silent — unresolved for "
            f"{CONFIRM_REGRESSION_SILENCE_DAYS} days, escalating."
        )
        return ReconcileAction(swi_id, "confirm_regression_silent", "Escalated", body)

    if state_name == "Triage" and silent_for >= timedelta(days=TRIAGE_PING_DAYS):
        body = (
            f"{RECONCILER_PREFIX} triage-ping — Triage is a holding pattern; "
            "this SWI has been here for "
            f"{silent_for.days} days. Move to its destination state."
        )
        return ReconcileAction(swi_id, "triage_ping", None, body)

    if state_name == "Resolved Candidate" and silent_for >= timedelta(
        days=RESOLVED_CANDIDATE_SILENCE_DAYS
    ):
        sha = _closing_commit_in_comments(swi_id, comments)
        if sha:
            body = (
                f"{RECONCILER_PREFIX} resolved-candidate-close — silent for "
                f"{silent_for.days} days, closing commit `{sha[:12]}` "
                f"verified in git log --grep={swi_id}."
            )
            return ReconcileAction(swi_id, "resolved_candidate_close", "Resolved", body)
        return None

    return None
