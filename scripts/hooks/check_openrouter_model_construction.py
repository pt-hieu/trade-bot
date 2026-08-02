"""Pre-commit hook: flag bare `OpenRouterModel(...)` construction outside the model package.

After 2026-04-22 the only supported way to get an OpenRouter-backed model is
`scripts/agents/model/::resolve_model` / `resolve_model_with_fallback`.
Those entry points wire the per-hop wall (`HopTimingModel`) and the
conditional retry (`RetryModel`), without which a silent provider hang
eats the outer phase budget (MON-2026-04-19-008).

Constructing `OpenRouterModel(...)` directly from other modules bypasses
both. This hook catches that drift at commit time. Whitelist is
`scripts/agents/model/` itself (it IS the factory). Anywhere else must
route through `resolve_model_with_fallback(config)`.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SCAN_PREFIXES: tuple[str, ...] = ("scripts/",)
_FACTORY_FILE = "scripts/agents/model"  # package after SWI-212 split
_TARGET_NAME = "OpenRouterModel"


def _is_target_call(node: ast.Call) -> bool:
    """True when `node` constructs OpenRouterModel by name."""
    func = node.func
    if isinstance(func, ast.Name) and func.id == _TARGET_NAME:
        return True
    return isinstance(func, ast.Attribute) and func.attr == _TARGET_NAME


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_target_call(node):
            violations.append(
                (
                    node.lineno,
                    f"{_TARGET_NAME}(...) constructed outside "
                    f"{_FACTORY_FILE}. Route through "
                    "`resolve_model_with_fallback(config)` so per-hop wall + "
                    "Retry wrapping apply.",
                )
            )
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        if not any(raw.startswith(prefix) for prefix in SCAN_PREFIXES):
            continue
        # Normalize so Windows-style paths don't silently slip past the whitelist.
        normalized = raw.replace("\\", "/")
        if normalized == f"{_FACTORY_FILE}.py" or normalized.startswith(f"{_FACTORY_FILE}/"):
            continue
        path = Path(raw)
        if path.suffix != ".py" or not path.is_file():
            continue
        for lineno, message in _scan_file(path):
            all_violations.append((raw, lineno, message))

    if all_violations:
        print(
            "Bare OpenRouterModel construction detected. Silent-hang-proofing "
            "requires HopTimingModel + RetryModel wrapping, which only "
            "`resolve_model_with_fallback(config)` wires correctly.",
            file=sys.stderr,
        )
        for relative_path, lineno, message in all_violations:
            print(f"  {relative_path}:{lineno}  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
