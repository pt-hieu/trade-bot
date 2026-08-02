"""Auto-promote contract for ``resolved_candidates[]`` entries.

Lifted out of ``scripts/process_review_findings.py`` so the orchestrator file
stays under the 350-line cap. Still owned by the same writer (the
pipeline-review/audit write-back) — this module is a pure-helper layer.

Responsibilities:

- ``IssueMeta`` snapshot (state, labels, updatedAt, identifier).
- ``parse_iso_datetime`` (Z-tolerant) — also used by the orchestrator's
  ``--bundle-collected-at`` argparse type.
- ``fetch_issue_meta`` — single GraphQL roundtrip per SWI being gated.
- ``apply_resolved_candidate`` — cautious lane + 4-invariant auto-promote
  lane. Each invariant fail-closes with an ``AUTO-PROMOTE rejected: ...``
  comment; only the happy path flips state to ``Resolved``. Closing-commit
  verification (Invariant 3) lives in ``git_utils.commit_subject_references``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from scripts.linear_migration.client import LinearClient
from scripts.linear_migration.findings_schema import ResolvedCandidateEntry
from scripts.linear_migration.git_utils import commit_subject_references
from scripts.linear_migration.tag_actions import (
    PIPELINE_LABEL_IDS,
    post_comment,
    resolve_linear_id,
    set_state,
)


@dataclass(frozen=True)
class IssueMeta:
    """Snapshot of fields the auto-promote invariants gate on."""

    state_name: str
    label_names: set[str]
    updated_at: datetime
    identifier: str  # ``SWI-NN`` form, used for ``git log --grep``


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 string. Tolerates trailing ``Z`` and naive datetimes."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def fetch_issue_meta(client: LinearClient, linear_uuid: str) -> IssueMeta:
    """Snapshot state, labels, updatedAt, and identifier for one issue."""
    data = client.query(
        """
        query($id: String!) {
          issue(id: $id) {
            identifier
            updatedAt
            state { name }
            labels { nodes { name } }
          }
        }
        """,
        {"id": linear_uuid},
    )
    issue = cast(dict[str, object], data.get("issue") or {})
    state = cast(dict[str, object], issue.get("state") or {})
    labels_obj = cast(dict[str, object], issue.get("labels") or {})
    label_nodes = cast(list[dict[str, object]], labels_obj.get("nodes") or [])
    return IssueMeta(
        state_name=cast(str, state.get("name") or ""),
        label_names={cast(str, n["name"]) for n in label_nodes if n.get("name")},
        updated_at=parse_iso_datetime(cast(str, issue.get("updatedAt") or "1970-01-01T00:00:00Z")),
        identifier=cast(str, issue.get("identifier") or ""),
    )


def _format_citation_summary(entry: ResolvedCandidateEntry) -> str:
    """Compact comment-friendly view of the citations bundle."""
    return "\n".join(f"- {c.kind}: {c.quote[:100]}" for c in entry.citations)


def apply_resolved_candidate(
    client: LinearClient,
    entry: ResolvedCandidateEntry,
    legacy_to_linear: dict[str, str],
    state_ids: dict[str, str],
    *,
    run_scope: set[str] | None = None,
    bundle_collected_at: datetime | None = None,
) -> str:
    """Cautious lane (``clean_runs < 3``) bumps the counter and parks the SWI
    at ``Resolved Candidate``. Auto-promote lane (``clean_runs >= 3``) fail-
    closes through four invariants — state precedence, scope match, git-log
    commit verification, bundle freshness — only flipping to ``Resolved`` on
    the happy path. Missing ``run_scope`` / ``bundle_collected_at`` (orches-
    trator did not pass the new flags) also fail-closes; auto-promote is
    opt-in by passing both.
    """
    linear_id = resolve_linear_id(client, entry.linear_id, legacy_to_linear)

    if entry.clean_runs < 3:
        set_state(client, linear_id, state_ids["Resolved Candidate"])
        post_comment(
            client,
            linear_id,
            f"Clean-run counter bumped to {entry.clean_runs}; auto-promotes at 3 "
            "with anchored citations + closing commit.",
        )
        return linear_id

    if run_scope is None or bundle_collected_at is None:
        set_state(client, linear_id, state_ids["Resolved Candidate"])
        post_comment(
            client,
            linear_id,
            f"AUTO-PROMOTE rejected: orchestrator did not pass --scope/"
            f"--bundle-collected-at. Counter at {entry.clean_runs}.",
        )
        return linear_id

    issue_meta = fetch_issue_meta(client, linear_id)

    # Invariant 1 — never overwrite a stronger signal.
    if issue_meta.state_name in {"Confirm Regression", "Escalated"}:
        post_comment(
            client,
            linear_id,
            f"AUTO-PROMOTE rejected: state={issue_meta.state_name} outranks clean signal.",
        )
        return linear_id

    # Invariant 2 — scope match: SWI's pipeline labels ∩ run scope must be non-empty
    # (or the SWI carries no pipeline label, or run scope contains "all").
    issue_pipelines = issue_meta.label_names & set(PIPELINE_LABEL_IDS.keys())
    if issue_pipelines and "all" not in run_scope and not (issue_pipelines & run_scope):
        post_comment(
            client,
            linear_id,
            f"AUTO-PROMOTE rejected: SWI watches {sorted(issue_pipelines)}, "
            f"run scope was {sorted(run_scope)}.",
        )
        return linear_id

    # Invariant 3 — closing commit must exist in git AND name the SWI.
    swi_handle = issue_meta.identifier or entry.linear_id
    if not commit_subject_references(entry.closing_commit or "", swi_handle):
        post_comment(
            client,
            linear_id,
            f"AUTO-PROMOTE rejected: commit {entry.closing_commit} not found "
            f"in git log or does not reference {swi_handle}.",
        )
        return linear_id

    # Invariant 4 — bundle freshness: SWI must not have been updated AFTER
    # the bundle's collection time (means a later run already touched it).
    if issue_meta.updated_at > bundle_collected_at:
        post_comment(
            client,
            linear_id,
            f"AUTO-PROMOTE rejected: SWI updated_at="
            f"{issue_meta.updated_at.isoformat()} postdates bundle "
            f"({bundle_collected_at.isoformat()}).",
        )
        return linear_id

    set_state(client, linear_id, state_ids["Resolved"])
    closing_short = (entry.closing_commit or "?")[:12]
    post_comment(
        client,
        linear_id,
        f"AUTO-RESOLVED on {entry.clean_runs} clean runs + closing commit "
        f"`{closing_short}`.\n\nCitations:\n{_format_citation_summary(entry)}",
    )
    return linear_id
