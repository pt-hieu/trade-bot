"""Linear tag-action helpers — the four GraphQL primitives the orchestrator
applies for every ``regressions[]`` / ``bumps[]`` / ``new[]`` /
``resolved_candidates[]`` entry.

Lifted out of ``scripts/process_review_findings.py`` so the orchestrator
stays under the 350-line cap while keeping each writer in one place. The
auto-promote lane lives in ``auto_promote.py`` and is plumbed via callable
injection so all GraphQL surface stays here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from scripts.linear_migration.client import GraphqlError, LinearClient, load_labels_json
from scripts.linear_migration.findings_schema import (
    BumpEntry,
    NewFindingEntry,
    RegressionEntry,
)

MIGRATION_DIR = Path(__file__).resolve().parent
ID_MAP_PATH = MIGRATION_DIR / "id_map.json"

_LABEL_MAP_RAW = load_labels_json()
TEAM_ID: str = cast(dict[str, str], _LABEL_MAP_RAW["team"])["id"]
CATEGORY_LABEL_IDS: dict[str, str] = cast(dict[str, str], _LABEL_MAP_RAW["category"])
SEVERITY_LABEL_IDS: dict[str, str] = cast(dict[str, str], _LABEL_MAP_RAW["severity"])
SOURCE_LABEL_IDS: dict[str, str] = cast(dict[str, str], _LABEL_MAP_RAW["source"])
AREA_LABEL_IDS: dict[str, str] = cast(dict[str, str], _LABEL_MAP_RAW["area"])
PIPELINE_LABEL_IDS: dict[str, str] = cast(dict[str, str], _LABEL_MAP_RAW["pipeline"])
DIMENSION_LABEL_IDS: dict[str, str] = cast(dict[str, str], _LABEL_MAP_RAW["dimension"])

PRIORITY_TO_INT: dict[str, int] = {"P0": 1, "P1": 2, "P2": 3, "P3": 4}


def load_id_map() -> dict[str, str]:
    """Return legacy_id -> Linear id lookup. Empty when no map exists yet."""
    if not ID_MAP_PATH.exists():
        return {}
    raw = json.loads(ID_MAP_PATH.read_text())
    return cast(dict[str, str], raw.get("legacy_to_linear") or {})


def resolve_linear_id(client: LinearClient, ref: str, legacy_to_linear: dict[str, str]) -> str:
    """Accept either a Linear identifier (``SWY-42``) or a legacy id (``MON-...``)."""
    if ref in legacy_to_linear:
        return legacy_to_linear[ref]
    data = client.query(
        "query($id: String!) { issue(id: $id) { id } }",
        {"id": ref},
    )
    issue = cast(dict[str, object], data.get("issue") or {})
    linear_id = cast(str | None, issue.get("id"))
    if not linear_id:
        raise GraphqlError(f"cannot resolve Linear id for reference: {ref}")
    return linear_id


def set_state(client: LinearClient, linear_id: str, state_id: str) -> None:
    client.query(
        """
        mutation($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: { stateId: $stateId }) { success }
        }
        """,
        {"id": linear_id, "stateId": state_id},
    )


def post_comment(client: LinearClient, linear_id: str, body: str) -> None:
    client.query(
        "mutation($id: String!, $body: String!) { commentCreate(input: { issueId: $id, body: $body }) { success } }",
        {"id": linear_id, "body": body},
    )


def apply_regression(
    client: LinearClient,
    entry: RegressionEntry,
    legacy_to_linear: dict[str, str],
    state_ids: dict[str, str],
) -> str:
    linear_id = resolve_linear_id(client, entry.linear_id, legacy_to_linear)
    set_state(client, linear_id, state_ids["Confirm Regression"])
    post_comment(
        client,
        linear_id,
        f"REGRESSION observed on {entry.new_last_seen_date}:\n\n{entry.evidence}",
    )
    return linear_id


def apply_bump(client: LinearClient, entry: BumpEntry, legacy_to_linear: dict[str, str]) -> str:
    linear_id = resolve_linear_id(client, entry.linear_id, legacy_to_linear)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    post_comment(client, linear_id, f"Reproduced on {today}: {entry.reproduction_note}")
    return linear_id


def labels_for_new(entry: NewFindingEntry, source_kind: str) -> list[str]:
    ids: list[str] = [
        CATEGORY_LABEL_IDS[entry.category.value],
        SEVERITY_LABEL_IDS[entry.severity.value],
        SOURCE_LABEL_IDS[source_kind],
    ]
    if entry.dimension is not None:
        ids.append(DIMENSION_LABEL_IDS[entry.dimension.value])
    if entry.area is not None and entry.area in AREA_LABEL_IDS:
        ids.append(AREA_LABEL_IDS[entry.area])
    for pipeline in entry.pipelines or []:
        if pipeline in PIPELINE_LABEL_IDS:
            ids.append(PIPELINE_LABEL_IDS[pipeline])
    return sorted(set(ids))


def apply_new_finding(client: LinearClient, entry: NewFindingEntry, source_kind: str) -> str:
    variables: dict[str, object] = {
        "teamId": TEAM_ID,
        "title": entry.title,
        "description": entry.evidence,
        "labelIds": labels_for_new(entry, source_kind),
    }
    if entry.priority is not None:
        variables["priority"] = PRIORITY_TO_INT[entry.priority]
    data = client.query(
        """
        mutation($teamId: String!, $title: String!, $description: String!,
                 $labelIds: [String!], $priority: Int) {
          issueCreate(input: {
            teamId: $teamId, title: $title, description: $description,
            labelIds: $labelIds, priority: $priority
          }) { success issue { id } }
        }
        """,
        variables,
    )
    result = cast(dict[str, object], data.get("issueCreate") or {})
    issue = cast(dict[str, object], result.get("issue") or {})
    linear_id = cast(str | None, issue.get("id"))
    if not linear_id:
        raise GraphqlError(f"issueCreate failed for new finding: {result}")
    return linear_id
