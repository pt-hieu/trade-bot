#!/usr/bin/env python3
"""Pre-commit hook: flag ``typing.Any`` usage in ``scripts/**/*.py``.

CLAUDE.md rule: "Typed signatures — use specific types, TypedDicts, `Union`,
`Protocol`, or `object`. Keep `Any` out so pyright stays effective."

AST walk rather than regex avoids false positives on string literals and
comments. Counts per file:
- ``from typing import Any`` / ``from typing import Any as X`` imports
- Annotations referencing ``Any``: direct (``x: Any``), subscripted
  (``list[Any]``, ``dict[str, Any]``), and Union members (``int | Any``).
- Any argument or return annotations on function definitions.

Baseline grandfathers existing occurrences in
``scripts/hooks/data/no_any_baseline.txt`` (18 files on seed). Regressions:
new files with Any annotations, or existing files whose Any count increases.

Escape hatches:
- ``# HOOK-ALLOW: no-any reason=<why>`` on the annotation line for isolated
  cases (e.g. third-party callbacks forcing ``Any``).
- Regenerate baseline after an intentional reduction/refactor with
  ``uv run python scripts/hooks/check_no_any_type.py --regenerate``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks._baseline import load_baseline, regress_diff, write_baseline  # noqa: E402
from hooks._common import iter_python_files, line_has_allow_marker  # noqa: E402

HOOK_ALLOW_MARKER = "HOOK-ALLOW: no-any"

EXEMPT_FILES: frozenset[str] = frozenset()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_BASELINE_PATH = _REPO_ROOT / "scripts" / "hooks" / "data" / "no_any_baseline.txt"


def _resolve_any_aliases(tree: ast.AST) -> set[str]:
    """Return the set of local names bound to typing.Any in this module."""
    aliases = {"Any"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                if alias.name == "Any":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _annotation_uses_any(annotation: ast.AST | None, any_names: set[str]) -> bool:
    if annotation is None:
        return False
    for sub in ast.walk(annotation):
        if isinstance(sub, ast.Name) and sub.id in any_names:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == "Any":
            value = sub.value
            if isinstance(value, ast.Name) and value.id == "typing":
                return True
    return False


def _count_any(path: Path) -> int:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return 0
    any_names = _resolve_any_aliases(tree)
    count = 0

    def _line_allowed(lineno: int) -> bool:
        return line_has_allow_marker(source_lines, lineno, lineno, HOOK_ALLOW_MARKER)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                if alias.name == "Any" and not _line_allowed(node.lineno):
                    count += 1
        elif isinstance(node, ast.AnnAssign):
            if _annotation_uses_any(node.annotation, any_names) and not _line_allowed(node.lineno):
                count += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in (
                list(node.args.args) + list(node.args.kwonlyargs) + list(node.args.posonlyargs)
            ):
                if _annotation_uses_any(arg.annotation, any_names) and not _line_allowed(
                    arg.lineno
                ):
                    count += 1
            if (
                node.args.vararg
                and _annotation_uses_any(node.args.vararg.annotation, any_names)
                and not _line_allowed(node.args.vararg.lineno)
            ):
                count += 1
            if (
                node.args.kwarg
                and _annotation_uses_any(node.args.kwarg.annotation, any_names)
                and not _line_allowed(node.args.kwarg.lineno)
            ):
                count += 1
            if _annotation_uses_any(node.returns, any_names) and not _line_allowed(node.lineno):
                count += 1
    return count


def _collect_current() -> dict[str, int]:
    results: dict[str, int] = {}
    for path in iter_python_files(_SCRIPTS_DIR):
        rel = str(path.relative_to(_REPO_ROOT))
        if rel in EXEMPT_FILES:
            continue
        count = _count_any(path)
        if count > 0:
            results[rel] = count
    return results


def regenerate() -> int:
    current = _collect_current()
    _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_baseline(_BASELINE_PATH, current)
    print(f"Wrote {len(current)} files with Any usage to {_BASELINE_PATH.relative_to(_REPO_ROOT)}")
    return 0


def main(argv: list[str]) -> int:
    if "--regenerate" in argv:
        return regenerate()
    baseline = load_baseline(_BASELINE_PATH)
    current = _collect_current()
    regressions = regress_diff(current, baseline)
    if regressions:
        print(
            "typing.Any usage grew (CLAUDE.md: 'Keep `Any` out so pyright stays effective').",
            file=sys.stderr,
        )
        for rel, base_count, curr_count in regressions:
            if base_count == 0:
                print(f"  {rel}: {curr_count} occurrence(s) (new file)", file=sys.stderr)
            else:
                print(
                    f"  {rel}: {curr_count} occurrence(s) (baseline {base_count})",
                    file=sys.stderr,
                )
        print(
            "Replace with a specific type / TypedDict / Union / Protocol. "
            "If a reduction is intentional, rerun with "
            "`uv run python scripts/hooks/check_no_any_type.py --regenerate`.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
