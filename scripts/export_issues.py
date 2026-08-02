"""Pre-review export: Linear -> monitoring_items.md + resolved_items.md.

Replaces the legacy ``render_issues.py --view subagent-monitoring`` path at
the ``/pipeline-review`` and ``/audit`` seams. Runs only at skill startup —
the trading pipeline never reads Linear, so outages degrade human review
only.

Outputs (under ``--out <dir>``):
    - monitoring_items.md — OPEN+ESCALATED, category=regression-watch
    - resolved_items.md — Done ≤90 days, category=regression-watch
      (regression cross-check reference for subagents)

Fail-open:
    1. Live Linear fetch succeeds -> write outputs + refresh
       ``linear_migration/last_export.md`` as the stale-cache backup.
    2. Live fetch fails -> serve ``last_export.md`` with a WARNING banner
       prepended. Exit 0 so the skill still runs with degraded context.
    3. Cache missing, or cache older than 7 days while
       ``SWINGY_ENV=production`` -> exit non-zero (human review aborts).

Env:
    LINEAR_API_KEY — personal API key for the Swingy workspace.
    SWINGY_ENV — "production" tightens the fail-open gate.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.linear_migration.client import (  # noqa: E402
    GraphqlError,
    LinearClient,
    load_labels_json,
    require_api_key,
)
from scripts.linear_migration.export_render import (  # noqa: E402
    RenderedIssue,
    render_monitoring_items,
    render_resolved_items,
)

MIGRATION_DIR = Path(__file__).resolve().parent / "linear_migration"
STALE_CACHE_PATH = MIGRATION_DIR / "last_export.md"
STALE_CACHE_TTL_DAYS = 7
RESOLVED_WINDOW_DAYS = 90

_LABEL_MAP_RAW = load_labels_json()
TEAM_ID: str = cast(dict[str, str], _LABEL_MAP_RAW["team"])["id"]
REGRESSION_WATCH_LABEL_ID: str = cast(dict[str, str], _LABEL_MAP_RAW["category"])[
    "regression-watch"
]


@dataclass(frozen=True)
class LinearIssue:
    linear_id: str
    identifier: str
    title: str
    description: str
    state_type: str
    state_name: str
    labels: list[str]
    updated_at: str
    completed_at: str | None


def fetch_issues(client: LinearClient, state_names: list[str]) -> list[LinearIssue]:
    """Fetch Swingy team issues with ``category:regression-watch`` label.

    State filter is by explicit state name (post-SWI-159 custom states).
    Active regression-watch states: ``Monitoring``, ``Escalated``,
    ``Confirm Regression``, ``Resolved Candidate``, ``In Progress``.
    Resolved cross-check state: ``Resolved``.
    """
    issues: list[LinearIssue] = []
    cursor: str | None = None
    while True:
        data = client.query(
            """
            query($teamId: ID!, $labelId: ID!, $stateNames: [String!],
                  $after: String) {
              issues(
                first: 50, after: $after,
                filter: {
                  team: { id: { eq: $teamId } },
                  labels: { id: { eq: $labelId } },
                  state: { name: { in: $stateNames } }
                }
              ) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  id identifier title description updatedAt completedAt
                  state { name type }
                  labels { nodes { name } }
                }
              }
            }
            """,
            {
                "teamId": TEAM_ID,
                "labelId": REGRESSION_WATCH_LABEL_ID,
                "stateNames": state_names,
                "after": cursor,
            },
        )
        node_page = cast(dict[str, object], data.get("issues") or {})
        for raw in cast(list[dict[str, object]], node_page.get("nodes") or []):
            state = cast(dict[str, str], raw.get("state") or {})
            label_nodes = cast(
                list[dict[str, object]],
                cast(dict[str, object], raw.get("labels") or {}).get("nodes") or [],
            )
            issues.append(
                LinearIssue(
                    linear_id=cast(str, raw.get("id") or ""),
                    identifier=cast(str, raw.get("identifier") or ""),
                    title=cast(str, raw.get("title") or ""),
                    description=cast(str, raw.get("description") or ""),
                    state_type=state.get("type") or "",
                    state_name=state.get("name") or "",
                    labels=sorted(cast(str, node.get("name") or "") for node in label_nodes),
                    updated_at=cast(str, raw.get("updatedAt") or ""),
                    completed_at=cast(str | None, raw.get("completedAt")),
                )
            )
        page = cast(dict[str, object], node_page.get("pageInfo") or {})
        if not page.get("hasNextPage"):
            break
        cursor = cast(str | None, page.get("endCursor"))
    return issues


def _as_rendered(issue: LinearIssue) -> RenderedIssue:
    return RenderedIssue(
        linear_identifier=issue.identifier,
        title=issue.title,
        description=issue.description,
        state_name=issue.state_name,
        labels=tuple(issue.labels),
        updated_at=issue.updated_at,
        completed_at=issue.completed_at,
    )


def filter_recent_resolved(resolved: list[LinearIssue]) -> list[LinearIssue]:
    cutoff = datetime.now(UTC) - timedelta(days=RESOLVED_WINDOW_DAYS)
    kept: list[LinearIssue] = []
    for issue in resolved:
        stamp = issue.completed_at or issue.updated_at
        if not stamp:
            continue
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when >= cutoff:
            kept.append(issue)
    return kept


def write_outputs(out_dir: Path, monitoring_md: str, resolved_md: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "monitoring_items.md").write_text(monitoring_md)
    (out_dir / "resolved_items.md").write_text(resolved_md)
    cache_body = "\n\n".join(
        [
            "<!-- last_export.md — most recent successful Linear export -->",
            f"<!-- Generated: {datetime.now(UTC).isoformat()} -->",
            "# === monitoring_items.md ===",
            monitoring_md,
            "# === resolved_items.md ===",
            resolved_md,
        ]
    )
    STALE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STALE_CACHE_PATH.write_text(cache_body)


def stale_cache_age_days() -> float | None:
    if not STALE_CACHE_PATH.exists():
        return None
    mtime = datetime.fromtimestamp(STALE_CACHE_PATH.stat().st_mtime, tz=UTC)
    delta = datetime.now(UTC) - mtime
    return delta.total_seconds() / 86400.0


def serve_stale_cache(out_dir: Path, error: str) -> int:
    """Split last_export.md back into the two outputs, prepending a warning banner."""
    age = stale_cache_age_days()
    if age is None:
        print(
            f"FATAL: no stale cache at {STALE_CACHE_PATH}; live fetch failed: {error}",
            file=sys.stderr,
        )
        return 2
    if age > STALE_CACHE_TTL_DAYS and os.environ.get("SWINGY_ENV") == "production":
        print(
            f"FATAL: cache is {age:.1f}d stale (>{STALE_CACHE_TTL_DAYS}d) and SWINGY_ENV=production; live fetch failed: {error}",
            file=sys.stderr,
        )
        return 2
    raw = STALE_CACHE_PATH.read_text()
    monitoring_md, _, resolved_md = raw.partition("# === resolved_items.md ===")
    monitoring_md = monitoring_md.split("# === monitoring_items.md ===", 1)[-1]
    banner = f"> **WARNING: Linear unreachable; regression cross-check degraded. Cache age {age:.1f}d. Reason: {error}**\n\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "monitoring_items.md").write_text(banner + monitoring_md.lstrip())
    (out_dir / "resolved_items.md").write_text(banner + resolved_md.lstrip())
    print(f"WARNING: served stale cache (age {age:.1f}d); reason: {error}", file=sys.stderr)
    return 0


@dataclass(frozen=True)
class ExportResult:
    open_items: int
    escalated_items: int
    resolved_items: int
    served_stale_cache: bool
    stale_cache_reason: str | None


def run_export(out_dir: Path) -> ExportResult:
    """Fetch Linear and write monitoring_items.md + resolved_items.md.

    Falls back to the stale cache with a warning banner when the live fetch
    fails. Raises only when the cache is missing or expired under
    ``SWINGY_ENV=production`` (see ``serve_stale_cache``). Returns counts
    derived from the fetched (or served) content.
    """
    try:
        api_key = require_api_key()
        with LinearClient(api_key) as client:
            active = fetch_issues(
                client,
                [
                    "Monitoring",
                    "Escalated",
                    "Confirm Regression",
                    "Resolved Candidate",
                    "In Progress",
                ],
            )
            resolved_all = fetch_issues(client, ["Resolved"])
        resolved_recent = filter_recent_resolved(resolved_all)
        active_rendered = [_as_rendered(item) for item in active]
        resolved_rendered = [_as_rendered(item) for item in resolved_recent]
        monitoring_md = render_monitoring_items(active_rendered)
        resolved_md = render_resolved_items(resolved_rendered, RESOLVED_WINDOW_DAYS)
        write_outputs(out_dir, monitoring_md, resolved_md)
        open_count = sum(1 for item in active if item.state_name == "Monitoring")
        escalated_count = sum(
            1
            for item in active
            if item.state_name
            in {"Escalated", "Confirm Regression", "Resolved Candidate", "In Progress"}
        )
        return ExportResult(
            open_items=open_count,
            escalated_items=escalated_count,
            resolved_items=len(resolved_recent),
            served_stale_cache=False,
            stale_cache_reason=None,
        )
    except GraphqlError as exc:
        return _stale_fallback(out_dir, str(exc))
    except Exception as exc:  # noqa: BLE001 — fail-open on any fetch error
        return _stale_fallback(out_dir, f"{type(exc).__name__}: {exc}")


def _stale_fallback(out_dir: Path, reason: str) -> ExportResult:
    exit_code = serve_stale_cache(out_dir, reason)
    if exit_code != 0:
        raise GraphqlError(f"stale cache unavailable; live fetch failed: {reason}")
    return ExportResult(
        open_items=0,
        escalated_items=0,
        resolved_items=0,
        served_stale_cache=True,
        stale_cache_reason=reason,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = Path(f"/tmp/swingy-review-{datetime.now(UTC).strftime('%Y-%m-%d')}")
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args()
    try:
        result = run_export(args.out)
    except GraphqlError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    if result.served_stale_cache:
        print(f"WARNING: served stale cache to {args.out}", file=sys.stderr)
    else:
        active_total = result.open_items + result.escalated_items
        print(f"Exported {active_total} active + {result.resolved_items} resolved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
