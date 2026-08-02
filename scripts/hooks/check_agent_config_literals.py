#!/usr/bin/env python3
"""Pre-commit hook: flag hardcoded agent-config literals.

CLAUDE.md agent config table pins `max_tokens=96000`, `request_limit=30`,
`output_retries=2` as project-wide defaults. Historically these drifted into
~20 `UsageLimits(request_limit=30)` literals scattered through the agents
package. Drifting the table value would leave those literals stale.

AST-scoped to known config constructors — `AgentConfig`, `UsageLimits`,
`ModelSettings` — so observability kwargs like
`observe_agent_output(max_tokens=96000, ...)` (logfire metadata, not an
agent-config literal) don't trip the check.

Rule: when a constructor above is called with `max_tokens`, `output_retries`,
or `request_limit` as a keyword whose value is an integer literal, flag it.
Attribute/Name references (`config.request_limit`, `DEFAULT_MAX_TOKENS`) are
fine — those route back to a single source of truth.

Escape hatches:
- `# HOOK-ALLOW: config-literal reason=<why>` anywhere inside the call's line
  range (useful for debug/repro scripts that need hand-tuned values).
- `EXEMPT_FILES` for the module that owns the defaults (`shared/agent_config`).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks._common import line_has_allow_marker  # noqa: E402

HOOK_ALLOW_MARKER = "HOOK-ALLOW: config-literal"

EXEMPT_FILES: frozenset[str] = frozenset(
    {
        "scripts/shared/agent_config.py",
    }
)

_CONFIG_CONSTRUCTORS: frozenset[str] = frozenset({"AgentConfig", "UsageLimits", "ModelSettings"})

_TRACKED_KWARGS: frozenset[str] = frozenset({"max_tokens", "output_retries", "request_limit"})


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _check_file(relative_path: str, path: Path) -> list[tuple[int, str, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    hits: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in _CONFIG_CONSTRUCTORS:
            continue
        for kw in node.keywords:
            if kw.arg not in _TRACKED_KWARGS:
                continue
            value = kw.value
            if isinstance(value, ast.Constant) and isinstance(value.value, int):
                end_lineno = node.end_lineno if node.end_lineno else node.lineno
                if line_has_allow_marker(source_lines, node.lineno, end_lineno, HOOK_ALLOW_MARKER):
                    continue
                hits.append((kw.lineno, name, f"{kw.arg}={value.value}"))
    return hits


def main(argv: list[str]) -> int:
    violations: list[tuple[str, int, str, str]] = []
    for raw in argv[1:]:
        relative_path = raw
        if relative_path in EXEMPT_FILES:
            continue
        path = Path(raw)
        if not path.is_file() or path.suffix != ".py":
            continue
        for lineno, ctor, detail in _check_file(relative_path, path):
            violations.append((relative_path, lineno, ctor, detail))
    if violations:
        print(
            "Hardcoded agent-config literals found. Route these through "
            "`shared.agent_config` (e.g. `build_usage_limits(config)`).",
            file=sys.stderr,
        )
        for rel, lineno, ctor, detail in violations:
            print(f"  {rel}:{lineno}  {ctor}({detail})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
