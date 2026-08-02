"""Tests for scripts/hooks/check_migration_invariant_mirror.py (SWI-NN).

Hook contract: when a migration adds `CHECK (...)` to a table, the same commit
must either touch `scripts/shared/rules/row_invariants/{table}.py` or carry a
bypass marker `# row_invariant_mirror: not_applicable — SWI-NN: <reason>`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HOOK_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "hooks"
    / "check_migration_invariant_mirror.py"
)


def _run_hook(*paths: str, audit: bool = False) -> tuple[int, str]:
    cmd = [sys.executable, str(HOOK_PATH)]
    if audit:
        cmd.append("--audit")
    cmd.extend(paths)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


class TestMigrationMirrorHook:
    @pytest.fixture
    def tmp_repo(self, tmp_path):
        """Build a synthetic repo layout the hook can scan."""
        (tmp_path / "scripts" / "db" / "migrations").mkdir(parents=True)
        (tmp_path / "scripts" / "shared" / "rules" / "row_invariants").mkdir(parents=True)
        (tmp_path / "scripts" / "shared" / "rules" / "row_invariants" / "__init__.py").write_text(
            ""
        )
        return tmp_path

    def test_check_without_mirror_fails_in_enforce(self, tmp_repo):
        sql = tmp_repo / "scripts" / "db" / "migrations" / "999_test.sql"
        sql.write_text(
            "ALTER TABLE foo_table\n  ADD CONSTRAINT foo_test_chk CHECK (col IN ('A','B'));\n"
        )
        rc, out = _run_hook(str(sql))
        assert rc != 0
        assert "row_invariants/foo_table.py" in out or "foo_table" in out

    def test_check_with_mirror_passes(self, tmp_repo):
        sql = tmp_repo / "scripts" / "db" / "migrations" / "999_test.sql"
        sql.write_text(
            "ALTER TABLE foo_table\n  ADD CONSTRAINT foo_test_chk CHECK (col IN ('A','B'));\n"
        )
        mirror = tmp_repo / "scripts" / "shared" / "rules" / "row_invariants" / "foo_table.py"
        mirror.write_text("def validate_row(row): return []\n")
        rc, out = _run_hook(str(sql), str(mirror))
        assert rc == 0, f"Expected pass; got {rc}: {out}"

    def test_bypass_marker_with_swi_passes(self, tmp_repo):
        sql = tmp_repo / "scripts" / "db" / "migrations" / "999_test.sql"
        sql.write_text(
            "-- row_invariant_mirror: not_applicable — SWI-123: ephemeral test data only\n"
            "ALTER TABLE foo_table\n"
            "  ADD CONSTRAINT foo_test_chk CHECK (col IN ('A','B'));\n"
        )
        rc, out = _run_hook(str(sql))
        assert rc == 0, f"Bypass with SWI-NN should pass; got {rc}: {out}"

    def test_bypass_marker_without_swi_fails(self, tmp_repo):
        sql = tmp_repo / "scripts" / "db" / "migrations" / "999_test.sql"
        sql.write_text(
            "-- row_invariant_mirror: not_applicable — no reason\n"
            "ALTER TABLE foo_table\n"
            "  ADD CONSTRAINT foo_test_chk CHECK (col IN ('A','B'));\n"
        )
        rc, out = _run_hook(str(sql))
        assert rc != 0

    def test_no_check_in_migration_passes(self, tmp_repo):
        sql = tmp_repo / "scripts" / "db" / "migrations" / "999_test.sql"
        sql.write_text("ALTER TABLE foo_table\n  ADD COLUMN IF NOT EXISTS new_col TEXT;\n")
        rc, _ = _run_hook(str(sql))
        assert rc == 0

    def test_audit_mode_warns_does_not_fail(self, tmp_repo):
        sql = tmp_repo / "scripts" / "db" / "migrations" / "999_test.sql"
        sql.write_text(
            "ALTER TABLE foo_table\n  ADD CONSTRAINT foo_test_chk CHECK (col IN ('A','B'));\n"
        )
        rc, _ = _run_hook(str(sql), audit=True)
        assert rc == 0
