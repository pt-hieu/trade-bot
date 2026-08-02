"""Time-axis reconciler for the Linear team Swingy.

Daily GitHub Action walks every active issue and applies deterministic
transitions on the *time axis* — the sibling-class fix for state transitions
the post-commit hook and the auto-promote contract don't directly cover.

Rules (each evaluated independently, all fail-closed on missing data):

    1. ``In Progress`` SWIs with no commit reference in the last 14 days
       return to ``Monitoring`` (regression-watch) or ``Triage`` (other
       categories). Re-run begins their normal lifecycle.

    2. ``Confirm Regression`` SWIs with no comment activity in 14 days
       escalate to ``Escalated`` so a human reviewer is forced to look.

    3. ``Triage`` SWIs untouched for 7 days get a comment ping. No state
       change — Triage is a holding pattern by design.

    4. ``Resolved Candidate`` SWIs with no `bumps[]` or comment activity in
       14 days flip to ``Resolved`` ONLY when a closing-commit sha is named
       in any prior comment. Otherwise the cautious lane stays parked.

Idempotent within a calendar UTC day via a sentinel file at
``scripts/linear_migration/processed_reports/reconciler_<YYYY-MM-DD>.json``.
Re-running the same day is a no-op unless ``--force`` is passed.

Pure rule logic lives in ``scripts/linear_migration/reconciler_rules.py``;
this module owns the GraphQL fan-out + sentinel + CLI.

Env:
    LINEAR_API_KEY — personal API key for the Swingy workspace.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.linear_migration.client import (  # noqa: E402
    GraphqlError,
    LinearClient,
    load_team_id,
    require_api_key,
    state_ids_by_name,
)
from scripts.linear_migration.reconciler_rules import (  # noqa: E402
    RECONCILER_PREFIX,
    ReconcileAction,
    evaluate_issue,
    subprocess_has_commit,
)

SENTINEL_DIR = _REPO_ROOT / "scripts" / "linear_migration" / "processed_reports"

# Re-export so tests can monkeypatch the same names they always have.
__all__ = [
    "RECONCILER_PREFIX",
    "ReconcileAction",
    "ReconcileSummary",
    "already_ran",
    "evaluate_issue",
    "fetch_active_issues",
    "issue_comments",
    "execute_action",
    "reconcile",
    "sentinel_path",
    "subprocess_has_commit",
    "write_sentinel",
]


@dataclass
class ReconcileSummary:
    run_date: str
    actions: list[ReconcileAction] = field(default_factory=list)
    rule_counts: dict[str, int] = field(default_factory=dict)


def fetch_active_issues(client: LinearClient, team_id: str) -> list[dict[str, object]]:
    """Pull every backlog/unstarted/started issue for the Swingy team WITH
    its comments inlined. Comments page is capped at 100 per issue (the
    rule layer only needs the most recent activity timestamp + a sha
    backscan; SWIs with >100 comments are vanishingly rare and the rules
    fail-closed when truncation happens). Excludes ``Resolved`` (no-op for
    the reconciler) and ``Superseded`` (terminal).
    """
    nodes: list[dict[str, object]] = []
    cursor: str | None = None
    while True:
        data = client.query(
            """
            query($teamId: ID!, $cursor: String) {
              issues(
                first: 50,
                after: $cursor,
                filter: {
                  team: { id: { eq: $teamId } },
                  state: { type: { in: ["backlog", "unstarted", "started"] } }
                }
              ) {
                nodes {
                  id identifier title updatedAt
                  state { name }
                  labels { nodes { name } }
                  comments(first: 100) { nodes { id body createdAt } }
                }
                pageInfo { endCursor hasNextPage }
              }
            }
            """,
            {"teamId": team_id, "cursor": cursor},
        )
        issues = cast(dict[str, object], data.get("issues") or {})
        nodes.extend(cast(list[dict[str, object]], issues.get("nodes") or []))
        page = cast(dict[str, object], issues.get("pageInfo") or {})
        if not page.get("hasNextPage"):
            break
        cursor = cast(str | None, page.get("endCursor"))
        if not cursor:
            break
    return nodes


def issue_comments(issue: dict[str, object]) -> list[dict[str, object]]:
    """Pull the inlined comment list off an issue snapshot."""
    comments_obj = cast(dict[str, object], issue.get("comments") or {})
    return cast(list[dict[str, object]], comments_obj.get("nodes") or [])


def execute_action(
    client: LinearClient,
    action: ReconcileAction,
    state_ids: dict[str, str],
    issue_uuid: str,
) -> None:
    """Apply the proposed transition + comment to Linear."""
    if action.new_state:
        target_id = state_ids.get(action.new_state)
        if not target_id:
            raise GraphqlError(f"reconciler cannot find state '{action.new_state}' in team states")
        client.query(
            """
            mutation($id: String!, $stateId: String!) {
              issueUpdate(id: $id, input: { stateId: $stateId }) { success }
            }
            """,
            {"id": issue_uuid, "stateId": target_id},
        )
    client.query(
        """
        mutation($id: String!, $body: String!) {
          commentCreate(input: { issueId: $id, body: $body }) { success }
        }
        """,
        {"id": issue_uuid, "body": action.comment_body},
    )


def sentinel_path(run_date: date) -> Path:
    return SENTINEL_DIR / f"reconciler_{run_date.isoformat()}.json"


def already_ran(run_date: date) -> bool:
    return sentinel_path(run_date).exists()


def write_sentinel(summary: ReconcileSummary) -> Path:
    SENTINEL_DIR.mkdir(parents=True, exist_ok=True)
    path = sentinel_path(date.fromisoformat(summary.run_date))
    payload = {
        "run_date": summary.run_date,
        "rule_counts": summary.rule_counts,
        "actions": [asdict(a) for a in summary.actions],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def reconcile(*, dry_run: bool, force: bool) -> ReconcileSummary:
    """Walk every active issue, evaluate the rules, execute non-dry actions."""
    now = datetime.now(UTC)
    run_date = now.date()
    summary = ReconcileSummary(run_date=run_date.isoformat())

    if already_ran(run_date) and not force:
        print(f"reconciler already ran on {run_date}; pass --force to re-run.")
        return summary

    api_key = require_api_key()
    team_id = load_team_id()

    with LinearClient(api_key) as client:
        state_ids = state_ids_by_name(client, team_id)
        issues = fetch_active_issues(client, team_id)
        for issue in issues:
            comments = issue_comments(issue)
            action = evaluate_issue(issue, now=now, comments=comments)
            if action is None:
                continue
            summary.actions.append(action)
            summary.rule_counts[action.rule] = summary.rule_counts.get(action.rule, 0) + 1
            if dry_run:
                continue
            execute_action(client, action, state_ids, cast(str, issue.get("id") or ""))
            action.executed = True

    if not dry_run:
        write_sentinel(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate rules and print proposed actions without writing to Linear.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even when today's sentinel exists.",
    )
    args = parser.parse_args()

    summary = reconcile(dry_run=args.dry_run, force=args.force)
    print(
        f"reconciler {summary.run_date} — {len(summary.actions)} actions; "
        f"by rule: {summary.rule_counts or '{}'}"
    )
    for action in summary.actions:
        flag = "[would]" if args.dry_run else ("[done]" if action.executed else "[skip]")
        target = action.new_state or "comment-only"
        print(f"  {flag} {action.swi_id} {action.rule} → {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
