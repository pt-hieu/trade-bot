"""Pre-commit hook: prevent `[EMBED: ...]` placeholder tokens drifting back in.

2026-04-15 pipeline review (MON-2026-04-16-005): 5 unsubstituted
`[EMBED: X verbatim from pre-computed sections]` tokens shipped in the
published morning-brief.md (GOAL PROGRESS, CAPITAL STATUS, PERFORMANCE
CHECK, GLOBAL CONTEXT, ENTRY CRITERIA TODAY). Root cause was
`scripts/agents/configs/entry_strategist.yaml` carrying the tokens from
a pre-inject-verbatim architecture; the LLM faithfully emitted them.

Rule: fail any commit that adds a file under
`scripts/agents/configs/*.yaml` or `research/**/*.md` whose contents
contain the literal substring `[EMBED:`. Migrations under
`scripts/db/migrations/` are exempt (historical prompt text).
"""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN_SUBSTR = "[EMBED:"

SCAN_PREFIXES: tuple[str, ...] = (
    "scripts/agents/configs/",
    "research/",
)

# Scan only these suffixes to avoid blocking binary artifacts.
SCAN_SUFFIXES: tuple[str, ...] = (".yaml", ".yml", ".md")

# Migrations are historical — historical prompt text may contain the tokens.
EXEMPT_PREFIXES: tuple[str, ...] = ("scripts/db/migrations/",)


def _should_scan(relative: str) -> bool:
    if any(relative.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return False
    if not any(relative.startswith(prefix) for prefix in SCAN_PREFIXES):
        return False
    return any(relative.endswith(suffix) for suffix in SCAN_SUFFIXES)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text()
    except OSError:
        return []
    violations: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FORBIDDEN_SUBSTR in line:
            violations.append((lineno, line.strip()))
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        if not _should_scan(raw):
            continue
        path = Path(raw)
        if not path.is_file():
            continue
        for lineno, line in _scan_file(path):
            all_violations.append((raw, lineno, line))

    if all_violations:
        print(
            "[EMBED: ...] placeholder token lint failed. These tokens ship "
            "unsubstituted into the published brief (MON-2026-04-16-005).",
            file=sys.stderr,
        )
        for relative_path, lineno, line in all_violations:
            print(f"  {relative_path}:{lineno}  {line!r}", file=sys.stderr)
        print(
            "\nFix: remove the token from the yaml. Deterministic sections "
            "are concatenated by the Python renderer in "
            "scripts/agents/entry_strategist.py — the LLM no longer emits them.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
