#!/usr/bin/env python3
"""Pre-commit hook: catch code that references columns not yet shipped in migrations.

Context (2026-04-21 cascade): commit e8f5b814 added
`SELECT plan_type FROM daily_recommendations` without shipping the
`ALTER TABLE ... ADD COLUMN plan_type`. Code compiled, ruff + pyright
passed. Midday, retro, and catalyst all crashed with
`UndefinedColumnError`.

Oracle
------
Composite: `scripts/db/schema.sql` is parsed as the historical baseline
(`CREATE TABLE` statements established before the migration system was
introduced) AND `scripts/db/migrations/*.sql` are replayed in filename
order as incremental deltas. The resulting `{table: set[col]}` map
represents what exists in the live DB.

Why the baseline is needed: the migrations directory only contains
incremental changes from `001_add_fk_indexes_daily.sql` onward. The 44
core tables (daily_records, daily_recommendations, trades_calculated,
articles, etc.) were created in `schema.sql` before the migration system
existed. A pure-migrations oracle would false-flag every SELECT against
those tables.

Policy: `schema.sql` is treated as the immutable baseline from here on.
Every schema change ships as a new migration file, NOT an edit to
`schema.sql`. The `docker-compose.yml` bootstrap for local dev still
reads `schema.sql`, which is why the file stays in place.

Code walker
-----------
AST-walk `scripts/**/*.py`. Extract every string literal that's the
first positional arg to `db.{execute,fetch_*}` / `connection.{execute,
fetch_*}` and parse the SQL for:
  - `SELECT c1, c2, ... FROM <table>`
  - `INSERT INTO <table> (c1, c2, ...) VALUES ...`
  - `UPDATE <table> SET c1 = ..., c2 = ...`

Unknown columns produce a `file:line: column X not in table Y` error.

Escape hatches
--------------
- `# HOOK-ALLOW: schema-drift reason=<why>` on the same line suppresses
  the check for f-string / dynamic SQL that this static walker can't
  parse.
- `EXEMPT_TABLES` covers things not in migrations (postgres system
  catalogs, e.g. `pg_tables`).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _REPO_ROOT / "scripts" / "db" / "migrations"
_BASELINE_SCHEMA = _REPO_ROOT / "scripts" / "db" / "schema.sql"
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

_DB_METHODS: frozenset[str] = frozenset(
    {"execute", "execute_many", "fetch_val", "fetch_one", "fetch_all", "fetchval", "fetchone"}
)

# Tables the static oracle doesn't know about (system catalogs, etc).
EXEMPT_TABLES: frozenset[str] = frozenset(
    {
        "pg_tables",
        "pg_stat_activity",
        "pg_stat_statements",
        "information_schema.columns",
        "information_schema.tables",
    }
)

# Columns every table is allowed to reference even if the migration oracle
# doesn't list them. These are either aliases, identifier prefixes, or
# SQL-builtin pseudo-columns that appear in our writer layer.
_UNIVERSAL_COLUMNS: frozenset[str] = frozenset(
    {
        "*",
        "count",
        "now",
        "null",
        "true",
        "false",
        "excluded",  # upsert alias
    }
)


# ---------------------------------------------------------------------------
# Migration oracle
# ---------------------------------------------------------------------------


_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)
_DROP_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)\s+DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)
_RENAME_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)\s+RENAME\s+COLUMN\s+(\w+)\s+TO\s+(\w+)",
    re.IGNORECASE,
)
_RENAME_TABLE_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)\s+RENAME\s+TO\s+(\w+)",
    re.IGNORECASE,
)
_DROP_TABLE_RE = re.compile(
    r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)


def _strip_sql_comments(sql: str) -> str:
    """Remove `-- ...` line comments + `/* ... */` block comments."""
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def _parse_create_table_columns(body: str) -> set[str]:
    """Extract column names from a CREATE TABLE (...) body.

    Handles inline PRIMARY KEY, CHECK, FOREIGN KEY constraints by ignoring
    lines whose first token is a keyword, not a column name.
    """
    columns: set[str] = set()
    depth = 0
    segments: list[str] = []
    current: list[str] = []
    for char in body:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            segments.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        segments.append("".join(current))

    constraint_starts = {
        "primary",
        "foreign",
        "constraint",
        "unique",
        "check",
        "like",
        "exclude",
    }
    for segment in segments:
        stripped = segment.strip()
        if not stripped:
            continue
        first = stripped.split(None, 1)[0].lower()
        if first in constraint_starts:
            continue
        match = re.match(r"\"?(\w+)\"?", stripped)
        if match:
            columns.add(match.group(1).lower())
    return columns


def _replay_sql_into(schema: dict[str, set[str]], sql: str) -> None:
    """Apply CREATE / ALTER / DROP statements from `sql` into `schema` in place."""
    for match in _CREATE_TABLE_RE.finditer(sql):
        table = match.group(1).lower()
        body = match.group(2)
        schema.setdefault(table, set()).update(_parse_create_table_columns(body))

    for match in _ADD_COLUMN_RE.finditer(sql):
        table = match.group(1).lower()
        col = match.group(2).lower()
        schema.setdefault(table, set()).add(col)

    for match in _DROP_COLUMN_RE.finditer(sql):
        table = match.group(1).lower()
        col = match.group(2).lower()
        schema.setdefault(table, set()).discard(col)

    for match in _RENAME_COLUMN_RE.finditer(sql):
        table = match.group(1).lower()
        old = match.group(2).lower()
        new = match.group(3).lower()
        cols = schema.setdefault(table, set())
        cols.discard(old)
        cols.add(new)

    for match in _RENAME_TABLE_RE.finditer(sql):
        old = match.group(1).lower()
        new = match.group(2).lower()
        if old in schema:
            schema[new] = schema.pop(old)

    for match in _DROP_TABLE_RE.finditer(sql):
        schema.pop(match.group(1).lower(), None)


def build_schema_from_migrations(
    migrations_dir: Path,
    baseline_path: Path | None = None,
) -> dict[str, set[str]]:
    """Build `{table: set[column]}` from baseline + migrations replayed in order."""
    schema: dict[str, set[str]] = {}
    if baseline_path is not None and baseline_path.exists():
        _replay_sql_into(
            schema,
            _strip_sql_comments(baseline_path.read_text(encoding="utf-8")),
        )
    files = sorted(migrations_dir.glob("*.sql"))
    for path in files:
        sql = _strip_sql_comments(path.read_text(encoding="utf-8"))
        _replay_sql_into(schema, sql)
    return schema


# ---------------------------------------------------------------------------
# SQL literal parsing
# ---------------------------------------------------------------------------


_SELECT_RE = re.compile(
    r"SELECT\s+(?P<cols>.+?)\s+FROM\s+(?P<table>\"?\w+\"?)",
    re.IGNORECASE | re.DOTALL,
)
_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+(?P<table>\"?\w+\"?)\s*\((?P<cols>[^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
_UPDATE_RE = re.compile(
    r"UPDATE\s+(?:ONLY\s+)?(?P<table>\"?\w+\"?)\s+SET\s+(?P<body>.+?)(?:\s+WHERE\b|\s+RETURNING\b|\s*;|\s*$)",
    re.IGNORECASE | re.DOTALL,
)


def _strip_quotes(ident: str) -> str:
    return ident.strip().strip('"').lower()


def _split_columns(raw: str) -> list[str]:
    """Tokenize a comma-separated column list, ignoring commas inside parens."""
    out: list[str] = []
    depth = 0
    current: list[str] = []
    for char in raw:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            out.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        out.append("".join(current).strip())
    return out


def _column_identifier(expr: str) -> str | None:
    """Extract a column name from a SELECT / UPDATE expression.

    Returns None for expressions this static walker can't attribute
    confidently:
      - `*` or numeric literals
      - function calls / arithmetic (paren or operator present)
      - qualified names (`alias.col` — alias may point to a different
        table the walker doesn't know about)
      - quoted string literals
    """
    expr = expr.strip()
    if not expr or expr == "*":
        return None
    if any(ch in expr for ch in "()+-*/|<>=!"):
        return None
    expr = re.sub(r"\s+AS\s+\w+$", "", expr, flags=re.IGNORECASE).strip()
    # Qualified (`t.col`) — we don't know what `t` aliases; skip.
    if "." in expr:
        return None
    # Strip surrounding quotes; numeric / stringly literals fall through.
    stripped = expr.strip().strip('"')
    if not re.fullmatch(r"[A-Za-z_]\w*", stripped):
        return None
    return stripped.lower()


def _assignment_column(expr: str) -> str | None:
    """Left-hand side of `col = expr` in an UPDATE SET body."""
    if "=" not in expr:
        return None
    left = expr.split("=", 1)[0].strip().strip('"')
    if not re.fullmatch(r"\w+", left):
        return None
    return left.lower()


_JOIN_RE = re.compile(r"\bJOIN\b", re.IGNORECASE)
_CTE_RE = re.compile(r"\bWITH\b[^;]+?\bAS\s*\(", re.IGNORECASE)


def extract_column_refs(sql: str) -> list[tuple[str, str, str]]:
    """Return `[(kind, table, column), ...]` from SELECT / INSERT / UPDATE clauses.

    `kind` is "select" / "insert" / "update". SQL must be a plain literal —
    f-string callers suppress via `# HOOK-ALLOW: schema-drift`.

    Conservative rules: SELECTs containing JOIN or CTE are skipped
    (ambiguous table-to-column attribution). INSERT/UPDATE targets exactly
    one table so remain in-scope.
    """
    refs: list[tuple[str, str, str]] = []

    select_sql = sql if not (_JOIN_RE.search(sql) or _CTE_RE.search(sql)) else ""
    for match in _SELECT_RE.finditer(select_sql):
        table = _strip_quotes(match.group("table"))
        cols_raw = match.group("cols")
        if " FROM " in cols_raw.upper():
            # The regex greedily grabbed multiple SELECTs; bail on this one.
            continue
        for expr in _split_columns(cols_raw):
            col = _column_identifier(expr)
            if col:
                refs.append(("select", table, col))

    for match in _INSERT_RE.finditer(sql):
        table = _strip_quotes(match.group("table"))
        for expr in _split_columns(match.group("cols")):
            col = _column_identifier(expr)
            if col:
                refs.append(("insert", table, col))

    for match in _UPDATE_RE.finditer(sql):
        table = _strip_quotes(match.group("table"))
        for assignment in _split_columns(match.group("body")):
            col = _assignment_column(assignment)
            if col:
                refs.append(("update", table, col))

    return refs


# ---------------------------------------------------------------------------
# Python AST walker
# ---------------------------------------------------------------------------


def _is_db_call(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    return func.attr in _DB_METHODS


def _sql_literal(node: ast.AST) -> str | None:
    """Return the SQL text only if it's a plain string literal (not f-string)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _line_has_allow_marker(source: str, lineno: int) -> bool:
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        return "HOOK-ALLOW: schema-drift" in lines[lineno - 1]
    return False


def audit_file(
    path: Path,
    schema: dict[str, set[str]],
) -> list[str]:
    """Audit one Python file. Returns offense strings."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return []

    offenses: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_db_call(node):
            continue
        if not node.args:
            continue
        sql = _sql_literal(node.args[0])
        if sql is None:
            continue
        if _line_has_allow_marker(source, node.lineno):
            continue

        for kind, table, column in extract_column_refs(sql):
            if table in EXEMPT_TABLES:
                continue
            if column in _UNIVERSAL_COLUMNS:
                continue
            if table not in schema:
                # Unknown table — skip rather than false-flag CTEs, table
                # aliases, or tables created in non-migration contexts
                # (e.g. test fixtures). A hook scoped to static SQL cannot
                # reliably distinguish these cases.
                continue
            if column not in schema[table]:
                offenses.append(
                    f"{path}:{node.lineno}: {kind.upper()} references `{column}` "
                    f"not in table `{table}` (per migrations oracle). "
                    f"Add a migration that ships this column before merging."
                )
    return offenses


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    schema = build_schema_from_migrations(_MIGRATIONS_DIR, _BASELINE_SCHEMA)
    if not schema:
        print(
            f"check-schema-drift: could not parse any tables from "
            f"{_BASELINE_SCHEMA} or {_MIGRATIONS_DIR}. Hook misconfigured.",
            file=sys.stderr,
        )
        return 2

    if argv:
        paths = [Path(a) for a in argv if a.endswith(".py")]
    else:
        paths = sorted(_SCRIPTS_DIR.rglob("*.py"))
    paths = [p for p in paths if p.is_file() and "__pycache__" not in p.parts]

    all_offenses: list[str] = []
    for path in paths:
        all_offenses.extend(audit_file(path, schema))

    if all_offenses:
        print(
            "Schema drift detected — code references columns not in migrations:\n", file=sys.stderr
        )
        for offense in all_offenses:
            print(f"  - {offense}", file=sys.stderr)
        print(
            "\nFix: ship the column via a new migration in "
            "scripts/db/migrations/. Dynamic SQL suppresses via "
            "`# HOOK-ALLOW: schema-drift reason=<why>` on the call line.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
