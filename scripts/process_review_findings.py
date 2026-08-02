"""Post-subagent Linear write-back: parse fenced findings JSON -> Linear MCP.

Called by the ``/pipeline-review`` and ``/audit`` orchestrators at the end of
a run. Reads the full report text from stdin (or ``--report``), extracts the
final fenced JSON block, validates it against the Pydantic contract, and
applies the four tag actions against Linear:

    regressions[]         Resolved -> Confirm Regression, comment
    new[]                 create issue (category + severity + priority + description)
    bumps[]               append "Reproduced on <date>: ..." comment
    resolved_candidates[] cautious lane bumps counter; auto-promote lane closes
                          (4-invariant gate in scripts/linear_migration/auto_promote.py)

Idempotent via a content-hash sentinel at
``scripts/linear_migration/processed_reports/<report_id>.json``. Re-running
the same report is a no-op unless ``--force`` is passed.

On validation failure the raw report posts as a comment on the Linear issue
named in ``--parse-failure-issue``, so findings survive even when the
contract breaks. No such issue -> the report is written to
``scripts/linear_migration/processed_reports/parse_failures/<report_id>.md``.

Env:
    LINEAR_API_KEY — personal API key for the Swingy workspace.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.linear_migration import dedup  # noqa: E402
from scripts.linear_migration.auto_promote import (  # noqa: E402
    apply_resolved_candidate,
    parse_iso_datetime,
)
from scripts.linear_migration.client import (  # noqa: E402
    GraphqlError,
    LinearClient,
    require_api_key,
    state_ids_by_name,
)
from scripts.linear_migration.findings_schema import (  # noqa: E402
    FindingsBlock,
    extract_findings_block,
)
from scripts.linear_migration.tag_actions import (  # noqa: E402
    TEAM_ID,
    apply_bump,
    apply_new_finding,
    apply_regression,
    load_id_map,
    post_comment,
)

PARSE_FAILURE_DIR = (
    Path(__file__).resolve().parent / "linear_migration" / "processed_reports" / "parse_failures"
)


def handle_parse_failure(
    client: LinearClient, report_text: str, report_id: str, fallback_issue: str | None
) -> int:
    """Loud-fail when no fenced JSON parses out of the report.

    Post-`linear`-skill cutover, the orchestrator must surface a parse
    failure. Silently swallowing it loses the regression-watch tag actions and
    masks the underlying defect — the subagent prompt drifted from the
    Pydantic contract, the model went off-format, or the skill never loaded.
    """
    if fallback_issue:
        try:
            post_comment(
                client,
                fallback_issue,
                f"Parse failure for report {report_id}:\n\n```\n{report_text}\n```",
            )
            print(
                f"Parse-failure raw report posted to {fallback_issue} "
                f"(report_id={report_id}) — non-zero exit so the orchestrator "
                "surfaces it.",
                file=sys.stderr,
            )
            return 3
        except GraphqlError as exc:
            print(f"Parse-failure fallback comment failed: {exc}", file=sys.stderr)
    PARSE_FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    path = PARSE_FAILURE_DIR / f"{report_id}.md"
    path.write_text(report_text)
    print(
        f"FATAL [LinearSkillNotLoaded? findings JSON not parseable]: raw report "
        f"saved to {path}. Confirm the subagent prompt embeds the fenced-JSON "
        "contract from the `linear` skill and that the report ends with a "
        "fenced ```json block.",
        file=sys.stderr,
    )
    return 3


def process(
    report_text: str,
    *,
    source_kind: str,
    force: bool,
    parse_failure_issue: str | None,
    run_scope: set[str] | None = None,
    bundle_collected_at: datetime | None = None,
) -> int:
    report_id = dedup.compute_report_id(report_text)
    if dedup.is_already_processed(report_id) and not force:
        print(f"ALREADY PROCESSED — rerun with --force (report_id={report_id})")
        return 0

    payload = extract_findings_block(report_text)
    api_key = require_api_key()
    with LinearClient(api_key) as client:
        if payload is None:
            return handle_parse_failure(client, report_text, report_id, parse_failure_issue)
        try:
            block = FindingsBlock.model_validate_json(payload)
        except Exception as exc:  # noqa: BLE001 — fall back on any validation error
            print(f"Validation failure: {exc}", file=sys.stderr)
            return handle_parse_failure(client, report_text, report_id, parse_failure_issue)

        legacy_to_linear = load_id_map()
        state_ids = state_ids_by_name(client, TEAM_ID)
        touched: list[str] = []
        created: list[str] = []

        for regression in block.regressions:
            touched.append(apply_regression(client, regression, legacy_to_linear, state_ids))
        for bump in block.bumps:
            touched.append(apply_bump(client, bump, legacy_to_linear))
        for candidate in block.resolved_candidates:
            touched.append(
                apply_resolved_candidate(
                    client,
                    candidate,
                    legacy_to_linear,
                    state_ids,
                    run_scope=run_scope,
                    bundle_collected_at=bundle_collected_at,
                )
            )
        for finding in block.new:
            created.append(apply_new_finding(client, finding, source_kind))

    dedup.record_sentinel(
        report_id,
        source_kind=source_kind,
        touched_linear_ids=sorted(set(touched)),
        created_linear_ids=sorted(set(created)),
        note=(
            f"regressions={len(block.regressions)} new={len(block.new)} "
            f"bumps={len(block.bumps)} resolved={len(block.resolved_candidates)}"
        ),
    )
    print(
        f"Processed report_id={report_id}: {len(block.regressions)} regressions, "
        f"{len(block.new)} new, {len(block.bumps)} bumps, "
        f"{len(block.resolved_candidates)} resolved_candidates"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        help="Path to the subagent report text (default: read from stdin).",
    )
    parser.add_argument(
        "--source-kind",
        choices=["pipeline-review", "audit"],
        required=True,
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-process even when sentinel exists."
    )
    parser.add_argument(
        "--parse-failure-issue",
        default=None,
        help="Linear issue id/identifier for parse-failure fallback comments.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        choices=["morning", "midday", "retro", "all"],
        default=None,
        help=(
            "Pipeline scope(s) of the source run. Required for auto-promote of "
            "resolved_candidates with clean_runs>=3 — without it the auto-promote "
            "lane fail-closes to Resolved Candidate. Repeatable."
        ),
    )
    parser.add_argument(
        "--bundle-collected-at",
        type=parse_iso_datetime,
        default=None,
        help=(
            "ISO timestamp of the review bundle's collection. Required for "
            "auto-promote — used by the freshness invariant to reject SWIs "
            "updated AFTER the bundle was collected (likely by a later run)."
        ),
    )
    args = parser.parse_args()

    report_text = args.report.read_text() if args.report else sys.stdin.read()
    if not report_text.strip():
        print("FATAL: empty report text", file=sys.stderr)
        return 2

    run_scope: set[str] | None = set(args.scope) if args.scope else None

    return process(
        report_text,
        source_kind=args.source_kind,
        force=args.force,
        parse_failure_issue=args.parse_failure_issue,
        run_scope=run_scope,
        bundle_collected_at=args.bundle_collected_at,
    )


if __name__ == "__main__":
    raise SystemExit(main())
