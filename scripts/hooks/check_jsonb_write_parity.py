"""Pre-commit hook: block JSONB writes that double-encode via the codec.

Why this exists
---------------
`scripts/shared/database.py` registers a project-wide jsonb codec whose
encoder is `json.dumps`. When a SQL writer pre-serializes a Python value
with `json.dumps(...)` and then binds the resulting string to a jsonb
parameter *without* an explicit ``::jsonb`` cast, the codec runs
``json.dumps`` a second time on the already-serialized string and the
value lands as ``jsonb_typeof='string'`` — the exact bug migration 307
cleaned up across 8 tables.

Rule (scoped to ``scripts/shared/neon/*.py``)
---------------------------------------------
Walk every ``await db.execute(...)`` / ``await db.fetch_val(...)`` /
``await db.fetch_one(...)`` / ``await db.fetch_all(...)`` / ``await
db.execute_many(...)`` call node. For each such call, extract the first
positional argument as the SQL text and enumerate the remaining
positional arguments as the parameter list. For every parameter whose
expression is a ``json.dumps(...)`` call or an identifier that traces
back to a ``json.dumps(...)`` assignment, require the SQL to reference
that parameter via ``$N::jsonb`` (where N is the 1-based parameter
index). Flag mismatches with ``file:line``.

This is intentionally narrow — it only examines files under
``scripts/shared/neon/`` and only call sites whose SQL is a literal
string. SQL built from f-strings or concatenations is skipped (the
``shared/neon`` layer uses literal SQL almost everywhere).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SCAN_ROOT = Path("scripts/shared/neon")
DB_METHODS: frozenset[str] = frozenset(
    {"execute", "execute_many", "fetch_val", "fetch_one", "fetch_all"}
)
_PARAM_RE = re.compile(r"\$(\d+)(::jsonb)?")


class _JsonDumpsLocalTracker(ast.NodeVisitor):
    """Collects local names bound to ``json.dumps(...)`` results.

    Scoped per-function. ``json_dumps_locals`` ends up as the set of
    identifiers in the current function whose most recent assignment is a
    ``json.dumps(...)`` call.
    """

    def __init__(self) -> None:
        self.json_dumps_locals: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        if _is_json_dumps_call(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.json_dumps_locals.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            node.value is not None
            and _is_json_dumps_call(node.value)
            and isinstance(node.target, ast.Name)
        ):
            self.json_dumps_locals.add(node.target.id)
        self.generic_visit(node)


def _is_json_dumps_call(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id == "json" and func.attr == "dumps"
    return False


def _is_db_method_call(node: ast.Call) -> str | None:
    """Return the method name if `node` is ``<db>.<method>(...)``, else None."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in DB_METHODS:
        return None
    return func.attr


def _sql_text(node: ast.AST | None) -> str | None:
    """Extract a SQL literal string, or None if not a plain literal.

    Supports:
      - ``ast.Constant`` (plain string literals)
      - ``ast.JoinedStr`` (f-strings) — concatenate only the constant chunks
        so ``$N::jsonb`` markers are preserved even when the SQL is built
        with dynamic column names (e.g. ``update_catalyst_field``).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append(" ")  # placeholder for interpolated segments
        return "".join(parts)
    return None


def _param_is_jsonb_cast(sql: str, index_1based: int) -> bool:
    """True if the SQL references ``$N::jsonb`` for the given 1-based param."""
    for match in _PARAM_RE.finditer(sql):
        if int(match.group(1)) == index_1based and match.group(2):
            return True
    return False


def _param_appears_at_all(sql: str, index_1based: int) -> bool:
    return any(int(m.group(1)) == index_1based for m in _PARAM_RE.finditer(sql))


def _param_expression_flagged(node: ast.AST, json_dumps_locals: set[str]) -> bool:
    """True if the parameter expression directly pre-serializes via json.dumps."""
    if _is_json_dumps_call(node):
        return True
    if isinstance(node, ast.Name) and node.id in json_dumps_locals:
        return True
    # `json.dumps(...) if ... else ...` — both branches may be jsonb-bound
    if isinstance(node, ast.IfExp):
        return _param_expression_flagged(node.body, json_dumps_locals) or _param_expression_flagged(
            node.orelse, json_dumps_locals
        )
    return False


def _check_call(
    call: ast.Call,
    json_dumps_locals: set[str],
    file: Path,
) -> list[str]:
    """Audit one `db.<method>(...)` call. Returns list of offending messages."""
    method = _is_db_method_call(call)
    if method is None:
        return []
    args = call.args
    if not args:
        return []
    sql = _sql_text(args[0])
    if sql is None:
        return []
    params = args[1:]
    offenses: list[str] = []
    # `execute_many` passes a single list-of-tuples argument — we cannot
    # statically match positional params. Instead warn if ANY `json.dumps`
    # expression appears in the call subtree without a ``::jsonb`` cast in
    # the SQL. False positives are preferable to the bug slipping through.
    if method == "execute_many":
        if "::jsonb" in sql:
            return []
        for node in ast.walk(call):
            if _is_json_dumps_call(node) or (
                isinstance(node, ast.Name) and node.id in json_dumps_locals
            ):
                offenses.append(
                    f"{file}:{call.lineno}: `execute_many` references a "
                    f"`json.dumps(...)` value but the SQL has no `::jsonb` cast. "
                    f"Either add the cast or pass the raw dict/list — the asyncpg "
                    f"codec will double-encode pre-serialized strings."
                )
                break
        return offenses
    for param_index, param in enumerate(params, start=1):
        if not _param_expression_flagged(param, json_dumps_locals):
            continue
        if not _param_appears_at_all(sql, param_index):
            # SQL uses fewer params than positional args (e.g. `RETURNING id`
            # row arg) — skip.
            continue
        if not _param_is_jsonb_cast(sql, param_index):
            offenses.append(
                f"{file}:{call.lineno}: parameter ${param_index} binds a "
                f"`json.dumps(...)` value to a JSONB-looking column but the SQL "
                f"lacks a matching `${param_index}::jsonb` cast — the asyncpg "
                f"codec will double-encode. Add `::jsonb` or drop the "
                f"`json.dumps` and pass the raw dict/list."
            )
    return offenses


def audit_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as exc:
        return [f"{path}: parse error: {exc}"]
    offenses: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        tracker = _JsonDumpsLocalTracker()
        tracker.visit(func)
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                offenses.extend(_check_call(node, tracker.json_dumps_locals, path))
    return offenses


def main(argv: list[str]) -> int:
    if argv:
        targets = [Path(a) for a in argv if Path(a).exists()]
    else:
        targets = sorted(SCAN_ROOT.rglob("*.py"))
    targets = [
        p
        for p in targets
        if p.suffix == ".py"
        and p.parts[:3] == ("scripts", "shared", "neon")
        and "__pycache__" not in p.parts
    ]
    all_offenses: list[str] = []
    for path in targets:
        all_offenses.extend(audit_file(path))
    if all_offenses:
        print("JSONB write-parity guard caught the following issues:\n")
        for msg in all_offenses:
            print(f"  - {msg}")
        print(
            "\nFix: either add `$N::jsonb` cast in the SQL or drop the "
            "`json.dumps` call and pass the raw dict/list — the registered "
            "codec will serialize correctly for dicts and lists."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
