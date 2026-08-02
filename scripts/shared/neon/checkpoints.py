"""Pipeline checkpoint persistence for Phase 2 resume.

Saves/loads Phase2Result to DB so that Phase 3+ can resume
without re-running expensive sector analysis agents.
"""

import json
import logging
from datetime import date, timedelta

import numpy as np

from shared.database import execute, fetch_one

logger = logging.getLogger(__name__)

# Current schema version — bump when Phase2Result or PhaseIntermediates fields change
CHECKPOINT_SCHEMA_VERSION = 2

# Checkpoints older than this are auto-cleaned
CHECKPOINT_RETENTION_DAYS = 14


class _NumpySafeEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types gracefully."""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


async def save_checkpoint(
    scan_date: date,
    phase: str,
    data: dict,
    failed_sector_count: int = 0,
    total_sector_count: int = 0,
) -> bool:
    """Save a pipeline checkpoint to DB.

    Only saves if phase completed with acceptable quality
    (not all sectors failed).

    Returns True if saved, False if skipped.
    """
    # Don't checkpoint total failures
    if total_sector_count > 0 and failed_sector_count >= total_sector_count:
        logger.warning(
            "Checkpoint skipped: all %d sectors failed for %s phase '%s'",
            total_sector_count,
            scan_date,
            phase,
        )
        return False

    serialized_data = json.dumps(data, cls=_NumpySafeEncoder)

    # Smart upsert: only overwrite with same-or-better quality
    await execute(
        """
        INSERT INTO pipeline_checkpoints (scan_date, phase, schema_version, status, data)
        VALUES ($1, $2, $3, 'SUCCESS', $4::jsonb)
        ON CONFLICT (scan_date, phase)
        DO UPDATE SET
            data = EXCLUDED.data,
            status = EXCLUDED.status,
            schema_version = EXCLUDED.schema_version,
            created_at = NOW()
        WHERE pipeline_checkpoints.status != 'SUCCESS'
           OR EXCLUDED.schema_version >= pipeline_checkpoints.schema_version
        """,
        scan_date,
        phase,
        CHECKPOINT_SCHEMA_VERSION,
        serialized_data,
    )

    logger.info("Checkpoint saved: %s phase '%s'", scan_date, phase)

    # Auto-cleanup old checkpoints
    await _cleanup_old_checkpoints(scan_date)

    return True


async def load_checkpoint(scan_date: date, phase: str) -> dict | None:
    """Load a pipeline checkpoint from DB.

    Returns None if no checkpoint exists or schema version mismatches.
    """
    row = await fetch_one(
        """
        SELECT data, schema_version, status
        FROM pipeline_checkpoints
        WHERE scan_date = $1 AND phase = $2
        """,
        scan_date,
        phase,
    )

    if not row:
        return None

    schema_version = row.get("schema_version") or 0
    if schema_version != CHECKPOINT_SCHEMA_VERSION:
        logger.warning(
            "Checkpoint schema mismatch for %s phase '%s': "
            "stored=%d, current=%d — ignoring stale checkpoint",
            scan_date,
            phase,
            schema_version,
            CHECKPOINT_SCHEMA_VERSION,
        )
        return None

    status = row.get("status") or ""
    if status != "SUCCESS":
        logger.warning(
            "Checkpoint for %s phase '%s' has status '%s' — ignoring",
            scan_date,
            phase,
            status,
        )
        return None

    data = row.get("data")
    if isinstance(data, str):
        return json.loads(data)
    return data


async def _cleanup_old_checkpoints(current_scan_date: date) -> None:
    """Delete checkpoints older than retention period."""
    try:
        cutoff_date = current_scan_date - timedelta(days=CHECKPOINT_RETENTION_DAYS)
        await execute(
            "DELETE FROM pipeline_checkpoints WHERE scan_date < $1",
            cutoff_date,
        )
    except Exception as cleanup_error:
        logger.warning("Checkpoint cleanup failed (non-fatal): %s", cleanup_error)
