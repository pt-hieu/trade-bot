"""Parity guard: PERSIST_OK_STATUSES vs the catalysts.expected_status DB constraint.

Hits ``scripts/db/migrations/331_catalyst_expected_status.sql`` (the DDL
authority for the ``expected_status`` text-CHECK column) so any future enum
addition forces a same-change update of the Python allowlist + this test.

CLAUDE.md "Pipeline Resilience" rule: DB enum parity must be enforced — Python
allowlists match the DB exactly, and a new status = migration + Python set
update + parity test refresh in the same change.
"""

from __future__ import annotations

import re
from pathlib import Path

from shared.rules.catalyst_expected_parser import PERSIST_OK_STATUSES

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "db"
    / "migrations"
    / "331_catalyst_expected_status.sql"
)


def _parse_check_values() -> set[str]:
    raw_sql = MIGRATION_PATH.read_text(encoding="utf-8")
    sql_without_line_comments = re.sub(r"--[^\n]*", "", raw_sql)
    match = re.search(
        r"expected_status\s+IN\s*\(([^)]+)\)",
        sql_without_line_comments,
        flags=re.IGNORECASE,
    )
    assert match, f"could not locate expected_status CHECK list in {MIGRATION_PATH}"
    return {value.strip().strip("'") for value in match.group(1).split(",")}


def test_persist_ok_statuses_matches_db_check_constraint() -> None:
    db_values = _parse_check_values()
    expected = set(PERSIST_OK_STATUSES) | {"unparseable"}
    assert db_values == expected, f"enum drift: db={sorted(db_values)} python={sorted(expected)}"
