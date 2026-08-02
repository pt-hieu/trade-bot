"""Pre-commit hook: outer agent-wall sites must use derived constants, not
literals (SWI-306).

The 2026-05-10 silent-hang cascade root-caused to ``per_attempt_wall_s =
<PRIMARY_HOP_WALL_S>`` at ``sector_analysts.py:164`` matching the per-hop wall —
the outer ``asyncio.wait_for`` cancelled at the exact instant the inner
hop wall fired, starving ``RetryModel`` and ``FallbackModel`` of any
chance to roll over. The named constants in
``scripts/agents/model/wrappers.py`` (``OUTER_FALLBACK_STACK_WALL_S``,
``OUTER_DISABLE_FALLBACK_WALL_S``) are derived from the per-hop walls +
retry budget so they cannot collapse the failover stack again.

This hook flags any ``asyncio.wait_for(..., timeout=<LITERAL>)`` or
``run_agent_with_total_timeout(..., total_timeout_s=<LITERAL>)`` where
the timeout is a numeric literal in scope ``scripts/agents/``.

Allow-list per call site with ``# HOOK-ALLOW: outer-wall-helper
rationale=...``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from _common import line_has_allow_marker

SCAN_PREFIXES: tuple[str, ...] = ("scripts/agents/",)
HOOK_ALLOW_MARKER = "HOOK-ALLOW: outer-wall-helper"

_WAIT_FOR_NAMES: frozenset[str] = frozenset({"wait_for", "await_with_hop_unwrap"})
_TOTAL_TIMEOUT_KWARG_NAMES: frozenset[str] = frozenset({"total_timeout_s"})


def _is_wait_for_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in _WAIT_FOR_NAMES:
        return True
    return bool(isinstance(func, ast.Name) and func.id in _WAIT_FOR_NAMES)


def _is_run_total_timeout_call(call: ast.Call) -> bool:
    func = call.func
    name: str | None = None
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    return name == "run_agent_with_total_timeout"


def _literal_timeout_from_wait_for(call: ast.Call) -> ast.AST | None:
    # asyncio.wait_for(coro, timeout=N) or asyncio.wait_for(coro, N)
    for keyword in call.keywords:
        if keyword.arg == "timeout":
            if isinstance(keyword.value, ast.Constant) and isinstance(
                keyword.value.value, (int, float)
            ):
                return keyword.value
            return None
    if len(call.args) >= 2:
        arg = call.args[1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
            return arg
    return None


def _literal_total_timeout_kwarg(call: ast.Call) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg in _TOTAL_TIMEOUT_KWARG_NAMES and (
            isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, (int, float))
        ):
            return keyword.value
    return None


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except SyntaxError:
        return []
    source_lines = text.splitlines()
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        literal: ast.AST | None = None
        kind: str = ""
        if _is_wait_for_call(node):
            literal = _literal_timeout_from_wait_for(node)
            kind = "asyncio.wait_for(..., timeout=<literal>)"
        elif _is_run_total_timeout_call(node):
            literal = _literal_total_timeout_kwarg(node)
            kind = "run_agent_with_total_timeout(..., total_timeout_s=<literal>)"
        if literal is None:
            continue
        if line_has_allow_marker(source_lines, node.lineno - 3, node.lineno, HOOK_ALLOW_MARKER):
            continue
        violations.append(
            (
                node.lineno,
                f"{kind} uses a numeric literal — outer-wall sites must "
                "derive from OUTER_FALLBACK_STACK_WALL_S / "
                "OUTER_DISABLE_FALLBACK_WALL_S (SWI-306). Suppress per-call "
                f"with `# {HOOK_ALLOW_MARKER} rationale=...` when the site "
                "is an orchestration/compound wall.",
            )
        )
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        if not any(raw.startswith(prefix) for prefix in SCAN_PREFIXES):
            continue
        path = Path(raw)
        if path.suffix != ".py" or not path.is_file():
            continue
        for lineno, message in _scan_file(path):
            all_violations.append((raw, lineno, message))

    if all_violations:
        print(
            "Outer-wall helper lint failed (SWI-306). Literal timeouts on "
            "outer-wall sites starve the FallbackModel/RetryModel stack.",
            file=sys.stderr,
        )
        for relative_path, lineno, message in all_violations:
            print(f"  {relative_path}:{lineno}  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
