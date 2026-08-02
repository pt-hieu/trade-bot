"""Pre-commit hook: prevent TOOL RETRY GUARDRAIL drift from re-opening.

Rule: any yaml under `scripts/agents/configs/*.yaml` that contains the literal
string `## TOOL RETRY GUARDRAIL` must NOT re-inline the block — the canonical
body lives in `scripts/agents/configs/_fragments/tool_retry_guardrail.md` and
consumers pull it in via `{{include: tool_retry_guardrail}}`.

The fragment file itself IS expected to contain the header and is exempt.
"""

from __future__ import annotations

import sys
from pathlib import Path

FRAGMENT_HEADER = "## TOOL RETRY GUARDRAIL"
INCLUDE_DIRECTIVE = "{{include: tool_retry_guardrail}}"

EXEMPT_PATH_SUBSTR = "scripts/agents/configs/_fragments/"


def _scan(path: Path) -> list[str]:
    relative = str(path)
    if EXEMPT_PATH_SUBSTR in relative:
        return []
    if not relative.endswith((".yaml", ".yml")):
        return []
    if "scripts/agents/configs/" not in relative:
        return []
    try:
        text = path.read_text()
    except OSError:
        return []
    violations: list[str] = []
    if FRAGMENT_HEADER in text and INCLUDE_DIRECTIVE not in text:
        violations.append(
            f"{relative}: re-inlines '## TOOL RETRY GUARDRAIL' — replace with "
            "'{{include: tool_retry_guardrail}}' (see scripts/agents/configs/_fragments/)."
        )
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[str] = []
    for raw in argv[1:]:
        all_violations.extend(_scan(Path(raw)))
    if all_violations:
        print("TOOL RETRY GUARDRAIL drift detected:", file=sys.stderr)
        for message in all_violations:
            print(f"  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
