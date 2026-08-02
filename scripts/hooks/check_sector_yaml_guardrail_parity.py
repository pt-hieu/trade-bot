"""Pre-commit hook: enforce shared-fragment parity across sector_*.yaml.

Bedrock guard for the 2026-05-04 sector ensemble incident: sector_technical
shipped without the tool_retry_guardrail fragment and silently drifted from
its tool-using siblings, leaving the agent's recovery hint surface
inconsistent. This hook fails the push when a tool-using sector config
forgets to ``{{include: tool_retry_guardrail}}``.

Scope: tool-using sector configs only. ``sector_technical.yaml`` is
inject-only by design (see Change 4, 2026-05-04 plan) and is explicitly
exempt — adding the include there would invite spurious tool calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Sector configs that MUST include the shared retry-guardrail fragment.
TOOL_USING_SECTOR_CONFIGS: frozenset[str] = frozenset(
    {
        "sector_news",
        "sector_enrichment",
        "sector_rotation",
    }
)

# Sector configs that are inject-only and intentionally skip the include.
# Listed explicitly so future maintainers see the exemption is deliberate.
# - sector_technical: technicals fully pre-injected per ticker briefing.
# - sector_aggregator: declares "No tools" (synthesizes 3 analyst reports).
INJECT_ONLY_SECTOR_CONFIGS: frozenset[str] = frozenset({"sector_technical", "sector_aggregator"})

REQUIRED_FRAGMENTS_FOR_TOOL_USING: frozenset[str] = frozenset({"tool_retry_guardrail"})

CONFIG_DIR = "scripts/agents/configs/"


def _agent_key(path: Path) -> str | None:
    name = path.name
    if not name.startswith("sector_") or not name.endswith((".yaml", ".yml")):
        return None
    return path.stem


def _scan(path: Path) -> list[str]:
    relative = str(path)
    if CONFIG_DIR not in relative:
        return []
    key = _agent_key(path)
    if key is None:
        return []
    if key in INJECT_ONLY_SECTOR_CONFIGS:
        return []
    if key not in TOOL_USING_SECTOR_CONFIGS:
        return []
    try:
        text = path.read_text()
    except OSError:
        return []
    violations: list[str] = []
    for fragment in sorted(REQUIRED_FRAGMENTS_FOR_TOOL_USING):
        directive = "{{include: " + fragment + "}}"
        if directive not in text:
            violations.append(
                f"{relative}: tool-using sector config missing "
                f"'{directive}' — sibling parity rule "
                "(scripts/hooks/check_sector_yaml_guardrail_parity.py)."
            )
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[str] = []
    for raw in argv[1:]:
        all_violations.extend(_scan(Path(raw)))
    if all_violations:
        print("Sector yaml fragment-parity drift detected:", file=sys.stderr)
        for message in all_violations:
            print(f"  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
