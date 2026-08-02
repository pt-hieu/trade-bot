"""Pre-commit hook: flag unguarded `await agent.run(...)` calls.

After the 2026-04-14 sector_aggregator silent-hang incident, every
`agent.run(...)` in pipeline code MUST be wrapped in
`asyncio.wait_for(..., timeout=...)` so a first-byte hang surfaces as a
TimeoutError the caller can handle instead of waiting out the full phase
wall.

This hook AST-scans `scripts/agents/` and `scripts/pipeline/` and flags
any `await <expr>.run(...)` whose `<expr>` looks like an agent (name
contains "agent") and whose enclosing call is NOT
`asyncio.wait_for(...)`.

Scope filter: files under `scripts/agents/` and `scripts/pipeline/`.
Unit tests live under `tests/` which is already excluded by the scope
filter — tests intentionally call unguarded `.run()` to assert errors.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SCAN_PREFIXES: tuple[str, ...] = (
    "scripts/agents/",
    "scripts/pipeline/",
)

HOOK_ALLOW_MARKER = "HOOK-ALLOW: unguarded-agent-run"


def _is_agent_run_call(node: ast.Call) -> bool:
    """Return True if the call is `<something>.run(...)` where `something`
    looks agent-ish (name contains "agent")."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != "run":
        return False
    value = func.value
    if isinstance(value, ast.Name):
        return "agent" in value.id.lower()
    if isinstance(value, ast.Attribute):
        return "agent" in value.attr.lower()
    # e.g., create_agent(...).run(...) — always counts.
    return isinstance(value, ast.Call)


def _line_has_allow_marker(source_lines: list[str], lineno: int) -> bool:
    """Check if `lineno` (1-based) or one of the three lines above it
    contains the HOOK_ALLOW_MARKER string. Widened to 3 lines so multi-line
    comment blocks above the call site still satisfy the marker check."""
    for offset in (0, 1, 2, 3):
        index = lineno - 1 - offset
        if 0 <= index < len(source_lines) and HOOK_ALLOW_MARKER in source_lines[index]:
            return True
    return False


class _UnguardedRunFinder(ast.NodeVisitor):
    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.violations: list[tuple[int, str]] = []
        self._wait_for_stack: int = 0

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        entered_wait_for = False
        if self._is_wait_for(node):
            self._wait_for_stack += 1
            entered_wait_for = True

        if (
            _is_agent_run_call(node)
            and self._wait_for_stack == 0
            and not _line_has_allow_marker(self.source_lines, node.lineno)
        ):
            target = self._describe_target(node)
            self.violations.append(
                (
                    node.lineno,
                    f"await {target}.run(...) must be wrapped in "
                    f"asyncio.wait_for(timeout=...) — add wrapping or "
                    f"mark with `# {HOOK_ALLOW_MARKER} reason=...`",
                )
            )

        self.generic_visit(node)

        if entered_wait_for:
            self._wait_for_stack -= 1

    @staticmethod
    def _is_wait_for(call: ast.Call) -> bool:
        func = call.func
        guarded = {"wait_for", "await_with_hop_unwrap", "run_agent_with_total_timeout"}
        if isinstance(func, ast.Attribute) and func.attr in guarded:
            return True
        return isinstance(func, ast.Name) and func.id in guarded

    @staticmethod
    def _describe_target(call: ast.Call) -> str:
        func = call.func
        if isinstance(func, ast.Attribute):
            value = func.value
            if isinstance(value, ast.Name):
                return value.id
            if isinstance(value, ast.Attribute):
                return value.attr
            if isinstance(value, ast.Call):
                return "<call>"
        return "<agent>"


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except SyntaxError:
        return []
    source_lines = text.splitlines()
    finder = _UnguardedRunFinder(source_lines)
    finder.visit(tree)
    return finder.violations


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
            "Unguarded `agent.run(...)` calls found. The 2026-04-14 "
            "silent-hang incident showed that any disable_fallback agent "
            "without an asyncio.wait_for wrapper can eat the full phase "
            "wall. Wrap new calls or mark with the allow comment.",
            file=sys.stderr,
        )
        for relative_path, lineno, message in all_violations:
            print(f"  {relative_path}:{lineno}  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
