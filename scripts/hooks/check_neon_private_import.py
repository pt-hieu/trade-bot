"""Pre-commit hook: block private imports from `shared.neon.insert_records._common`
outside `scripts/shared/neon/` and `tests/` (SWI-NN).

Why
---
The `_common` module hosts the asyncpg INSERT SQL constants + the row-builder
boundary. A caller reaching into private names from outside the package
bypasses the public `insert_alert_fire_recommendation` / `insert_daily_record` /
`insert_morning_recommendations` seams — exactly the boundary violation that
turned the alert→BUY closure path into a silent regression vector before
SWI-NN extracted `alert_fire.py`.

Run::

    uv run python scripts/hooks/check_neon_private_import.py <files...>
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_PRIVATE_MODULE_PREFIX = "shared.neon.insert_records._"
_ALLOWED_PREFIXES: tuple[str, ...] = (
    "scripts/shared/neon/",
    "tests/",
)


def _is_allowed_path(path: Path) -> bool:
    posix = path.as_posix()
    return any(posix.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def check_file(path: Path) -> list[str]:
    if _is_allowed_path(path):
        return []
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: syntax error: {e.msg}"]

    findings: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith(_PRIVATE_MODULE_PREFIX)
        ):
            findings.append(
                f"{path}:{node.lineno}: private import from {node.module!r} "
                "— use a public seam (e.g. "
                "`from shared.neon.insert_records import insert_alert_fire_recommendation`)"
            )
    return findings


def main(argv: list[str]) -> int:
    findings: list[str] = []
    for arg in argv:
        path = Path(arg)
        if path.suffix != ".py" or not path.exists():
            continue
        findings.extend(check_file(path))
    if findings:
        print("Neon private-import guard violations:")
        for f in findings:
            print(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
