#!/usr/bin/env python3
"""Pre-commit hook: cap new Python files under ``scripts/`` at 350 lines.

CLAUDE.md rule: "Max 300-350 lines per file. Split using modularisation."

Existing over-limit files are grandfathered via
``scripts/hooks/data/max_lines_baseline.txt``; they can grow no further and
must shrink to 350 to leave the baseline. New files failing the 350 cap on
their first commit block until split.

Escape hatches:
- ``# HOOK-ALLOW: max-lines reason=<why>`` on the very first line of the
  file — reserved for files where a single-file shape is load-bearing
  (generated code, test fixtures dumped by tooling, etc.).
- Regenerate the baseline after a legitimate split with
  ``uv run python scripts/hooks/check_max_file_lines.py --regenerate``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly via `python scripts/hooks/check_max_file_lines.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks._baseline import load_baseline, regress_diff, write_baseline  # noqa: E402
from hooks._common import iter_python_files  # noqa: E402

HOOK_ALLOW_MARKER = "HOOK-ALLOW: max-lines"

EXEMPT_FILES: frozenset[str] = frozenset(
    {
        # SWI-212 FIX 2: linear 5-stage pipeline (extract_top_picks single
        # 481-line function). Decomposition deferred to Stage[PicksContext]
        # follow-up ticket.
        "scripts/agents/picks.py",
        # SWI-212 honest exception: script entry-point with sys.path setup
        # + tests importing from the module directly. Splitting requires
        # a shim refactor + invocation change. Defer to follow-up ticket.
        "scripts/collect_review_data.py",
    }
)

MAX_LINES = 350

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_BASELINE_PATH = _REPO_ROOT / "scripts" / "hooks" / "data" / "max_lines_baseline.txt"


def _line_count_or_skip(path: Path) -> int:
    """Return the file's line count, or 0 when exempt via header marker or read error."""
    try:
        with path.open(encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, UnicodeDecodeError):
        return 0
    if lines and HOOK_ALLOW_MARKER in lines[0]:
        return 0
    return len(lines)


def _current_over_limit() -> dict[str, int]:
    results: dict[str, int] = {}
    for path in iter_python_files(_SCRIPTS_DIR):
        rel = str(path.relative_to(_REPO_ROOT))
        if rel in EXEMPT_FILES:
            continue
        line_count = _line_count_or_skip(path)
        if line_count > MAX_LINES:
            results[rel] = line_count
    return results


def regenerate() -> int:
    current = _current_over_limit()
    _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_baseline(_BASELINE_PATH, current)
    print(f"Wrote {len(current)} over-limit files to {_BASELINE_PATH.relative_to(_REPO_ROOT)}")
    return 0


def main(argv: list[str]) -> int:
    if "--regenerate" in argv:
        return regenerate()
    baseline = load_baseline(_BASELINE_PATH)
    current = _current_over_limit()
    regressions = regress_diff(current, baseline)
    if regressions:
        print(
            f"Python files exceeding {MAX_LINES} lines (CLAUDE.md 'Max 300-350 lines per file'):",
            file=sys.stderr,
        )
        for rel, base_count, curr_count in regressions:
            if base_count == 0:
                print(
                    f"  {rel}: {curr_count} lines (new over-limit file)",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  {rel}: {curr_count} lines (baseline {base_count})",
                    file=sys.stderr,
                )
        print(
            "Split via modularisation. If the split is genuine, rerun with "
            "`uv run python scripts/hooks/check_max_file_lines.py --regenerate` "
            "and commit the refreshed baseline.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
