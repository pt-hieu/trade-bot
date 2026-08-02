"""Markdown renderers for the pre-review Linear export.

Pulled out of ``scripts/export_issues.py`` so that file can stay under the
350-LOC cap. Renderers are pure functions over ``LinearIssue`` (defined in
``export_issues`` to keep the import graph one-way: renderers don't need
the fetcher, and the fetcher imports these renderers).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from scripts.linear_migration.findings_schema import (
    FindingCategory,
    FindingSeverity,
)

SHORT_TAG_PATTERN = re.compile(r"^\[(?P<tag>[A-Z]+)\]\s*")
LEGACY_ID_IN_DESCRIPTION = re.compile(
    r"\*\*Legacy ID:\*\*\s*`?(?P<legacy>[A-Z]+-\d{4}-\d{2}-\d{2}-\d{3}(?:-[\w-]+)?)`?"
)
EVIDENCE_HEADING = re.compile(r"^##\s+Evidence\s*$", re.MULTILINE)
NEXT_HEADING = re.compile(r"^##\s+\S", re.MULTILINE)
FINGERPRINT_MAX_CHARS = 320

# Source of truth: scripts/linear_migration/findings_schema.py enums.
# Kept as frozensets (one-line derive) so the renderers stay drift-safe —
# adding `feature`/`decision` here used to require editing two places.
CATEGORY_LABELS = frozenset(c.value for c in FindingCategory)
SEVERITY_LABELS = frozenset(s.value for s in FindingSeverity)


@dataclass(frozen=True)
class RenderedIssue:
    """Minimal shape the renderers need — decoupled from the fetcher DTO."""

    linear_identifier: str
    title: str
    description: str
    state_name: str
    labels: tuple[str, ...]
    updated_at: str
    completed_at: str | None


def split_title_tag(title: str) -> tuple[str, str]:
    """Return (category_tag, title_body). Missing tag yields ('', title)."""
    match = SHORT_TAG_PATTERN.match(title)
    if match is None:
        return ("", title)
    return (match.group("tag"), title[match.end() :])


def extract_legacy_id(description: str) -> str:
    """Return the legacy id embedded in the description, or '' when absent."""
    match = LEGACY_ID_IN_DESCRIPTION.search(description)
    return match.group("legacy") if match else ""


def extract_evidence_fingerprint(description: str) -> str:
    """Pull the body under ``## Evidence`` (or leading text) capped at ~320 chars."""
    if match := EVIDENCE_HEADING.search(description):
        start = match.end()
        next_match = NEXT_HEADING.search(description, pos=start)
        body = description[start : next_match.start() if next_match else None]
    else:
        body = description
    compact = " ".join(body.split())
    return compact[:FINGERPRINT_MAX_CHARS]


def _header_id(issue: RenderedIssue) -> str:
    """Return 'SWI-NN (LEGACY-ID)' when legacy id parses, else 'SWI-NN'."""
    legacy = extract_legacy_id(issue.description)
    return f"{issue.linear_identifier} ({legacy})" if legacy else issue.linear_identifier


def render_monitoring_items(active: list[RenderedIssue]) -> str:
    """Flat markdown subagents consume as KNOWN ACTIVE ISSUES injection block."""
    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%MZ")
    lines = [
        "# Pipeline Review — Monitoring Items",
        "",
        f"Source: Linear team Swingy, category=regression-watch, state=Monitoring+Escalated+Confirm Regression+Resolved Candidate+In Progress. Generated {now_iso}.",
        "",
        "---",
        "",
        "## Active items",
        "",
    ]
    for issue in sorted(active, key=lambda i: i.updated_at, reverse=True):
        _, body = split_title_tag(issue.title)
        lines.append(f"## {_header_id(issue)} — {body}")
        lines.append(f"- **Status:** {issue.state_name}")
        lines.append(f"- **Labels:** {', '.join(issue.labels) or '_(none)_'}")
        lines.append(f"- **Last updated:** {issue.updated_at}")
        lines.append("")
        lines.append(issue.description.strip())
        lines.append("")
    return "\n".join(lines) + "\n"


def render_resolved_items(resolved: list[RenderedIssue], window_days: int) -> str:
    """Compact fingerprint list subagents use for the regression cross-check."""
    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%MZ")
    lines = [
        "# Resolved Issues — Regression Cross-Check Reference",
        "",
        f"Source: Linear team Swingy, category=regression-watch, state=Resolved ≤{window_days} days. Generated {now_iso}.",
        "",
        "Match new findings against these by evidence (file paths, error patterns, trace-span names, span ids, or quoted data). When a match exists, record under `regressions[]`.",
        "",
    ]
    for issue in sorted(resolved, key=lambda i: i.completed_at or i.updated_at, reverse=True):
        _, body = split_title_tag(issue.title)
        lines.append(f"## {_header_id(issue)} — {body}")
        lines.append(f"- **Resolved at:** {issue.completed_at or issue.updated_at}")
        lines.append(
            f"- **Evidence fingerprint:** {extract_evidence_fingerprint(issue.description)}"
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def render_active_issues_overview(active_all: list[RenderedIssue]) -> str:
    """Compact table used by the pipeline-review Step 2a / audit Step 1a sweeps.

    Lists every OPEN/ESCALATED issue across categories (MON/DEF/AUDIT/ISSUE)
    so the orchestrator can match incoming findings against queued work
    without opening each Linear ticket.
    """
    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%MZ")
    lines = [
        "# Active Issues Overview — Cross-Check Reference",
        "",
        f"Source: Linear team Swingy, state=Triage+Monitoring+Deferred+Escalated+Resolved Candidate+Confirm Regression+In Progress, all categories. Generated {now_iso}.",
        "",
        "| Linear | Legacy | Category | Severity | Title |",
        "|--------|--------|----------|----------|-------|",
    ]
    for issue in sorted(active_all, key=lambda i: i.updated_at, reverse=True):
        _, body = split_title_tag(issue.title)
        legacy = extract_legacy_id(issue.description) or "—"
        categories = [lbl for lbl in issue.labels if lbl in CATEGORY_LABELS]
        severities = [lbl for lbl in issue.labels if lbl in SEVERITY_LABELS]
        category = categories[0] if categories else "—"
        severity = severities[0] if severities else "—"
        body_short = body[:120] + ("…" if len(body) > 120 else "")
        lines.append(
            f"| {issue.linear_identifier} | {legacy} | {category} | {severity} | {body_short} |"
        )
    return "\n".join(lines) + "\n"
