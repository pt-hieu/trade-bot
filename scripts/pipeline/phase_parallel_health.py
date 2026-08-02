"""Phase 2 health accounting — partial-failure span emission.

Extracted from `phase_parallel.py` (Challenge F5 / CLAUDE.md file-size cap).
Keeps the 100%-collapse guard in `phase_parallel.py` unchanged — this module
covers the in-between degraded case (some sectors failed but not all) so
monitoring can distinguish "clean morning" from "degraded morning" without
any change in control flow.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.observability import span

logger = logging.getLogger(__name__)

# At or above this ratio, emit a `phase2_partial_failure` span. Chosen so a
# single failed sector in a 5-sector morning (~20%) does NOT fire, but two
# failures (~40%) does. Pairs with the belief-fallback path so degraded
# mornings are both visible and actionable.
PARTIAL_FAILURE_RATIO_THRESHOLD: float = 0.30

# At or above this ratio, the synthesizer must NOT publish recommendations
# from the surviving sector signal: >85% of sectors produced nothing, so
# what remains is too narrow a slice of the universe to drive recs.
# Downstream picks must drop sector_signals and route through the
# deterministic belief-fallback path instead.
AGGREGATOR_ONLY_RATIO_THRESHOLD: float = 0.5

# Canonical degraded-mode tag set by ``apply_aggregator_only_gate`` and
# consumed by Phase 3b. Centralised so a typo cannot silently re-enable
# the partial-coverage publish path.
DEGRADED_MODE_AGGREGATOR_ONLY: str = "aggregator_only"


def compute_partial_failure_ratio(*, failed_sector_count: int, total_sectors: int) -> float:
    """Return `failed / total` as a ratio in [0.0, 1.0]. 0 when no sectors.

    Deterministic Python — no DB, no LLM, no side effects. Shared by the
    telemetry emitter and (optionally) collector summaries so both read the
    same definition.
    """
    if total_sectors <= 0:
        return 0.0
    return failed_sector_count / total_sectors


def should_force_aggregator_only(
    *,
    failed_sector_count: int,
    total_sectors: int,
    threshold: float = AGGREGATOR_ONLY_RATIO_THRESHOLD,
) -> bool:
    """Return True when the failed-sector ratio crosses the aggregator-only floor.

    When True, downstream phases must drop the partially-covered sector
    signal layer and rely on the deterministic aggregator/belief-fallback
    path. Pure deterministic Python — same source of truth as the span
    emitter so live telemetry and the control-flow gate agree.
    """
    ratio = compute_partial_failure_ratio(
        failed_sector_count=failed_sector_count,
        total_sectors=total_sectors,
    )
    return ratio >= threshold


def apply_aggregator_only_gate(
    *,
    phase2_health,
    scan_date: str,
    failed_sector_count: int,
    total_sectors: int,
    failed_sector_names: list[str],
) -> None:
    """Stamp ``degraded_mode`` + emit ``degraded_pipeline_mode`` span.

    Mutates ``phase2_health.degraded_mode`` to ``"aggregator_only"`` when
    the failed-sector ratio meets the threshold. Caller passes
    ``phase2_health`` (a ``PhaseHealth`` instance, but typed as ``Any``
    here to avoid an upward dependency on ``pipeline.types``).
    """
    if phase2_health is None:
        return
    if not should_force_aggregator_only(
        failed_sector_count=failed_sector_count,
        total_sectors=total_sectors,
    ):
        return

    phase2_health.degraded_mode = DEGRADED_MODE_AGGREGATOR_ONLY
    with span(
        "degraded_pipeline_mode",
        mode=DEGRADED_MODE_AGGREGATOR_ONLY,
        scan_date=scan_date,
        failed_sector_count=failed_sector_count,
        total_sectors=total_sectors,
        threshold=AGGREGATOR_ONLY_RATIO_THRESHOLD,
        failed_sector_names=failed_sector_names[:16],
    ):
        logger.warning(
            "DEGRADED_PIPELINE_MODE=%s ratio>=%.2f failed=%d/%d names=%s",
            DEGRADED_MODE_AGGREGATOR_ONLY,
            AGGREGATOR_ONLY_RATIO_THRESHOLD,
            failed_sector_count,
            total_sectors,
            failed_sector_names[:16],
        )


def emit_partial_failure_span(
    *,
    scan_date: str,
    failed_sector_count: int,
    total_sectors: int,
    failed_sector_names: list[str],
    threshold: float = PARTIAL_FAILURE_RATIO_THRESHOLD,
    extra: dict[str, Any] | None = None,
) -> float:
    """Emit a `phase2_partial_failure` span when ratio crosses threshold.

    Does NOT raise. Does NOT change control flow. Returns the computed ratio
    so the caller can thread it into adjacent telemetry (e.g.,
    `silent_hang_alert` Telegram message). Ratio below the threshold = no
    span emitted, but the value is still returned for the caller's logs.
    """
    ratio = compute_partial_failure_ratio(
        failed_sector_count=failed_sector_count,
        total_sectors=total_sectors,
    )
    if ratio < threshold:
        return ratio

    attrs: dict[str, Any] = {
        "scan_date": scan_date,
        "failed_sector_count": failed_sector_count,
        "total_sectors": total_sectors,
        "partial_failure_ratio": round(ratio, 3),
        "failed_sector_names": failed_sector_names[:16],
    }
    if extra:
        attrs.update(extra)
    with span("phase2_partial_failure", **attrs):
        logger.warning(
            "PHASE2_PARTIAL_FAILURE ratio=%.2f failed=%d/%d names=%s",
            ratio,
            failed_sector_count,
            total_sectors,
            failed_sector_names[:16],
        )
    return ratio
