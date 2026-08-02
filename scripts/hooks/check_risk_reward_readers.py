#!/usr/bin/env python3
"""Pre-push guard: forbid direct ``risk_reward`` reads outside SSOT whitelist.

Defect class history: 4 regressions of the same `or 0` / `, 0)` coercion
pattern (SWI-115, SWI-317, SWI-340, 2026-05-14). The fix is the SSOT helper
``read_rr()`` in ``shared/rules/exit_strategy.py`` — it returns None for
trailing exits and forces the caller to branch on the sentinel rather than
collapsing it into the literal 0.0.

This guard catches:
- ``foo.get("risk_reward")``
- ``foo.get("risk_reward", 0)`` / ``foo.get("risk_reward", 0.0)``
- ``foo.get("risk_reward") or 0`` / ``foo.get("risk_reward") or 0.0``

It does NOT catch direct indexing (``pick["risk_reward"]``) — that raises
``KeyError`` on missing key, which fails loudly rather than silently
coercing. Acceptable for SSOT-internal use.
"""

from __future__ import annotations

import pathlib
import re
import sys

# Catch ONLY the silent-coercion shapes — these are the recurrence vectors:
#   .get("risk_reward", 0)         ← default-arg coercion
#   .get("risk_reward", 0.0)
#   .get("risk_reward") or 0       ← truthy-fallback coercion
#   .get("risk_reward") or 0.0
# Bare ``.get("risk_reward")`` (no default, no `or`) is intentionally allowed:
# it returns None to the caller, which is the correct contract for trailing
# exits — the caller is then forced to branch. ``read_rr()`` is the preferred
# helper for new code; bare ``.get`` is grandfathered.
PATTERN = re.compile(
    r'\.get\(\s*["\']risk_reward["\']\s*,\s*[\d.]+\s*\)'
    r"|"
    r'\.get\(\s*["\']risk_reward["\']\s*\)\s*or\s+[\d.]+'
)

WHITELIST = {
    "scripts/shared/rules/exit_strategy.py",  # where read_rr() lives
    "scripts/hooks/check_risk_reward_readers.py",  # this file
}


def main() -> int:
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    hits: list[tuple[str, int, str]] = []
    for py in (repo_root / "scripts").rglob("*.py"):
        rel = str(py.relative_to(repo_root))
        if rel in WHITELIST:
            continue
        try:
            text = py.read_text()
        except Exception:
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                hits.append((rel, line_number, line.strip()))
    if hits:
        print("✗ risk_reward direct-read guard:")
        for rel, line_number, src in hits:
            print(f"  {rel}:{line_number}: {src}")
        print(
            "  Fix: import read_rr from shared.rules.exit_strategy and "
            "branch on None (trailing exits)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
