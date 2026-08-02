"""Pre-commit hook: empty structured outputs require explicit allowlist.

Phase 2 §2.3 / §2.9 — Pydantic's ``default_factory=dict`` (or ``=list``) on
agent output models accepts an empty payload at parse time. The
synthesis_holdings 2026-04-28 incident shipped because
``HoldingsTheses(theses=[])`` validated, even though the brief was
unusably blank.

This hook scans ``scripts/agents/**.py`` for ``default_factory=dict`` /
``default_factory=list`` that look like agent output fields. Any hit must
either have an accompanying ``min_length=`` constraint OR be tagged with
``# HOOK-ALLOW: empty-output-permitted`` on the same line / on the
preceding comment block — explaining why an empty default is the
correct contract.

Allowlist any file that's not an agent output model via a top-of-file
comment ``# HOOK-ALLOW-FILE: empty-output-permitted``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Pattern matches ``Field(... default_factory=dict ...)`` /
# ``Field(... default_factory=list ...)`` — only inside a Field()
# constructor (avoids false positives in docstrings/comments). Tolerates
# multi-line Field() declarations by checking the surrounding ±2 lines
# in the call below.
_DEFAULT_FACTORY = re.compile(
    r"default_factory\s*=\s*(dict|list)\b",
)
_FIELD_CALL = re.compile(r"\bField\s*\(")
_MIN_LENGTH_INLINE = re.compile(r"\bmin_length\s*=")
_ALLOW_INLINE = re.compile(r"#\s*HOOK-ALLOW:\s*empty-output-permitted")
_ALLOW_FILE = re.compile(r"#\s*HOOK-ALLOW-FILE:\s*empty-output-permitted")

# Only scan agent-output-shaped files. Models elsewhere (DB row dataclasses,
# config defaults) legitimately default to empty — no need to prove
# non-emptiness for those.
SCAN_PREFIXES: tuple[str, ...] = (
    "scripts/agents/",
    "scripts/agents/synthesis_writers.py",
    "scripts/agents/synthesis_picks_writer.py",
)

# Files that are NOT agent output models — config loaders, factories,
# etc. Keep small; prefer per-line allowlist for legitimate per-field
# exceptions.
ALLOW_FILES: frozenset[str] = frozenset(
    {
        "scripts/agents/agent_factory.py",
        "scripts/agents/agent_config.py",
    }
)


def _line_or_prev_has_allow(lines: list[str], idx: int) -> bool:
    """Look up to 8 lines back for an allowlist comment.

    Comment-block above the field declaration is the typical placement
    when the justification spans multiple lines.
    """
    start = max(0, idx - 8)
    return any(_ALLOW_INLINE.search(lines[i]) for i in range(start, idx + 1))


def _line_has_min_length_in_field(lines: list[str], idx: int) -> bool:
    """Look for ``min_length=`` within the same Field(...) call.

    Pydantic Field() may span multiple lines; scan ±2 lines around the
    match for the constraint token.
    """
    start = max(0, idx - 2)
    end = min(len(lines), idx + 3)
    return any(_MIN_LENGTH_INLINE.search(lines[i]) for i in range(start, end))


def _is_inside_field_call(lines: list[str], idx: int) -> bool:
    """True when the matched line is part of a ``Field(...)`` call.

    Filters out docstrings/comments/example pseudo-code that mention
    ``default_factory=dict`` without invoking ``Field(`` itself.
    """
    start = max(0, idx - 2)
    end = min(len(lines), idx + 3)
    return any(_FIELD_CALL.search(lines[i]) for i in range(start, end))


def main(argv: list[str]) -> int:
    violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        relative_path = raw
        path = Path(raw)
        if not relative_path.startswith(SCAN_PREFIXES):
            continue
        if relative_path in ALLOW_FILES:
            continue
        if path.suffix != ".py":
            continue
        if not path.is_file():
            continue

        text = path.read_text()
        if _ALLOW_FILE.search(text):
            continue

        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if not _DEFAULT_FACTORY.search(line):
                continue
            if not _is_inside_field_call(lines, idx):
                continue
            if _line_or_prev_has_allow(lines, idx):
                continue
            if _line_has_min_length_in_field(lines, idx):
                continue
            violations.append((relative_path, idx + 1, line.strip()))

    if violations:
        print(
            "default_factory=dict|list on an agent output model without "
            "min_length=... constraint OR a `# HOOK-ALLOW: "
            "empty-output-permitted` comment.\n"
            "Phase 2 §2.3 — empty structured outputs ship blank briefs. "
            "Add min_length, or allowlist with a justification.",
            file=sys.stderr,
        )
        for relative_path, line_number, content in violations:
            print(f"  {relative_path}:{line_number}  {content}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
