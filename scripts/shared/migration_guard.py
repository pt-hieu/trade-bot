"""Pre-flight migration drift check for pipeline entrypoints.

Raises ``MigrationDriftError`` if any ``.sql`` file in
``scripts/db/migrations/`` lacks a row in ``schema_migrations``. Pipeline
entrypoints catch the error, print a remediation block, and ``sys.exit(1)``
before any LLM work begins.
"""

from __future__ import annotations

import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


class MigrationDriftError(RuntimeError):
    """Raised when on-disk migrations do not match ``schema_migrations`` rows."""

    def __init__(self, pending: list[str], reason: str = "pending migrations"):
        self.pending = pending
        self.reason = reason
        super().__init__(f"{reason}: {pending}")


async def assert_no_pending_migrations() -> None:
    """Raise ``MigrationDriftError`` if the DB is missing any on-disk migration."""
    from shared.database import get_db

    on_disk = {f.stem for f in MIGRATIONS_DIR.glob("*.sql")}
    if not on_disk:
        raise MigrationDriftError(
            [],
            reason=f"migrations directory empty or missing at {MIGRATIONS_DIR}",
        )

    db = await get_db()
    rows = await db.fetch_all("SELECT version FROM schema_migrations")
    applied = {r["version"] for r in rows}

    pending = sorted(on_disk - applied)
    if pending:
        raise MigrationDriftError(pending)


def report_drift_and_exit(drift: MigrationDriftError) -> None:
    """Print a remediation block for ``drift`` and ``sys.exit(1)``."""
    print(f"[migration-guard] ABORT: {drift.reason}", flush=True)
    for version in drift.pending:
        print(f"  - {version}.sql", flush=True)
    print(
        '[migration-guard] Fix: psql "<owner_url>" -v ON_ERROR_STOP=1 '
        "-f scripts/db/migrations/<filename>.sql && "
        'psql "<owner_url>" -c "INSERT INTO schema_migrations (version) '
        "VALUES ('<filename-without-.sql>') ON CONFLICT DO NOTHING;\"",
        flush=True,
    )
    sys.exit(1)
