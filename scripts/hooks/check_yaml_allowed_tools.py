"""Pre-push hook — validate every YAML's `allowed_tools:` entries against
the live broker registry (SWI-180).

Catches three drift classes:
  1. an ``allowed_tools:`` entry naming a tool that doesn't exist in the
     `TOOL_CATALOG` (typo / removed tool)
  2. an ``allowed_tools:`` entry without an adjacent ``# rationale: SWI-...``
     comment (rationale-required-on-add convention)
  3. a YAML referencing a tool name in its ``system_prompt`` body that is
     NEITHER on its allowed_tools nor reachable via ``unlock_tool`` (legacy
     `call_tools` exemplar drift)

Exits 0 on clean, 1 on any drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Make scripts importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force domain registration so TOOL_CATALOG is populated.
import agents.tools.broker.domains  # noqa: E402, F401
from agents.tools.broker.registry import TOOL_CATALOG  # noqa: E402

CONFIGS_DIR = Path(__file__).parent.parent / "agents" / "configs"

ALLOWED_TOOLS_LINE = re.compile(r"^\s*-\s*([a-z_]+\.[a-z_]+)\s*(?:#.*)?$")
RATIONALE_RE = re.compile(r"#\s*rationale:\s*SWI-\d+")
DOTTED_TOOL_REF = re.compile(r"`?([a-z_]+\.[a-z_]+)`?")


def _split_yaml_sections(text: str) -> tuple[list[str], str]:
    """Return (allowed_tools_lines, rest-of-document-text)."""
    in_allowed = False
    allowed_lines: list[str] = []
    rest_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("allowed_tools:"):
            in_allowed = True
            continue
        if in_allowed:
            if line.startswith(" ") or line.startswith("\t"):
                allowed_lines.append(line)
                continue
            in_allowed = False
        rest_lines.append(line)
    return allowed_lines, "\n".join(rest_lines)


def main() -> int:
    drifts: list[str] = []
    catalog_names = set(TOOL_CATALOG)

    for yaml_path in sorted(CONFIGS_DIR.glob("*.yaml")):
        text = yaml_path.read_text(encoding="utf-8")
        if "allowed_tools:" not in text:
            continue  # pre-SWI-180 YAML or fragment

        allowed_lines, body = _split_yaml_sections(text)
        agent_allowed: set[str] = set()
        for line in allowed_lines:
            match = ALLOWED_TOOLS_LINE.match(line)
            if not match:
                continue
            tool_name = match.group(1)
            agent_allowed.add(tool_name)

            if tool_name not in catalog_names:
                drifts.append(
                    f"{yaml_path.name}: allowed_tools entry '{tool_name}' is "
                    "not registered in TOOL_CATALOG"
                )
            if not RATIONALE_RE.search(line):
                drifts.append(
                    f"{yaml_path.name}: allowed_tools entry '{tool_name}' "
                    "is missing an adjacent `# rationale: SWI-NN — ...` "
                    "comment"
                )

        # Stale tool references in body — find any dotted name that exists
        # in TOOL_CATALOG but is NOT on the agent's allowed_tools.
        for line_no, body_line in enumerate(body.splitlines(), start=1):
            if "# " in body_line and "rationale:" in body_line:
                continue
            for token_match in DOTTED_TOOL_REF.finditer(body_line):
                token = token_match.group(1)
                if token not in catalog_names:
                    continue
                if token in agent_allowed:
                    continue
                drifts.append(
                    f"{yaml_path.name}:body~L{line_no}: references "
                    f"'{token}' but it is not on allowed_tools (use "
                    f"unlock_tool or add to allowed_tools with rationale)"
                )

    if drifts:
        print("YAML allowed_tools drift detected (SWI-180 pre-push hook):", file=sys.stderr)
        for drift in drifts:
            print(f"  {drift}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
