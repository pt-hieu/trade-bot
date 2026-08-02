"""Shared helpers for ``scripts/hooks/check_*.py``.

Extracted once three hooks repeated the same walk/marker logic. Hook scripts
should import from here rather than reimplementing; that keeps the escape-
hatch semantics (``HOOK-ALLOW: <rule>``) consistent across rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path


def iter_python_files(root: Path, scopes: Sequence[str] | None = None) -> list[Path]:
    """Walk ``.py`` files under ``root``, skipping ``__pycache__``.

    ``scopes`` is a sequence of repo-relative directory prefixes (e.g.
    ``"scripts/agents/tools/"``) to restrict the walk. ``None`` walks all of
    ``root``.
    """
    if scopes is None:
        return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]
    files: list[Path] = []
    for scope in scopes:
        scope_dir = root / scope
        if not scope_dir.exists():
            continue
        for path in scope_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def line_has_allow_marker(
    source_lines: Iterable[str],
    start_lineno: int,
    end_lineno: int,
    marker: str,
) -> bool:
    """Return True if ``marker`` appears on any line in ``[start_lineno, end_lineno]``.

    Line numbers are 1-indexed (AST convention). ``end_lineno`` is inclusive.
    """
    lines = list(source_lines)
    start = max(start_lineno - 1, 0)
    end = min(max(end_lineno, start_lineno), len(lines))
    return any(marker in line for line in lines[start:end])


def file_first_line_has_marker(path: Path, marker: str) -> bool:
    """Return True when the first line of ``path`` contains ``marker``."""
    try:
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
    except (OSError, UnicodeDecodeError):
        return False
    return marker in first
