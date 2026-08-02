"""Unit tests for the fenced-JSON findings contract between /pipeline-review
or /audit subagents and the Linear write-back orchestrator.
"""

import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from linear_migration.findings_schema import (
    FindingCategory,
    FindingDimension,
    FindingsBlock,
    ResolvedCandidateEntry,
    extract_findings_block,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestFindingsBlockHappyPath:
    def test_empty_block_validates(self):
        block = FindingsBlock.model_validate_json(
            '{"regressions":[],"new":[],"bumps":[],"resolved_candidates":[]}'
        )
        assert block.regressions == []
        assert block.new == []

    def test_full_block_validates(self):
        payload = """
        {
          "regressions": [
            {
              "linear_id": "SWY-42",
              "evidence": "2026-04-25 scan shows sector_aggregator dur=120 null-token hang, matching MON-2026-04-13-002 resolved signal",
              "new_last_seen_date": "2026-04-25"
            }
          ],
          "new": [
            {
              "category": "regression-watch",
              "title": "New hallucinated VN ticker tagging on 2026-04-25 articles",
              "severity": "warning",
              "evidence": "articles.affected_tickers contains OKX, XIV, WHR on 2026-04-25 despite ticker whitelist",
              "dimension": "reasoning-and-output"
            }
          ],
          "bumps": [
            {
              "linear_id": "SWY-11",
              "reproduction_note": "2026-04-25 reproduced — same null-token pattern on 2 sector_aggregator runs"
            }
          ],
          "resolved_candidates": [
            {"linear_id": "SWY-7", "clean_runs": 2}
          ]
        }
        """
        block = FindingsBlock.model_validate_json(payload)
        assert block.regressions[0].linear_id == "SWY-42"
        assert block.new[0].category == FindingCategory.regression_watch
        assert block.new[0].dimension == FindingDimension.reasoning_and_output
        assert block.bumps[0].linear_id == "SWY-11"
        assert block.resolved_candidates[0].clean_runs == 2

    def test_legacy_id_accepted(self):
        payload = '{"regressions":[],"new":[],"bumps":[{"linear_id":"MON-2026-04-13-002","reproduction_note":"same null-token hang"}],"resolved_candidates":[]}'
        block = FindingsBlock.model_validate_json(payload)
        assert block.bumps[0].linear_id == "MON-2026-04-13-002"

    def test_scheduled_work_with_priority_validates(self):
        payload = """
        {"regressions":[],"bumps":[],"resolved_candidates":[],
         "new":[{
           "category": "scheduled-work",
           "title": "Re-tighten HoldingData types from list[dict] to list[HoldingData]",
           "severity": "info",
           "evidence": "pyright list-invariance fails on 10 call sites; 19-file Sequence cascade deferred",
           "priority": "P2",
           "area": "types"
         }]}
        """
        block = FindingsBlock.model_validate_json(payload)
        assert block.new[0].priority == "P2"


class TestFindingsBlockValidationFailures:
    def test_extra_keys_rejected(self):
        payload = '{"regressions":[],"new":[],"bumps":[],"resolved_candidates":[],"extra":"oops"}'
        with pytest.raises(ValidationError) as exc:
            FindingsBlock.model_validate_json(payload)
        assert "extra" in str(exc.value).lower()

    def test_unknown_category_rejected(self):
        payload = '{"regressions":[],"bumps":[],"resolved_candidates":[],"new":[{"category":"unknown-cat","title":"Long enough title here","severity":"info","evidence":"Evidence text long enough to pass"}]}'
        with pytest.raises(ValidationError):
            FindingsBlock.model_validate_json(payload)

    def test_regression_watch_without_dimension_rejected(self):
        payload = '{"regressions":[],"bumps":[],"resolved_candidates":[],"new":[{"category":"regression-watch","title":"Title long enough here","severity":"critical","evidence":"Evidence long enough to pass minimum length"}]}'
        with pytest.raises(ValidationError) as exc:
            FindingsBlock.model_validate_json(payload)
        assert "dimension" in str(exc.value).lower()

    def test_scheduled_work_without_priority_rejected(self):
        payload = '{"regressions":[],"bumps":[],"resolved_candidates":[],"new":[{"category":"scheduled-work","title":"Title long enough here","severity":"info","evidence":"Evidence long enough to pass minimum length"}]}'
        with pytest.raises(ValidationError) as exc:
            FindingsBlock.model_validate_json(payload)
        assert "priority" in str(exc.value).lower()

    def test_malformed_id_rejected(self):
        payload = '{"regressions":[],"new":[],"resolved_candidates":[],"bumps":[{"linear_id":"not-an-id","reproduction_note":"reproduction note long enough"}]}'
        with pytest.raises(ValidationError):
            FindingsBlock.model_validate_json(payload)

    def test_short_evidence_rejected(self):
        payload = '{"regressions":[{"linear_id":"SWY-1","evidence":"short","new_last_seen_date":"2026-04-25"}],"new":[],"bumps":[],"resolved_candidates":[]}'
        with pytest.raises(ValidationError):
            FindingsBlock.model_validate_json(payload)

    def test_bad_priority_rejected(self):
        payload = '{"regressions":[],"bumps":[],"resolved_candidates":[],"new":[{"category":"scheduled-work","title":"Title long enough here","severity":"info","evidence":"Evidence long enough to pass minimum length","priority":"P9"}]}'
        with pytest.raises(ValidationError):
            FindingsBlock.model_validate_json(payload)

    def test_severity_invalid_rejected(self):
        payload = '{"regressions":[],"bumps":[],"resolved_candidates":[],"new":[{"category":"bug","title":"Title long enough here","severity":"fatal","evidence":"Evidence long enough to pass minimum length"}]}'
        with pytest.raises(ValidationError):
            FindingsBlock.model_validate_json(payload)


class TestExtractFindingsBlock:
    def test_extracts_fenced_json_block(self):
        report = """
        # Report

        Some analysis here.

        ```json
        {"regressions":[],"new":[],"bumps":[],"resolved_candidates":[]}
        ```
        """
        payload = extract_findings_block(report)
        assert payload is not None
        block = FindingsBlock.model_validate_json(payload)
        assert block.regressions == []

    def test_extracts_last_fenced_block_when_multiple(self):
        report = """
        ```json
        {"old": "ignore"}
        ```

        Further analysis below.

        ```json
        {"regressions":[],"new":[],"bumps":[],"resolved_candidates":[]}
        ```
        """
        payload = extract_findings_block(report)
        assert payload is not None
        assert "regressions" in payload
        assert "old" not in payload

    def test_returns_none_when_no_fenced_block(self):
        report = "# Report\n\nJust text here, no JSON block."
        assert extract_findings_block(report) is None

    def test_handles_fenced_block_without_json_language_tag(self):
        report = """
        ```
        {"regressions":[],"new":[],"bumps":[],"resolved_candidates":[]}
        ```
        """
        payload = extract_findings_block(report)
        assert payload is not None
        block = FindingsBlock.model_validate_json(payload)
        assert block.regressions == []


# ---- ResolvedCandidateEntry auto-promote contract ----------------------------

_CITATION_QUOTE = "watched span ran clean across the audited slice no symptom"


def _citation(kind: str, **anchors: str) -> dict[str, object]:
    payload: dict[str, object] = {"kind": kind, "quote": _CITATION_QUOTE}
    payload.update(anchors)
    return payload


class TestResolvedCandidateAutoPromoteContract:
    def test_cautious_lane_passes_without_citations(self) -> None:
        entry = ResolvedCandidateEntry.model_validate({"linear_id": "SWI-7", "clean_runs": 2})
        assert entry.clean_runs == 2
        assert entry.citations == []
        assert entry.closing_commit is None

    def test_auto_promote_with_full_bundle_passes(self) -> None:
        payload = {
            "linear_id": "SWI-7",
            "clean_runs": 3,
            "closing_commit": "abcdef0",
            "citations": [
                _citation("exercised", trace_id="0123456789abcdef"),
                _citation("clean", span_name="sector_aggregator"),
                _citation("coherent", table_row="agent_beliefs ticker=FPT"),
            ],
        }
        entry = ResolvedCandidateEntry.model_validate(payload)
        assert entry.closing_commit == "abcdef0"
        assert {c.kind for c in entry.citations} == {"exercised", "clean", "coherent"}

    def test_auto_promote_missing_closing_commit_rejected(self) -> None:
        payload = {
            "linear_id": "SWI-7",
            "clean_runs": 3,
            "citations": [
                _citation("exercised", trace_id="0123456789abcdef"),
                _citation("clean", span_name="sector_aggregator"),
                _citation("coherent", table_row="agent_beliefs ticker=FPT"),
            ],
        }
        with pytest.raises(ValidationError) as exc:
            ResolvedCandidateEntry.model_validate(payload)
        assert "closing_commit" in str(exc.value)

    def test_auto_promote_missing_kind_rejected(self) -> None:
        payload = {
            "linear_id": "SWI-7",
            "clean_runs": 3,
            "closing_commit": "abcdef0",
            "citations": [
                _citation("exercised", trace_id="0123456789abcdef"),
                _citation("clean", span_name="sector_aggregator"),
            ],
        }
        with pytest.raises(ValidationError) as exc:
            ResolvedCandidateEntry.model_validate(payload)
        assert "exercised, clean, coherent" in str(exc.value)

    def test_citation_without_anchor_rejected(self) -> None:
        payload = {
            "linear_id": "SWI-7",
            "clean_runs": 3,
            "closing_commit": "abcdef0",
            "citations": [
                {"kind": "exercised", "quote": _CITATION_QUOTE},
                _citation("clean", span_name="sector_aggregator"),
                _citation("coherent", table_row="agent_beliefs ticker=FPT"),
            ],
        }
        with pytest.raises(ValidationError) as exc:
            ResolvedCandidateEntry.model_validate(payload)
        assert "anchor" in str(exc.value)

    def test_citation_bad_trace_id_rejected(self) -> None:
        payload = {
            "linear_id": "SWI-7",
            "clean_runs": 3,
            "closing_commit": "abcdef0",
            "citations": [
                _citation("exercised", trace_id="NOT-A-HEX-TRACE"),
                _citation("clean", span_name="sector_aggregator"),
                _citation("coherent", table_row="agent_beliefs ticker=FPT"),
            ],
        }
        with pytest.raises(ValidationError):
            ResolvedCandidateEntry.model_validate(payload)


# ---- Bucket-vs-prompt parity (drift guard) -----------------------------------


class TestSubagentPromptsReferenceEveryBucket:
    """Every top-level FindingsBlock bucket must be named in BOTH the
    pipeline-review subagent prompts and the audit instructions. Adding a
    bucket to the schema without teaching the subagents how to emit it ships
    silently — this guard fails the pre-commit hook on drift.
    """

    def test_pipeline_review_prompts_reference_every_bucket(self) -> None:
        prompts = (
            REPO_ROOT / ".claude/skills/pipeline-review/references/subagent-prompts.md"
        ).read_text()
        for bucket in FindingsBlock.model_fields:
            assert bucket in prompts, (
                f"pipeline-review subagent-prompts.md missing bucket: {bucket}"
            )

    def test_audit_instructions_reference_every_bucket(self) -> None:
        instructions = (REPO_ROOT / ".claude/skills/audit/instructions.md").read_text()
        for bucket in FindingsBlock.model_fields:
            assert bucket in instructions, f"audit instructions.md missing bucket: {bucket}"
