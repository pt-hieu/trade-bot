"""Pre-commit hook: try/except blocks guarding ``asyncio.wait_for(...)`` or
``run_agent_with_total_timeout(...)`` must explicitly handle ``TimeoutError``
or use ``except* HopTimeout`` BEFORE any bare ``except Exception`` (SWI-306).

A generic ``except Exception:`` chain that catches a HopTimeout swallows
the typed-exception fix and starves the silent-hang alerter of the
provider slug — the same defect class as the producer-wire severance the
SWI-306 ticket repaired.

The hook fires when ALL of these are true at one ``try`` block:
  1. Try body awaits ``wait_for(...)`` or ``run_agent_with_total_timeout(...)``.
  2. None of the ``except`` clauses (or ``except*`` clauses) name
     ``TimeoutError``, ``HopTimeout``, or a tuple containing either.
  3. At least one ``except Exception`` (or bare ``except:``) handler exists.

Suppress per-site with ``# HOOK-ALLOW: silent-swallow rationale=...``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from _common import line_has_allow_marker

SCAN_PREFIXES: tuple[str, ...] = ("scripts/agents/", "scripts/pipeline/")
HOOK_ALLOW_MARKER = "HOOK-ALLOW: silent-swallow"
_GUARDED_NAMES: frozenset[str] = frozenset(
    {"wait_for", "run_agent_with_total_timeout", "await_with_hop_unwrap"}
)
_TYPED_NAMES: frozenset[str] = frozenset({"TimeoutError", "HopTimeout"})


def _is_guarded_call(call: ast.Call) -> bool:
    func = call.func
    name: str | None = None
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    return name in _GUARDED_NAMES


def _try_body_awaits_guarded(try_node: ast.Try | ast.TryStar) -> bool:
    for inner in ast.walk(ast.Module(body=try_node.body, type_ignores=[])):
        if isinstance(inner, ast.Call) and _is_guarded_call(inner):
            return True
    return False


def _handler_handles_timeout(handler: ast.ExceptHandler) -> bool:
    """Return True if this except clause catches TimeoutError or HopTimeout."""
    exc_type = handler.type
    if exc_type is None:
        return False
    if isinstance(exc_type, ast.Name) and exc_type.id in _TYPED_NAMES:
        return True
    if isinstance(exc_type, ast.Tuple):
        for el in exc_type.elts:
            if isinstance(el, ast.Name) and el.id in _TYPED_NAMES:
                return True
            if isinstance(el, ast.Attribute) and el.attr in _TYPED_NAMES:
                return True
    return bool(isinstance(exc_type, ast.Attribute) and exc_type.attr in _TYPED_NAMES)


def _handler_is_generic(handler: ast.ExceptHandler) -> bool:
    exc_type = handler.type
    if exc_type is None:
        return True
    return bool(isinstance(exc_type, ast.Name) and exc_type.id in {"Exception", "BaseException"})


def _check_try(try_node: ast.Try | ast.TryStar) -> bool:
    """Return True if this try block violates the rule."""
    if not _try_body_awaits_guarded(try_node):
        return False
    has_typed = any(_handler_handles_timeout(h) for h in try_node.handlers)
    has_generic = any(_handler_is_generic(h) for h in try_node.handlers)
    return has_generic and not has_typed


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except SyntaxError:
        return []
    source_lines = text.splitlines()
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Try, ast.TryStar)):
            continue
        if not _check_try(node):
            continue
        if line_has_allow_marker(source_lines, node.lineno - 3, node.lineno, HOOK_ALLOW_MARKER):
            continue
        violations.append(
            (
                node.lineno,
                "try-block guards asyncio.wait_for / run_agent_with_total_timeout "
                "but only has a bare `except Exception` — add an explicit "
                "`except TimeoutError` (or `except* HopTimeout`) BEFORE the generic "
                f"handler. Suppress with `# {HOOK_ALLOW_MARKER} rationale=...`.",
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
            "Silent-swallow lint failed (SWI-306). Bare `except Exception` "
            "swallows HopTimeout and severs the silent-hang producer wire.",
            file=sys.stderr,
        )
        for relative_path, lineno, message in all_violations:
            print(f"  {relative_path}:{lineno}  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
