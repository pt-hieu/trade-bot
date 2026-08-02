"""Pre-commit hook: every `emit_silent_provider_hang_span(...)` call must
pass `downstream_provider=`.

The producer wire to `_silent_provider_hang_providers` (consumed by
`maybe_emit_silent_hang_alert` and the session-side dynamic provider
exclusion list) fires off the `downstream_provider` slug — the real
OpenRouter serving upstream. The `provider` kwarg (model author) is still
required by the function signature, but Python enforces that one; the
`downstream_provider` kwarg has a default, so without this hook an emit
site could silently omit it and sever the exclusion wire. Keying the
exclusion set on a downstream upstream rather than the author is what
stops a provider-class hang from taking the whole fleet offline
(2026-05-15 incident).

AST-based — handles both `emit_silent_provider_hang_span(...)` (direct
call) and `observability.emit_silent_provider_hang_span(...)` (attribute
call) forms, including `import ... as` aliases via best-effort scan of
the file's import statements.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

TARGET_FUNCTION_NAME = "emit_silent_provider_hang_span"


def _import_aliases(tree: ast.AST) -> set[str]:
    """Return any local names bound to `emit_silent_provider_hang_span`."""
    aliases: set[str] = {TARGET_FUNCTION_NAME}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == TARGET_FUNCTION_NAME:
                    aliases.add(alias.asname or alias.name)
    return aliases


def _is_target_call(node: ast.Call, aliases: set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id in aliases:
        return True
    return bool(isinstance(func, ast.Attribute) and func.attr == TARGET_FUNCTION_NAME)


def _has_provider_kwarg(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg == "downstream_provider":
            return True
        # `**extra` style spread — opaque; accept conservatively to avoid
        # false positives, but flag absence of explicit downstream_provider=
        # where no spread exists.
        if keyword.arg is None:
            return True
    return False


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except SyntaxError:
        return []
    aliases = _import_aliases(tree)
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_target_call(node, aliases):
            continue
        if _has_provider_kwarg(node):
            continue
        violations.append(
            (
                node.lineno,
                f"{TARGET_FUNCTION_NAME}(...) must pass `downstream_provider=` "
                "explicitly — it feeds the session provider-exclusion set. "
                "Pass `downstream_provider_from_timeout(exc)`; it returns None "
                "when no upstream is identifiable, which is the safe default.",
            )
        )
    return violations


def main(argv: list[str]) -> int:
    all_violations: list[tuple[str, int, str]] = []
    for raw in argv[1:]:
        path = Path(raw)
        if path.suffix != ".py" or not path.is_file():
            continue
        for lineno, message in _scan_file(path):
            all_violations.append((raw, lineno, message))

    if all_violations:
        print(
            "Silent-hang producer wire lint failed. "
            "`emit_silent_provider_hang_span` requires `downstream_provider=`.",
            file=sys.stderr,
        )
        for relative_path, lineno, message in all_violations:
            print(f"  {relative_path}:{lineno}  {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
