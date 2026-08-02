#!/usr/bin/env python3
"""Pre-commit hook: regress on `dict.get("key", default)` in DB-adjacent code.

CLAUDE.md rule: "None-safe dict access — `r.get("key") or default` (guards
both missing key and NULL column value)." Recurrence: `tool_get_insider` hit
this 3 times (commits 5a12024 / d98924c / 7b36035). Root cause is any DB
fetch-row consumer treating absent-key and NULL-value defaults the same way.

Scope: `scripts/agents/tools/**`, `scripts/shared/neon/**`,
`scripts/shared/api/**`. Pipeline scope (`scripts/pipeline/**`) is deferred
to a TypedDict-returns rework — see `issues/active/DEF-2026-04-22-001.yaml`.

Baseline grandfathers the ~353 current call sites; any growth fails. New call
sites must use either the `or` form or carry a `HOOK-ALLOW: none-safe-get`
marker on the same line (e.g. string concatenations where `""` is
semantically correct).

Regenerate after a genuine cleanup with
`uv run python scripts/hooks/check_none_safe_get.py --regenerate`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks._baseline import load_baseline, regress_diff, write_baseline  # noqa: E402
from hooks._common import iter_python_files  # noqa: E402

HOOK_ALLOW_MARKER = "HOOK-ALLOW: none-safe-get"

EXEMPT_FILES: frozenset[str] = frozenset()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASELINE_PATH = _REPO_ROOT / "scripts" / "hooks" / "data" / "none_safe_get_baseline.txt"

# `.get("key", <default>)` / `.get('key', <default>)` where <default> isn't `None`.
# Anchored on a key literal so we don't match `dict.get(key, default)` on a
# variable key (those are uncommon and the false-positive rate isn't worth
# the extra AST work here).
_PATTERN = re.compile(r"\.get\(\s*(?:\"[^\"\n]+\"|'[^'\n]+')\s*,\s*(?!None\b)[^)\n]+\)")

_SCOPES: tuple[str, ...] = (
    "scripts/agents/tools/",
    "scripts/shared/neon/",
    "scripts/shared/api/",
)


def _count_hits(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    count = 0
    for line in text.splitlines():
        if HOOK_ALLOW_MARKER in line:
            continue
        if _PATTERN.search(line):
            count += 1
    return count


def _collect_current() -> dict[str, int]:
    results: dict[str, int] = {}
    for path in iter_python_files(_REPO_ROOT, _SCOPES):
        rel = str(path.relative_to(_REPO_ROOT))
        if rel in EXEMPT_FILES:
            continue
        hits = _count_hits(path)
        if hits > 0:
            results[rel] = hits
    return results


def regenerate() -> int:
    current = _collect_current()
    _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_baseline(_BASELINE_PATH, current)
    print(
        f"Wrote {len(current)} files "
        f"({sum(current.values())} call sites) "
        f"to {_BASELINE_PATH.relative_to(_REPO_ROOT)}"
    )
    return 0


def main(argv: list[str]) -> int:
    if "--regenerate" in argv:
        return regenerate()
    baseline = load_baseline(_BASELINE_PATH)
    current = _collect_current()
    regressions = regress_diff(current, baseline)
    if regressions:
        print(
            "`.get(key, default)` grew in DB-adjacent scope. Use `r.get('key') or default` "
            "(CLAUDE.md 'None-safe dict access') or add `# HOOK-ALLOW: none-safe-get`.",
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
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
