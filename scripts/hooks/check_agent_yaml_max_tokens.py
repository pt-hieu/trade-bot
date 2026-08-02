#!/usr/bin/env python3
"""Pre-commit hook: every `scripts/agents/configs/*.yaml` pins `max_tokens=96000`.

CLAUDE.md agent config table pins `max_tokens=96000` as the universal cap.
Drift cost a real trading day (SWI-264 — `news_relevance.yaml` carried
`max_tokens=4096` and tripped two structured-output exceptions in the
2026-05-06 morning brief). This hook converts the recurring drift class into
a fail-fast invariant.

Escape hatch:
- `# HOOK-ALLOW: max-tokens-override reason=<why>` on the YAML line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HOOK_ALLOW_MARKER = "HOOK-ALLOW: max-tokens-override"

EXPECTED_MAX_TOKENS = 96000

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIGS_DIR = _REPO_ROOT / "scripts" / "agents" / "configs"

_MAX_TOKENS_RE = re.compile(r"^max_tokens:\s*([^\s#]+)", re.MULTILINE)


def _extract_max_tokens(source: str) -> tuple[str | None, bool]:
    match = _MAX_TOKENS_RE.search(source)
    if not match:
        return None, False
    line_start = source.rfind("\n", 0, match.start()) + 1
    line_end = source.find("\n", match.start())
    if line_end == -1:
        line_end = len(source)
    line = source[line_start:line_end]
    has_allow = HOOK_ALLOW_MARKER in line
    return match.group(1).strip(), has_allow


def main() -> int:
    if not _CONFIGS_DIR.exists():
        return 0
    yaml_files = sorted(
        p for p in _CONFIGS_DIR.glob("*.yaml") if p.is_file() and p.suffix in {".yaml", ".yml"}
    )
    violations: list[tuple[str, str]] = []
    for path in yaml_files:
        rel = f"scripts/agents/configs/{path.name}"
        max_tokens_value, has_allow = _extract_max_tokens(path.read_text(encoding="utf-8"))
        if has_allow:
            continue
        if max_tokens_value is None:
            continue
        if max_tokens_value != str(EXPECTED_MAX_TOKENS):
            violations.append((rel, max_tokens_value))
    if violations:
        print(
            f"Agent YAML `max_tokens` drift — CLAUDE.md pins {EXPECTED_MAX_TOKENS}. "
            "Add `# HOOK-ALLOW: max-tokens-override reason=<why>` only with explicit justification.",
            file=sys.stderr,
        )
        for rel, value in violations:
            print(f"  {rel}: max_tokens={value} (expected {EXPECTED_MAX_TOKENS})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
