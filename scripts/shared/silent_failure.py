"""Silent-failure invariants for the news pipeline.

Holds the exception classes + ratio thresholds used by
``data.narrative_tracker``. Concentrating them here keeps the guardrails
legible and lets that module stay under the CLAUDE.md 350-line cap.

Context: AUDIT-2026-04-24-001 / ISSUE-2026-04-24-003 — the narrative
tracker used to swallow every downstream error inside ``except Exception``,
which turned a full labeler outage into a silent zero-output run. The
exception is the pager hook (``news_pipeline_v2._main_async`` surfaces it
via ``send_telegram_error``).
"""

from __future__ import annotations

from datetime import date

# Common floor — below this volume, zero output is plausibly a real
# weekend/low-RSS day, not a silent failure.
SILENT_FAILURE_MIN_ARTICLES = 40

# Narrative tracker: high-volume days with <5% success ratio raise.
SILENT_FAILURE_MIN_SUCCESS_RATIO = 0.05

# Narrative tracker: labeling-task exceptions >20% of unmatched raise.
SILENT_FAILURE_MAX_LABELING_FAILURE_RATIO = 0.2


class NarrativeTrackerSilentFailure(RuntimeError):
    """Raised when narrative tracking processes a high-volume day but assigns ~nothing."""

    def __init__(
        self,
        scan_date: date,
        article_count: int,
        assigned: int,
        created: int,
        detail: str = "",
    ) -> None:
        self.scan_date = scan_date
        self.article_count = article_count
        self.assigned = assigned
        self.created = created
        suffix = f" ({detail})" if detail else ""
        super().__init__(
            f"NarrativeTrackerSilentFailure on {scan_date}: "
            f"{article_count} articles, {assigned} assigned + {created} created"
            f"{suffix}"
        )
