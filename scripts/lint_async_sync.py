#!/usr/bin/env python3
"""Lint: detect _sync() calls inside async def functions.

Catches the pattern where sync wrappers (which use asyncio.run())
are called from within async code — causing RuntimeError in Python 3.12.

Usage:
    uv run python scripts/lint_async_sync.py
"""

import ast
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

# Files that legitimately use _sync wrappers (standalone CLI, not async pipelines)
ALLOW_LIST = {
    "shared/neon/_sync.py",
}


class SyncInAsyncChecker(ast.NodeVisitor):
    """Find _sync() calls inside async function bodies."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.violations: list[str] = []
        self._in_async = False
        self._sync_imports: set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track imports of *_sync names from shared.neon."""
        if node.module and "shared.neon" in node.module:
            for alias in node.names or []:
                orig = alias.name
                local = alias.asname or alias.name
                if orig.endswith("_sync"):
                    self._sync_imports.add(local)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        old = self._in_async
        self._in_async = True
        self.generic_visit(node)
        self._in_async = old

    def visit_FunctionDef(self, node: ast.FunctionDef):
        old = self._in_async
        self._in_async = False
        self.generic_visit(node)
        self._in_async = old

    def visit_Call(self, node: ast.Call):
        if self._in_async:
            name = _get_call_name(node)
            if name and name in self._sync_imports:
                self.violations.append(
                    f"  {self.filepath}:{node.lineno}: "
                    f"{name}() inside async function — use async version"
                )
        self.generic_visit(node)


def _get_call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def main() -> int:
    violations: list[str] = []
    for py_file in sorted(SCRIPTS_DIR.rglob("*.py")):
        rel = py_file.relative_to(SCRIPTS_DIR)
        if str(rel) in ALLOW_LIST:
            continue

        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        checker = SyncInAsyncChecker(str(rel))
        checker.visit(tree)
        violations.extend(checker.violations)

    if violations:
        print("ERROR: _sync() calls found inside async functions:")
        print("\n".join(violations))
        print(f"\n{len(violations)} violation(s). Use async versions instead.")
        return 1

    print("OK: no _sync() calls inside async functions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
