"""Pre-commit hook: flag risky bare `_get_provider()` calls.

After the 2026-04-14 sector_aggregator silent-hang incident, the
`_get_provider` default was flipped from 300s → 60s in
`scripts/agents/model.py`. The incident root cause was a `disable_fallback`
agent inheriting the 300s default and then hanging for the full phase wall.

This hook prevents recurrence by flagging:
  1. Any new function/closure that calls `_get_provider(timeout=N)` with
     N >= 120. Such opt-ins must either (a) be justified with an inline
     comment `# HOOK-ALLOW: long-timeout reason=...` OR (b) be removed.
  2. Explicitly enforces that the default at `_get_provider(timeout=...)`
     declaration in `model.py` stays at 60.0 — raise the default here and
     this hook fails.

Scope: only AST-scans `scripts/agents/` `.py` files (and anything that
imports `_get_provider`).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SCAN_PREFIXES: tuple[str, ...] = ("scripts/agents/",)
MAX_BARE_TIMEOUT_SECONDS = 120.0
HOOK_ALLOW_MARKER = "HOOK-ALLOW: long-timeout"
UNGUARDED_AGENT_RUN_MARKER = "HOOK-ALLOW: unguarded-agent-run"
_MODEL_FILE = "scripts/agents/model.py"


def _get_timeout_kwarg(call: ast.Call) -> float | None:
    """Return the `timeout=` kwarg value if it's a numeric literal, else None."""
    for keyword in call.keywords:
        if keyword.arg != "timeout":
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(
            keyword.value.value, (int, float)
        ):
            return float(keyword.value.value)
        # Non-literal (variable, expression) — skip; we only lint literals.
        return None
    return None


def _line_has_marker(source_lines: list[str], lineno: int, marker: str) -> bool:
    """Return True if `lineno` (1-based) or the three lines above it
    contain `marker`."""
    for offset in (0, 1, 2, 3):
        index = lineno - 1 - offset
        if 0 <= index < len(source_lines) and marker in source_lines[index]:
            return True
    return False


def _line_has_allow_marker(source_lines: list[str], lineno: int) -> bool:
    return _line_has_marker(source_lines, lineno, HOOK_ALLOW_MARKER)


def _check_default_unchanged(tree: ast.AST, source_lines: list[str]) -> list[tuple[int, str]]:
    """Ensure _get_provider's default timeout stays at 60.0 in model.py."""
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "_get_provider":
            continue
        defaults = node.args.defaults
        args = node.args.args
        # Pair defaults with their args (defaults bind to the tail of args).
        offset = len(args) - len(defaults)
        for idx, default in enumerate(defaults):
            arg_name = args[offset + idx].arg
            if arg_name != "timeout":
                continue
            if not (isinstance(default, ast.Constant) and isinstance(default.value, (int, float))):
                violations.append(
                    (
                        node.lineno,
                        f"_get_provider(timeout=...) default must be a numeric "
                        f"literal, got {ast.dump(default)}",
                    )
                )
                continue
            if float(default.value) != 60.0:
                violations.append(
                    (
                        node.lineno,
                        f"_get_provider(timeout={default.value}) default must "
                        f"remain 60.0 to avoid silent-hang regressions "
                        f"(2026-04-14 incident). Raise per-call with "
                        f"'# {HOOK_ALLOW_MARKER} reason=...' instead.",
                    )
                )
    return violations


_NON_AGENT_RUN_RECEIVERS: frozenset[str] = frozenset({"asyncio", "loop", "subprocess", "trio"})


def _is_agent_run_call(node: ast.Call) -> bool:
    """Match `<receiver>.run(...)` where the receiver is an agent-like name.

    Narrowed from a blanket `.run` match to avoid flagging `asyncio.run(...)`,
    `loop.run_until_complete(...)` style calls, and other non-Agent methods
    that happen to share the name.
    """
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "run":
        return False
    receiver = func.value
    if isinstance(receiver, ast.Name) and receiver.id in _NON_AGENT_RUN_RECEIVERS:
        return False
    if isinstance(receiver, ast.Attribute) and receiver.attr in _NON_AGENT_RUN_RECEIVERS:
        return False
    # Require the receiver expression to mention "agent" somewhere — covers
    # `agent`, `batch_agent`, `cross_agent`, `self.agent`, etc. without
    # matching unrelated `.run(` methods on arbitrary objects.
    receiver_source = ast.dump(receiver)
    return "agent" in receiver_source.lower()


_TOTAL_TIMEOUT_WRAPPERS: frozenset[str] = frozenset(
    {"wait_for", "run_agent_with_total_timeout", "await_with_hop_unwrap"}
)


def _check_unguarded_agent_runs(tree: ast.AST, source_lines: list[str]) -> list[tuple[int, str]]:
    """Every `agent.run(...)` site must sit inside `asyncio.wait_for(...)` or
    `run_agent_with_total_timeout(...)`.

    Pre-2026-04-21 this was gated on `disable_fallback: true`. MON-2026-04-19-008
    found 13 sibling agents producing silent 75-180s hangs without the guard;
    broadening the check to every agent closes that class.
    """
    violations: list[tuple[int, str]] = []
    parent_map: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[id(child)] = parent

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_agent_run_call(node):
            continue
        # Walk ancestors looking for an accepted total-timeout wrapper.
        guarded = False
        current: ast.AST | None = node
        while current is not None:
            outer = parent_map.get(id(current))
            if isinstance(outer, ast.Call):
                outer_func = outer.func
                wrapper_name: str | None = None
                if isinstance(outer_func, ast.Attribute):
                    wrapper_name = outer_func.attr
                elif isinstance(outer_func, ast.Name):
                    wrapper_name = outer_func.id
                if wrapper_name in _TOTAL_TIMEOUT_WRAPPERS:
                    guarded = True
                    break
            current = outer
        if guarded:
            continue
        if _line_has_marker(source_lines, node.lineno, UNGUARDED_AGENT_RUN_MARKER):
            continue
        violations.append(
            (
                node.lineno,
                "agent.run() must be wrapped in asyncio.wait_for(...) or "
                "run_agent_with_total_timeout(...). Silent provider hangs "
                "(MON-2026-04-19-008) otherwise eat the outer phase budget — "
                "13 sibling agents were hanging 75-180s without this guard. "
                f"Suppress with `# {UNGUARDED_AGENT_RUN_MARKER} reason=...` "
                "only when the call is already inside a total-timeout scope.",
            )
        )
    return violations


def _scan_file(path: Path, relative: str) -> list[tuple[int, str]]:
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except SyntaxError:
        return []
    source_lines = text.splitlines()

    violations: list[tuple[int, str]] = []

    # Enforce the 60.0 default in the model.py declaration itself.
    if relative == _MODEL_FILE:
        violations.extend(_check_default_unchanged(tree, source_lines))

    violations.extend(_check_unguarded_agent_runs(tree, source_lines))

    # Flag long-timeout call sites elsewhere.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id == "_get_provider"
            or isinstance(func, ast.Attribute)
            and func.attr == "_get_provider"
        ):
            target = True
        else:
            target = False
        if not target:
            continue

        timeout = _get_timeout_kwarg(node)
        if timeout is None:
            continue
        if timeout < MAX_BARE_TIMEOUT_SECONDS:
            continue
        if _line_has_allow_marker(source_lines, node.lineno):
            continue
        violations.append(
            (
                node.lineno,
                f"_get_provider(timeout={timeout}) exceeds {MAX_BARE_TIMEOUT_SECONDS}s "
                f"without `# {HOOK_ALLOW_MARKER} reason=...` justification",
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
        for lineno, message in _scan_file(path, raw):
            all_violations.append((raw, lineno, message))

    if all_violations:
        print(
            "Provider timeout lint failed. The 2026-04-14 sector_aggregator "
            "silent-hang incident was caused by disable_fallback agents "
            "inheriting a 300s _get_provider() default. Keep the default at "
            f"60s and justify any per-call override >= {MAX_BARE_TIMEOUT_SECONDS}s.",
            file=sys.stderr,
        )
        for relative_path, lineno, message in all_violations:
            print(f"  {relative_path}:{lineno}  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
