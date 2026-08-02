"""Schema-drift hook invariants.

2026-04-21 cascade: a SELECT added a column reference without the
ALTER TABLE migration, crashing midday + retro + catalyst. This hook
replays `scripts/db/migrations/*.sql` (with `schema.sql` as baseline)
into a `{table: set[column]}` oracle and compares against SQL literals
in `scripts/**/*.py`.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "check_schema_drift.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("check_schema_drift_for_test", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body).lstrip("\n"))
    return path


class TestMigrationReplay:
    def test_create_then_add_column(self, tmp_path: Path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations,
            "001_base.sql",
            """
            CREATE TABLE daily_records (
                id uuid PRIMARY KEY,
                record_date date NOT NULL,
                trading_mode text
            );
            """,
        )
        _write(
            migrations,
            "002_add_column.sql",
            """
            ALTER TABLE daily_records ADD COLUMN IF NOT EXISTS plan_type text;
            """,
        )

        schema = hook.build_schema_from_migrations(migrations)
        assert "daily_records" in schema
        assert {"id", "record_date", "trading_mode", "plan_type"} <= schema["daily_records"]

    def test_drop_column_removes(self, tmp_path: Path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations,
            "001_base.sql",
            """
            CREATE TABLE daily_records (id uuid PRIMARY KEY, stale_col text);
            """,
        )
        _write(
            migrations,
            "002_drop.sql",
            """
            ALTER TABLE daily_records DROP COLUMN IF EXISTS stale_col;
            """,
        )

        schema = hook.build_schema_from_migrations(migrations)
        assert "stale_col" not in schema["daily_records"]

    def test_rename_column(self, tmp_path: Path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations,
            "001_base.sql",
            """
            CREATE TABLE t (id uuid, old_name text);
            """,
        )
        _write(
            migrations,
            "002_rename.sql",
            """
            ALTER TABLE t RENAME COLUMN old_name TO new_name;
            """,
        )
        schema = hook.build_schema_from_migrations(migrations)
        assert "new_name" in schema["t"]
        assert "old_name" not in schema["t"]

    def test_baseline_plus_migrations(self, tmp_path: Path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        baseline = tmp_path / "schema.sql"
        baseline.write_text(
            textwrap.dedent(
                """
                CREATE TABLE daily_records (id uuid PRIMARY KEY, scan_date date);
                """
            ).lstrip("\n")
        )
        _write(
            migrations,
            "001_add_col.sql",
            """
            ALTER TABLE daily_records ADD COLUMN plan_type text;
            """,
        )

        schema = hook.build_schema_from_migrations(migrations, baseline)
        assert {"id", "scan_date", "plan_type"} <= schema["daily_records"]


class TestColumnExtraction:
    def test_select_columns(self):
        refs = hook.extract_column_refs(
            "SELECT ticker, plan_type, rationale FROM daily_recommendations WHERE record_id = $1"
        )
        assert ("select", "daily_recommendations", "ticker") in refs
        assert ("select", "daily_recommendations", "plan_type") in refs
        assert ("select", "daily_recommendations", "rationale") in refs

    def test_select_skips_joins(self):
        refs = hook.extract_column_refs("SELECT a, b FROM t1 JOIN t2 ON t1.id = t2.id")
        assert refs == []

    def test_select_skips_qualified_names(self):
        refs = hook.extract_column_refs("SELECT t.foo, t.bar FROM t")
        cols = {col for _, _, col in refs}
        assert cols == set()  # `t.foo` and `t.bar` are qualified; skipped

    def test_insert_columns(self):
        refs = hook.extract_column_refs(
            "INSERT INTO daily_records (id, scan_date, plan_type) VALUES ($1, $2, $3)"
        )
        cols = {col for kind, _, col in refs if kind == "insert"}
        assert {"id", "scan_date", "plan_type"} <= cols

    def test_update_columns(self):
        refs = hook.extract_column_refs(
            "UPDATE daily_records SET plan_type = $1, scan_date = $2 WHERE id = $3"
        )
        cols = {col for kind, _, col in refs if kind == "update"}
        assert {"plan_type", "scan_date"} <= cols

    def test_select_star_not_flagged(self):
        refs = hook.extract_column_refs("SELECT * FROM daily_records")
        assert refs == []


class TestAuditFile:
    def _schema(self) -> dict[str, set[str]]:
        return {"daily_records": {"id", "scan_date", "trading_mode"}}

    def test_unknown_column_flagged(self, tmp_path: Path):
        source = tmp_path / "probe.py"
        source.write_text(
            textwrap.dedent(
                """
                async def run(db):
                    await db.fetch_one(
                        "SELECT scan_date, bogus_column FROM daily_records WHERE id = $1",
                        1,
                    )
                """
            ).lstrip("\n")
        )
        offenses = hook.audit_file(source, self._schema())
        assert any("bogus_column" in o for o in offenses)
        assert not any("scan_date" in o and "not in" in o for o in offenses)

    def test_allow_marker_suppresses(self, tmp_path: Path):
        source = tmp_path / "probe.py"
        source.write_text(
            textwrap.dedent(
                """
                async def run(db):
                    await db.fetch_one(  # HOOK-ALLOW: schema-drift reason=dynamic
                        "SELECT bogus_column FROM daily_records WHERE id = $1",
                        1,
                    )
                """
            ).lstrip("\n")
        )
        offenses = hook.audit_file(source, self._schema())
        assert offenses == []

    def test_unknown_table_skipped(self, tmp_path: Path):
        """Tables not in the oracle are skipped rather than false-flagged.

        Common cases: CTEs, table aliases, test fixtures.
        """
        source = tmp_path / "probe.py"
        source.write_text(
            textwrap.dedent(
                """
                async def run(db):
                    await db.fetch_one("SELECT something FROM unknown_table WHERE id = $1", 1)
                """
            ).lstrip("\n")
        )
        offenses = hook.audit_file(source, self._schema())
        assert offenses == []


class TestReplayCascadeRegression:
    """Pin the 2026-04-21 defect: SELECT plan_type with no migration."""

    def test_missing_migration_fails(self, tmp_path: Path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        # Baseline has daily_recommendations WITHOUT plan_type (the 2026-04-20
        # state before migration 317 shipped).
        _write(
            migrations,
            "001_base.sql",
            """
            CREATE TABLE daily_recommendations (
                id uuid PRIMARY KEY,
                ticker text NOT NULL,
                action text
            );
            """,
        )

        schema = hook.build_schema_from_migrations(migrations)

        probe = tmp_path / "probe.py"
        probe.write_text(
            textwrap.dedent(
                """
                async def run(db):
                    await db.fetch_all("SELECT plan_type FROM daily_recommendations WHERE id = $1", 1)
                """
            ).lstrip("\n")
        )

        offenses = hook.audit_file(probe, schema)
        assert any("plan_type" in o for o in offenses)

    def test_with_migration_passes(self, tmp_path: Path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations,
            "001_base.sql",
            """
            CREATE TABLE daily_recommendations (id uuid PRIMARY KEY, ticker text);
            """,
        )
        _write(
            migrations,
            "002_add_plan_type.sql",
            """
            ALTER TABLE daily_recommendations ADD COLUMN plan_type text;
            """,
        )

        schema = hook.build_schema_from_migrations(migrations)

        probe = tmp_path / "probe.py"
        probe.write_text(
            textwrap.dedent(
                """
                async def run(db):
                    await db.fetch_all("SELECT plan_type FROM daily_recommendations WHERE id = $1", 1)
                """
            ).lstrip("\n")
        )

        offenses = hook.audit_file(probe, schema)
        assert offenses == []
