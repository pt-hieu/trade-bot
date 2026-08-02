"""Idempotency bookkeeping for the Linear write-back path.

Every /pipeline-review and /audit report is hashed once; the resulting report
id gates whether the orchestrator re-enters Linear writes on a re-run. The
sentinel file carries the list of Linear ids touched by that report so a
rerun can short-circuit cleanly or re-process in --force mode.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SENTINEL_DIR = Path(__file__).resolve().parent / "processed_reports"


@dataclass
class ProcessedReport:
    """One sentinel record per processed report."""

    report_id: str
    processed_at: str
    source_kind: str
    touched_linear_ids: list[str] = field(default_factory=list)
    created_linear_ids: list[str] = field(default_factory=list)
    note: str = ""


def compute_report_id(report_text: str) -> str:
    """Stable 12-hex report id derived from the full report text.

    The orchestrator is expected to pass the exact bytes it shows the user.
    Two runs that would produce the same Linear mutations must share a hash —
    so include anything that influences mutation, and nothing that does not.
    """

    digest = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
    return digest[:12]


def sentinel_path(report_id: str) -> Path:
    return SENTINEL_DIR / f"{report_id}.json"


def is_already_processed(report_id: str) -> bool:
    return sentinel_path(report_id).exists()


def load_sentinel(report_id: str) -> ProcessedReport | None:
    path = sentinel_path(report_id)
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    return ProcessedReport(**raw)


def record_sentinel(
    report_id: str,
    *,
    source_kind: str,
    touched_linear_ids: list[str],
    created_linear_ids: list[str],
    note: str = "",
) -> Path:
    """Commit the sentinel. Called after the orchestrator finishes all Linear
    MCP writes for a report. Directory is created on first write.
    """

    SENTINEL_DIR.mkdir(parents=True, exist_ok=True)
    record = ProcessedReport(
        report_id=report_id,
        processed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source_kind=source_kind,
        touched_linear_ids=touched_linear_ids,
        created_linear_ids=created_linear_ids,
        note=note,
    )
    path = sentinel_path(report_id)
    path.write_text(json.dumps(asdict(record), indent=2, sort_keys=True) + "\n")
    return path
