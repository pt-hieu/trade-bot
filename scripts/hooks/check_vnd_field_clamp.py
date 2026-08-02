#!/usr/bin/env python3
"""Pre-commit hook: every Pydantic ``*_vnd`` int/float field must clamp.

SWI-184 — generalizes the unit-shift-recovering ``normalize_vnd_price``
clamp to every Pydantic ``BaseModel`` field whose name ends ``_vnd`` and
whose resolved type is one of ``int``, ``int | None``, ``Optional[int]``,
``float``, or ``Annotated[int, ...]``. Each such field must be guarded
either by:

  * ``Field(ge=1000, ...)`` — value-floor clamp, OR
  * a ``model_validator`` referencing ``normalize_vnd_price`` — recovery
    clamp.

Function parameters and TypedDict members are out of scope: the defect
the clamp guards is LLM-emitted Pydantic field values, not internal
plumbing types.

Escape hatch: ``# noqa: vnd-clamp`` on the field line.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks._common import iter_python_files, line_has_allow_marker  # noqa: E402

NOQA_MARKER = "noqa: vnd-clamp"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_DIR = _REPO_ROOT / "scripts" / "agents"

_INT_TYPES: frozenset[str] = frozenset({"int", "float"})


def _annotation_is_int_vnd(annotation: ast.AST | None) -> bool:
    """Return True when annotation resolves to int/float (with optional None)."""
    if annotation is None:
        return False
    if isinstance(annotation, ast.Name):
        return annotation.id in _INT_TYPES
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        # ``int | None`` style.
        return _annotation_is_int_vnd(annotation.left) or _annotation_is_int_vnd(annotation.right)
    if isinstance(annotation, ast.Subscript):
        # ``Optional[int]`` / ``Annotated[int, ...]``.
        value = annotation.value
        if isinstance(value, ast.Name) and value.id in {"Optional", "Annotated"}:
            slice_node = annotation.slice
            if isinstance(slice_node, ast.Tuple):
                return any(_annotation_is_int_vnd(elt) for elt in slice_node.elts)
            return _annotation_is_int_vnd(slice_node)
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return False
    return False


def _field_call_has_ge_floor(value: ast.AST | None) -> bool:
    """Return True when ``value`` is a Field(...) call with ge >= 1000."""
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    if not (isinstance(func, ast.Name) and func.id == "Field"):
        return False
    for kw in value.keywords:
        if kw.arg == "ge" and isinstance(kw.value, ast.Constant):
            literal = kw.value.value
            if isinstance(literal, (int, float)) and not isinstance(literal, bool):
                return literal >= 1000
            return False
    return False


_CLAMP_NAMES: frozenset[str] = frozenset({"normalize_vnd_price", "clamp_vnd_field"})


def _decorator_name(deco: ast.expr) -> str | None:
    target = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _function_body_calls_clamp(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True when the function body invokes a clamp routine.

    Scoped to the function body — a stray module-level reference (docstring,
    import, unrelated helper) does not satisfy the guard.
    """
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            func_node = node.func
            if isinstance(func_node, ast.Name) and func_node.id in _CLAMP_NAMES:
                return True
            if isinstance(func_node, ast.Attribute) and func_node.attr in _CLAMP_NAMES:
                return True
    return False


def _class_validator_calls_clamp(cls: ast.ClassDef, helper_funcs: set[str]) -> bool:
    """Return True when any ``@model_validator`` method invokes a clamp routine.

    A validator may delegate to a module-level helper (e.g.
    ``_normalize_belief_probabilities``) — if the helper itself calls a clamp
    routine and the validator calls the helper, treat as guarded.
    """
    for stmt in cls.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_decorator_name(d) == "model_validator" for d in stmt.decorator_list):
            continue
        if _function_body_calls_clamp(stmt):
            return True
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                func_node = node.func
                if isinstance(func_node, ast.Name) and func_node.id in helper_funcs:
                    return True
    return False


def _collect_helpers_calling_clamp(tree: ast.Module) -> set[str]:
    """Return module-level function names whose body calls a clamp routine."""
    helpers: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _function_body_calls_clamp(
            node
        ):
            helpers.add(node.name)
    return helpers


def _is_pydantic_basemodel(cls: ast.ClassDef) -> bool:
    """Heuristic: class inherits from ``BaseModel`` (direct or qualified).

    Catches ``class X(BaseModel)`` and ``class X(pydantic.BaseModel)``.
    Misses subclasses of project-defined intermediate bases — those need
    a ``# noqa: vnd-clamp`` opt-in or registration here.
    """
    for base in cls.bases:
        if isinstance(base, ast.Name) and base.id == "BaseModel":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
            return True
    return False


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return [(lineno, field_name)] for unguarded *_vnd fields in this file."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    violations: list[tuple[int, str]] = []
    helper_funcs = _collect_helpers_calling_clamp(tree)

    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        if not _is_pydantic_basemodel(cls):
            continue
        class_has_validator = _class_validator_calls_clamp(cls, helper_funcs)

        for stmt in cls.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            target = stmt.target
            if not (isinstance(target, ast.Name) and target.id.endswith("_vnd")):
                continue
            if not _annotation_is_int_vnd(stmt.annotation):
                continue
            # Allowlisted via inline noqa.
            if line_has_allow_marker(
                source_lines, stmt.lineno, stmt.end_lineno or stmt.lineno, NOQA_MARKER
            ):
                continue
            # Guarded by Field(ge=1000, ...).
            if _field_call_has_ge_floor(stmt.value):
                continue
            # Guarded by a sibling model_validator referencing normalize_vnd_price.
            if class_has_validator:
                continue
            violations.append((stmt.lineno, target.id))

    return violations


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        files = [Path(arg) for arg in args if arg.endswith(".py")]
    else:
        files = iter_python_files(_REPO_ROOT, scopes=["scripts/agents/"])
    failures: list[str] = []
    for path in files:
        for lineno, field_name in _scan_file(path):
            try:
                rel = path.relative_to(_REPO_ROOT)
            except ValueError:
                rel = path
            failures.append(
                f"{rel}:{lineno}: unguarded VND field {field_name!r} — "
                f"add Field(ge=1000, ...) or a model_validator that calls "
                f"normalize_vnd_price (see shared/rules/vnd_price_clamp.py); "
                f"otherwise tag the line with `# noqa: vnd-clamp`."
            )
    if failures:
        sys.stderr.write("VND-clamp guard violations:\n")
        for line in failures:
            sys.stderr.write(f"  {line}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
