"""Shared baseline helpers for regression-style hooks.

Baseline format: one entry per line, ``<relative_path>:<count>`` sorted by path.
Blank lines and ``#`` comments are ignored.

Semantics:
- ``regress_diff(current, baseline)`` returns the paths where enforcement
  should fail: a path that's new to the tree with a positive count, OR a path
  whose count strictly exceeds the baseline.
- Paths present in the baseline but missing from ``current`` are silently
  dropped — deletion is always a win.

Caller writes baselines via ``write_baseline`` so on-disk files stay
deterministic (sorted, stable formatting).
"""

from __future__ import annotations

from pathlib import Path


def parse_baseline_text(text: str) -> dict[str, int]:
    """Parse baseline-format text into ``{path: count}``. Blank/comment lines skipped."""
    baseline: dict[str, int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        rel, count_str = line.rsplit(":", 1)
        rel = rel.strip()
        try:
            count = int(count_str.strip())
        except ValueError:
            continue
        if rel:
            baseline[rel] = count
    return baseline


def load_baseline(path: Path) -> dict[str, int]:
    """Read a baseline file. Missing file yields an empty dict."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    return parse_baseline_text(text)


def _format_baseline(data: dict[str, int]) -> str:
    lines = [f"{rel}:{count}" for rel, count in sorted(data.items()) if count > 0]
    return "\n".join(lines) + ("\n" if lines else "")


def write_baseline(path: Path, data: dict[str, int]) -> None:
    """Persist a baseline sorted by path. Skips the write when content is unchanged."""
    serialized = _format_baseline(data)
    try:
        existing = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = None
    if existing == serialized:
        return
    path.write_text(serialized, encoding="utf-8")


def regress_diff(current: dict[str, int], baseline: dict[str, int]) -> list[tuple[str, int, int]]:
    """Return (path, baseline_count, current_count) for regressions.

    A regression is any of:
    - ``path`` is not in ``baseline`` and ``current[path] > 0``
    - ``current[path] > baseline[path]``
    """
    regressions: list[tuple[str, int, int]] = []
    for rel, count in sorted(current.items()):
        if count <= 0:
            continue
        baseline_count = baseline.get(rel)
        if baseline_count is None:
            regressions.append((rel, 0, count))
        elif count > baseline_count:
            regressions.append((rel, baseline_count, count))
    return regressions
