"""Pre-commit hook: block negative tool AND domain-rule instructions in agent prompts.

CLAUDE.md rule: "Positive-only agent prompts — every instruction reads 'do X'.
LLMs follow the most specific instruction near the data they're looking at, so
positive phrasing near the payload wins."

## Two pattern classes

Phase 2 §2.9 extended the original tool-instruction hook with a second class:

1. **Tool-instruction negatives** (`DO NOT call`, `NEVER call`, `DO NOT SEARCH`) —
   originally swept in 2026-04-12 after the sector_news 30-round tool loop
   (commit 1a83827). The positive `call_tools([...])` example is what works;
   reactive prohibitions sit closer to the model's reasoning than the broker
   preamble above them, which inverted the intent.

2. **Domain-rule negatives** (`DO NOT recalculate`, `DO NOT override`,
   `DO NOT compute`, `DO NOT recommend BUY when`) — Phase 2 §2.2 / §2.6 found
   these phrases scattered across positions_*/synthesis_* configs. Same
   anti-pattern: the negative instruction primes the model to *think* about
   the forbidden action; positive framing ("Use the holdings P/L exactly as
   provided") outperforms.

Both classes share one hook so we have a single place to track positive-only
discipline and one allowlist mechanism.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Class 1 — TOOL-instruction negatives. Distinguishing tokens like
# `\bcall\b` / `\bretry\b` / `\bSEARCH\b` keep these narrow.
TOOL_INSTRUCTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bDO NOT call\b", re.IGNORECASE),
    re.compile(r"\bNEVER call\b", re.IGNORECASE),
    re.compile(r"\bDo not call\b", re.IGNORECASE),
    re.compile(r"\bDo not retry\b", re.IGNORECASE),
    re.compile(r"\bNEVER retry\b", re.IGNORECASE),
    re.compile(r"\bDO NOT SEARCH\b", re.IGNORECASE),
)

# Class 2 — DOMAIN-rule negatives. Each pattern targets a phrase the
# challenge round flagged as "rephrase positively". Add to the list,
# don't broaden — a too-wide negative pattern matches legitimate prose.
DOMAIN_RULE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bDO NOT recalculate\b", re.IGNORECASE),
    re.compile(r"\bDO NOT compute\b", re.IGNORECASE),
    re.compile(r"\bDO NOT override\s+pre-computed\b", re.IGNORECASE),
    re.compile(r"\bDO NOT use\s+total_cash\b", re.IGNORECASE),
    re.compile(r"\bDO NOT recommend\s+BUY\s+when\b", re.IGNORECASE),
    re.compile(r"\bDO NOT assume\s+positions\b", re.IGNORECASE),
)

NEGATIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    *TOOL_INSTRUCTION_PATTERNS,
    *DOMAIN_RULE_PATTERNS,
)

# Escape hatch for legitimate cases. Add full relative path + inline comment
# explaining why the match is OK. Every entry must be justified.
ALLOW_LIST: frozenset[str] = frozenset()

SCAN_PREFIXES: tuple[str, ...] = (
    "scripts/agents/configs/",
    "scripts/agents/tools/broker/",
)


def main(argv: list[str]) -> int:
    violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        relative_path = raw
        path = Path(raw)
        if not relative_path.startswith(SCAN_PREFIXES):
            continue
        if relative_path in ALLOW_LIST:
            continue
        if path.suffix not in {".yaml", ".py"}:
            continue
        if not path.is_file():
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            for pattern in NEGATIVE_PATTERNS:
                if pattern.search(line):
                    violations.append((relative_path, line_number, line.strip()))
                    break  # one hit per line is enough

    if violations:
        print(
            "Negative tool instructions found. Use positive framing instead "
            "(see CLAUDE.md: 'No negative tool instructions').",
            file=sys.stderr,
        )
        for relative_path, line_number, content in violations:
            print(f"  {relative_path}:{line_number}  {content}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
