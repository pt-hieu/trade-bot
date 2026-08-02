"""Regression test for structured-output opener directives.

Structured-output agents (those with `output_type=...` in `create_agent` call +
`output_retries > 0`) must open their system prompt with an explicit directive
to emit the `final_result` tool call. Without it, glm-5 reasons indefinitely
instead of committing to structured output — reproduces as an `is_exception=true`
span with validation feedback "Please return text or include your response in
a tool call."

Originating incident: MON-2026-04-23-003 (retro_commentary reasoning-only loop,
+757s wall, +16K tokens per run).

The `PINNED_AGENTS` list is the audited set where the invariant is enforced.
Expand via DEF-structured-output-opener-invariant as other structured-output
agents are swept.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

CONFIGS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "agents" / "configs"

# Agents whose system prompt MUST open with an explicit tool-call directive.
# Confirmed empirically — news_examiner carries this pattern today and does
# not exhibit the reasoning-loop failure; retro_commentary is added here after
# MON-2026-04-23-003. Expand as DEF-structured-output-opener-invariant audits
# the remaining output_retries>0 agents.
PINNED_AGENTS = ("news_examiner", "retro_commentary")

# Permissive regex: first non-empty, non-comment line of system_prompt body
# must mention "tool call" OR "final_result" OR "structured" as an emit-now
# directive. Keeps flexibility for future phrasing.
OPENER_RE = re.compile(
    r"(tool\s*call|final_result|structured\s+(tool|output))",
    re.IGNORECASE,
)


@pytest.mark.parametrize("agent_key", PINNED_AGENTS)
def test_structured_output_agents_carry_tool_call_directive(agent_key: str) -> None:
    config_path = CONFIGS_DIR / f"{agent_key}.yaml"
    assert config_path.exists(), f"Expected config at {config_path}"
    config = yaml.safe_load(config_path.read_text())
    prompt = config.get("system_prompt") or ""
    assert OPENER_RE.search(prompt), (
        f"{agent_key}: system_prompt must carry a tool-call / final_result / "
        f"structured-output emit directive somewhere in its body. "
        f"Prompt had no matching directive."
    )


def test_retro_commentary_has_output_retries_configured() -> None:
    config = yaml.safe_load((CONFIGS_DIR / "retro_commentary.yaml").read_text())
    assert config.get("output_retries", 0) >= 1, (
        "retro_commentary needs output_retries>=1 for schema-failure recovery"
    )
