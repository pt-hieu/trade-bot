#!/usr/bin/env python3
"""Reject `except Exception: print(...)` silent-swallow patterns.

Any `except` clause matching `Exception` followed by `print(` within a
few non-blank lines (and no `raise` before the print) is rejected. Use
`shared.errors.report_caught(name, exc)` — it emits a traceback AND a
Logfire `task_exception` span so swallows stay visible.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Exclude the hook itself and the helper that documents the pattern.
_EXCLUDE = {
    "scripts/hooks/check_no_silent_swallow.py",
    "scripts/shared/errors.py",
}

_EXCEPT_RE = re.compile(r"^\s*except\s+[\w.]*Exception[\w\s,.()]*:\s*$")
_PRINT_RE = re.compile(r"^\s*print\s*\(")
_RAISE_RE = re.compile(r"^\s*raise\b")
_REPORT_RE = re.compile(r"report_caught\s*\(")


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, line_text) for offending except/print pairs."""
    lines = path.read_text(encoding="utf-8").splitlines()
    offenses: list[tuple[int, str]] = []

    for idx, line in enumerate(lines):
        if not _EXCEPT_RE.match(line):
            continue
        # Look at the next 3 non-blank lines
        seen_raise = False
        for look_ahead in range(1, 8):
            next_idx = idx + look_ahead
            if next_idx >= len(lines):
                break
            next_line = lines[next_idx]
            if not next_line.strip():
                continue
            if _RAISE_RE.match(next_line):
                seen_raise = True
                break
            if _REPORT_RE.search(next_line):
                # report_caught present — compliant even if a later print exists
                break
            if _PRINT_RE.match(next_line):
                if seen_raise:
                    break
                offenses.append((idx + 1, line.rstrip()))
                break
            # Not blank, not raise, not print, not report_caught — stop looking
            break

    return offenses


def main() -> int:
    files = [Path(arg) for arg in sys.argv[1:] if arg.endswith(".py")]
    total = 0
    for path in files:
        rel = str(path)
        if rel in _EXCLUDE or any(rel.endswith(skip) for skip in _EXCLUDE):
            continue
        offenses = scan_file(path)
        for line_no, line_text in offenses:
            print(
                f"{path}:{line_no}: silent-swallow — replace `print` with "
                f"`shared.errors.report_caught(name, exc)`: {line_text.strip()}"
            )
            total += 1

    if total:
        print(
            f"\nFound {total} silent-swallow site(s). Use "
            f"`shared.errors.report_caught` — see scripts/shared/errors.py "
            f"for rationale.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
