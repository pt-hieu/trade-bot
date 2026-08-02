"""Pydantic contract for the fenced-JSON block that /pipeline-review and
/audit subagents emit at the end of their reports. The orchestrator parses
the block and calls Linear MCP based on the validated content.

Every field that has a finite vocabulary is an Enum; extras are forbidden so
a subagent that drifts the contract fails loud at the top of the write-back
path. On failure, the orchestrator posts the raw report as a Linear comment
on a sentinel issue and surfaces the validation error so no finding is lost.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Legacy id pattern is kept as an alias so the orchestrator can accept either
# a Linear id (e.g. "SWY-123") or a legacy id (e.g. "MON-2026-04-13-002") in
# the weeks after cutover — the write-back resolves both via labels.json and
# title-prefix search.
LINEAR_ID_PATTERN = r"^[A-Z]{2,5}-\d+$"
LEGACY_ID_PATTERN = r"^(MON|DEF|AUDIT|ISSUE)-\d{4}-\d{2}-\d{2}-\d{3}$"
ISSUE_ID_PATTERN = f"({LINEAR_ID_PATTERN[1:-1]})|({LEGACY_ID_PATTERN[1:-1]})"


class FindingCategory(str, Enum):
    regression_watch = "regression-watch"
    scheduled_work = "scheduled-work"
    audit_finding = "audit-finding"
    bug = "bug"
    quality_gap = "quality-gap"
    feature = "feature"
    decision = "decision"


class FindingSeverity(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class FindingDimension(str, Enum):
    inputs_and_config = "inputs-and-config"
    reasoning_and_output = "reasoning-and-output"
    resilience_and_integration = "resilience-and-integration"


IssueIdField = Annotated[
    str,
    StringConstraints(pattern=ISSUE_ID_PATTERN, min_length=5, max_length=64),
]


class RegressionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linear_id: IssueIdField
    evidence: str = Field(min_length=20, max_length=2000)
    new_last_seen_date: date


class NewFindingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: FindingCategory
    title: str = Field(min_length=10, max_length=200)
    severity: FindingSeverity
    evidence: str = Field(min_length=20, max_length=4000)
    dimension: FindingDimension | None = None
    watch_for: str | None = Field(default=None, max_length=2000)
    priority: str | None = Field(default=None, pattern=r"^P[0-3]$")
    area: str | None = None
    pipelines: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_category_conditional_fields(self) -> NewFindingEntry:
        if self.category == FindingCategory.regression_watch and self.dimension is None:
            raise ValueError(
                "regression-watch findings must include a dimension "
                "(inputs-and-config | reasoning-and-output | resilience-and-integration)"
            )
        if self.category == FindingCategory.scheduled_work and self.priority is None:
            raise ValueError("scheduled-work findings must include a priority (P0|P1|P2|P3)")
        return self


class BumpEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linear_id: IssueIdField
    reproduction_note: str = Field(min_length=10, max_length=1000)


class ResolutionCitation(BaseModel):
    """Anchored evidence backing a `clean_runs >= 3` auto-promote claim.

    Three citation kinds are required for auto-promote: ``exercised`` (proves
    the watched code path ran in the bundle's traces), ``clean`` (proves the
    watch-for symptom was absent in that path), and ``coherent`` (cites the
    closing commit's diff against the original symptom). Each citation must
    anchor to at least one of: ``trace_id``, ``span_name``, or ``table_row``.
    Free-text quotes alone are rejected — anchors are how the orchestrator
    later spot-checks against fabrication.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["exercised", "clean", "coherent"]
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16,32}$")
    span_name: str | None = Field(default=None, max_length=200)
    table_row: str | None = Field(default=None, max_length=200)
    quote: str = Field(min_length=20, max_length=500)

    @model_validator(mode="after")
    def at_least_one_anchor(self) -> ResolutionCitation:
        if not (self.trace_id or self.span_name or self.table_row):
            raise ValueError(
                "citation needs at least one anchor: trace_id, span_name, or table_row"
            )
        return self


class ResolvedCandidateEntry(BaseModel):
    """Two lanes:

    - **Cautious lane** (``clean_runs`` 1 or 2): subagent reports the watch-for
      stayed absent for one more run; orchestrator bumps the counter on the
      Linear issue and parks at ``Resolved Candidate``. No citations needed.
    - **Auto-promote lane** (``clean_runs`` >= 3): subagent asserts the
      regression has structurally closed. Requires (a) all three citation
      kinds, each anchored to a concrete trace/span/table, and (b) the closing
      commit sha so ``process_review_findings.py`` can verify against
      ``git log --grep=SWI-NN``. The validator below rejects payloads that
      claim ``clean_runs >= 3`` without the full evidence bundle, so a drifted
      subagent cannot smuggle a self-asserted integer into a state flip.
    """

    model_config = ConfigDict(extra="forbid")

    linear_id: IssueIdField
    clean_runs: int = Field(ge=1, le=30)
    citations: list[ResolutionCitation] = Field(default_factory=list, max_length=10)
    closing_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")

    @model_validator(mode="after")
    def auto_promote_requires_three_anchored_citations(self) -> ResolvedCandidateEntry:
        if self.clean_runs < 3:
            return self
        kinds = {c.kind for c in self.citations}
        if kinds != {"exercised", "clean", "coherent"}:
            raise ValueError(
                "auto-promote (clean_runs>=3) requires citations with all three "
                "kinds: exercised, clean, coherent. Got: "
                f"{sorted(kinds) if kinds else 'none'}"
            )
        if not self.closing_commit:
            raise ValueError(
                "auto-promote (clean_runs>=3) requires closing_commit sha so the "
                "orchestrator can verify against git log --grep=<linear_id>"
            )
        return self


class FindingsBlock(BaseModel):
    """Top-level payload emitted by subagent reports.

    Every array is required (empty list is the positive way to say "none").
    extra="forbid" means unknown keys in any nested model fail parsing — the
    subagent contract cannot silently grow.
    """

    model_config = ConfigDict(extra="forbid")

    regressions: list[RegressionEntry] = Field(default_factory=list)
    new: list[NewFindingEntry] = Field(default_factory=list)
    bumps: list[BumpEntry] = Field(default_factory=list)
    resolved_candidates: list[ResolvedCandidateEntry] = Field(default_factory=list)


FENCED_JSON_PATTERN = re.compile(
    r"^[ \t]*```(?:json)?[ \t]*\n(?P<payload>.*?)\n[ \t]*```",
    re.DOTALL | re.MULTILINE,
)


def extract_findings_block(report_text: str) -> str | None:
    """Pull the last fenced JSON block out of a subagent report. Returns the
    raw JSON string or None when no fenced block is present. The orchestrator
    feeds the result to FindingsBlock.model_validate_json().

    Matches fenced blocks optionally prefixed with ```json. The payload is
    returned verbatim — JSON parser tolerates surrounding whitespace.
    """

    matches = list(FENCED_JSON_PATTERN.finditer(report_text))
    for match in reversed(matches):
        payload = match.group("payload").strip()
        if payload.startswith("{") and payload.endswith("}"):
            return payload
    return None
