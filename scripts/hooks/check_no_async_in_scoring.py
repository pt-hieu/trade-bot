#!/usr/bin/env python3
"""Pre-commit hook: forbid async / DB / LLM in scripts/shared/rules/scoring.py.

SWI-171 invariant: ``scoring.py`` must remain pure deterministic Python.
The whole rationale of moving feature weighting + threshold + regime
penalty math into a shared rules module is replay determinism — every
``pre_gate_candidates`` row snapshots the weights vector AND scoring
math, and the math has to be re-runnable from a frozen test rig with no
network or DB pool.

AST walk so docstring text mentioning forbidden symbols is ignored —
only syntactic violations fail. Catches:

  * ``await`` expressions and ``async def`` functions
  * ``import asyncio`` / ``from asyncio …``
  * ``import asyncpg`` / ``from asyncpg …``
  * ``Database()`` call expressions
  * imports from pydantic_ai / openai / anthropic / google.genai / cohere

Escape hatch: ``# HOOK-ALLOW: scoring-purity reason=<why>`` on the
violating line. The whole point of the rule is that ``scoring.py`` is a
leaf module — avoid using the escape hatch.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks._common import line_has_allow_marker  # noqa: E402

TARGET_PREFIX = "scripts/shared/rules/scoring/"  # package after SWI-212 split
HOOK_ALLOW_MARKER = "HOOK-ALLOW: scoring-purity"

_FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "asyncio",
    "asyncpg",
    "pydantic_ai",
    "openai",
    "anthropic",
    "google.genai",
    "cohere",
)


def _matches_forbidden(module: str | None) -> bool:
    if not module:
        return False
    return any(
        module == prefix or module.startswith(prefix + ".") for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )


def _check_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[tuple[int, str]] = []

    def _flag(lineno: int, label: str) -> None:
        if line_has_allow_marker(source_lines, lineno, lineno, HOOK_ALLOW_MARKER):
            return
        violations.append((lineno, label))

    for node in ast.walk(tree):
        if isinstance(node, ast.Await):
            _flag(node.lineno, "await expression")
        elif isinstance(node, ast.AsyncFunctionDef):
            _flag(node.lineno, f"async def {node.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _matches_forbidden(alias.name):
                    _flag(node.lineno, f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if _matches_forbidden(node.module):
                _flag(node.lineno, f"from {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Name)
                and func.id == "Database"
                or isinstance(func, ast.Attribute)
                and func.attr == "Database"
            ):
                _flag(node.lineno, "Database() call")

    return violations


def main(argv: list[str]) -> int:
    hits: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        if not raw.startswith(TARGET_PREFIX) or not raw.endswith(".py"):
            continue
        path = Path(raw)
        if not path.is_file():
            continue
        for lineno, label in _check_file(path):
            hits.append((raw, lineno, label))
    if hits:
        print(
            f"SWI-171 purity violation in {TARGET_PREFIX} — must stay pure deterministic Python "
            "(no async/DB/LLM). Move impure code to scripts/eval/score_recorder.py.",
            file=sys.stderr,
        )
        for rel, lineno, label in hits:
            print(f"  {rel}:{lineno}  [{label}]", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
