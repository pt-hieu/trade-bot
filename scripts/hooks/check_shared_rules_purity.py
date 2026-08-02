#!/usr/bin/env python3
"""Pre-commit hook: forbid LLM imports in ``scripts/shared/rules/``.

CLAUDE.md rule: "Centralized rules in `shared/rules/` — entry gates, R:R
floors, goal horizon live here as pure deterministic Python (no async/DB/LLM).
Single source of truth for main pipeline and resume path."

Scope refinement (2026-04-22): the historical wording was "no async/DB/LLM",
but `shared/rules/max_loss.py` is a deliberate "pure core + thin async DB
wrapper" consolidation (commit 612b8ab6) that dedupes 3 callers. The rule the
project actually wants enforced is "no LLM provider imports"; async/DB remain
permissible when they stay a thin wrapper around the deterministic core.

AST walk instead of regex because the original regex (`^from scripts\\.shared`)
had two bugs: (1) real imports are `from shared.*` (no `scripts.` prefix per
`sys.path` handling), (2) the rule we actually want is "no LLM" not "no DB".

Escape hatches:
- `# HOOK-ALLOW: shared-rules-llm reason=<why>` on the import line.
- `EXEMPT_FILES` for whole-file exemptions (empty today).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks._common import line_has_allow_marker  # noqa: E402

HOOK_ALLOW_MARKER = "HOOK-ALLOW: shared-rules-llm"

EXEMPT_FILES: frozenset[str] = frozenset()

# LLM provider packages that must not be imported from shared/rules/.
_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "pydantic_ai",
    "openai",
    "anthropic",
    "google.genai",
    "cohere",
)

SCAN_PREFIX = "scripts/shared/rules/"


def _matches_forbidden(module: str) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".") for prefix in _FORBIDDEN_PREFIXES
    )


def _check_file(relative_path: str, path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    source_lines = source.splitlines()
    violations: list[tuple[int, str]] = []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _matches_forbidden(alias.name):
                    if line_has_allow_marker(
                        source_lines, node.lineno, node.lineno, HOOK_ALLOW_MARKER
                    ):
                        continue
                    violations.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom) and node.module and _matches_forbidden(node.module):
            if line_has_allow_marker(source_lines, node.lineno, node.lineno, HOOK_ALLOW_MARKER):
                continue
            violations.append((node.lineno, f"from {node.module}"))
    return violations


def main(argv: list[str]) -> int:
    hits: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        relative_path = raw
        if not relative_path.startswith(SCAN_PREFIX):
            continue
        if relative_path in EXEMPT_FILES:
            continue
        path = Path(raw)
        if not path.is_file() or path.suffix != ".py":
            continue
        for lineno, snippet in _check_file(relative_path, path):
            hits.append((relative_path, lineno, snippet))
    if hits:
        print(
            "shared/rules/ must stay LLM-free (CLAUDE.md: 'Centralized rules in shared/rules/').",
            file=sys.stderr,
        )
        for rel, lineno, snippet in hits:
            print(f"  {rel}:{lineno}  {snippet}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
