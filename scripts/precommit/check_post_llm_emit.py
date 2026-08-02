#!/usr/bin/env python3
"""Pre-commit AST guard for the post-LLM emit contract (SWI-206 Layer B).

Rejects new mutating Pydantic validators in ``scripts/agents/*.py`` that
do not call ``emit_rule_outcome`` from
``shared.observability_post_llm``. Catches the defect class
``feedback_post_llm_rule_layer.md`` documents.

Scope:
  * Decorators flagged: ``@model_validator``, ``@field_validator``,
    ``@root_validator``.
  * Mutation primitives flagged: ``object.__setattr__`` calls AND
    ``Attribute`` assignments where the target resolves to ``self`` or
    a function parameter (catches ``model.foo = bar``,
    ``self.score = total``, ``self.bull_probability /= 100``).
  * Helper-call follow: one frame deep, same module. If the validator
    body calls a locally-defined function with the validator's first
    argument (typically ``self`` or ``model``), the helper's body is
    walked too. Catches the ``belief_models`` pattern: validator →
    ``_normalize_belief_probabilities(self)`` → mutation.

Allowlist: ``scripts/precommit/post_llm_emit_allowlist.txt`` for
legitimate raise-only validators. Adding entries triggers Layer C
drift telemetry (the guard emits once per run with allowlist size).

Self-tests live in
``scripts/agents/evals/coercion_parity/test_precommit_guard.py``.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = Path(__file__).with_name("post_llm_emit_allowlist.txt")

TARGET_DECORATORS: frozenset[str] = frozenset(
    {"model_validator", "field_validator", "root_validator"}
)
TARGET_PREFIX = "scripts/agents/"

REMEDIATION_HINT = (
    "    Validator mutates LLM output but does not call emit_rule_outcome.\n"
    "    Either:\n"
    "      (a) Add a call: from shared.observability_post_llm import emit_rule_outcome\n"
    "          emit_rule_outcome('your_rule_id', 'coerced', agent=..., reason=..., ...)\n"
    "      (b) If the validator only raises (no mutation), add to the allowlist:\n"
    "          scripts/precommit/post_llm_emit_allowlist.txt"
)


def _load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()
    out: set[str] = set()
    for raw in ALLOWLIST_PATH.read_text().splitlines():
        stripped = raw.split("#", 1)[0].strip()
        if stripped:
            out.add(stripped)
    return out


def _decorator_name(node: ast.expr) -> str | None:
    """Return the bare name of a decorator (handles ``X`` and ``X(...)``)."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _has_target_decorator(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_decorator_name(d) in TARGET_DECORATORS for d in func.decorator_list)


def _enclosing_class_name(parents: list[ast.AST]) -> str | None:
    for node in reversed(parents):
        if isinstance(node, ast.ClassDef):
            return node.name
    return None


def _is_setattr_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "__setattr__"
        and isinstance(func.value, ast.Name)
        and func.value.id == "object"
    )


def _attribute_assign_targets_param(node: ast.AST, param_names: set[str]) -> bool:
    """True iff ``node`` is `<param>.<attr> = ...` or `<param>.<attr> op= ...`."""
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif (
        isinstance(node, ast.AugAssign)
        or isinstance(node, ast.AnnAssign)
        and node.value is not None
    ):
        targets = [node.target]
    for tgt in targets:
        if (
            isinstance(tgt, ast.Attribute)
            and isinstance(tgt.value, ast.Name)
            and tgt.value.id in param_names
        ):
            return True
    return False


def _is_emit_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "emit_rule_outcome":
        return True
    return isinstance(func, ast.Attribute) and func.attr == "emit_rule_outcome"


def _walk_for_signals(
    body: list[ast.stmt],
    param_names: set[str],
) -> tuple[bool, bool, set[str]]:
    """Walk ``body`` collecting (mutates, emits, locally_called_helpers).

    A helper is "locally called" when invoked as a bare ``Name(...)`` and
    receives one of ``param_names`` as the first positional argument.
    The guard follows those one frame deep against module-defined helpers.
    """
    mutates = False
    emits = False
    helpers: set[str] = set()
    for stmt in body:
        for node in ast.walk(stmt):
            if _is_setattr_call(node):
                mutates = True
            if _attribute_assign_targets_param(node, param_names):
                mutates = True
            if _is_emit_call(node):
                emits = True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in param_names
            ):
                helpers.add(node.func.id)
    return mutates, emits, helpers


def _module_helper_bodies(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def _check_file(path: Path, allowlist: set[str]) -> list[str]:
    rel = str(path.relative_to(REPO_ROOT))
    if not rel.startswith(TARGET_PREFIX):
        return []
    try:
        tree = ast.parse(path.read_text(), filename=rel)
    except SyntaxError as exc:
        return [f"{rel}: SyntaxError {exc}"]
    helpers = _module_helper_bodies(tree)
    findings: list[str] = []

    parents: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        parents.append(node)
        try:
            for child in ast.iter_child_nodes(node):
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and _has_target_decorator(child):
                    cls = _enclosing_class_name(parents) or "?"
                    key = f"{rel}:{cls}.{child.name}"
                    if key not in allowlist:
                        param_names: set[str] = set()
                        if child.args.args:
                            param_names.add(child.args.args[0].arg)
                        mutates, emits, called_helpers = _walk_for_signals(child.body, param_names)
                        if not mutates and called_helpers:
                            for hname in called_helpers:
                                helper_node = helpers.get(hname)
                                if helper_node is None:
                                    continue
                                helper_params: set[str] = set()
                                if helper_node.args.args:
                                    helper_params.add(helper_node.args.args[0].arg)
                                h_mut, h_emit, _ = _walk_for_signals(
                                    helper_node.body, helper_params
                                )
                                mutates = mutates or h_mut
                                emits = emits or h_emit
                        if mutates and not emits:
                            line = child.lineno
                            findings.append(
                                f"{rel}:{line}: {cls}.{child.name} mutates without "
                                f"emit_rule_outcome\n{REMEDIATION_HINT}"
                            )
                visit(child)
        finally:
            parents.pop()

    visit(tree)
    return findings


def main(argv: list[str]) -> int:
    files = [Path(a).resolve() for a in argv[1:]]
    if not files:
        files = sorted((REPO_ROOT / "scripts" / "agents").rglob("*.py"))
    allowlist = _load_allowlist()
    failures: list[str] = []
    for path in files:
        if not path.exists() or path.suffix != ".py":
            continue
        try:
            failures.extend(_check_file(path, allowlist))
        except ValueError:
            # path not under repo root (e.g. tmp file) — skip.
            continue

    # Allowlist drift telemetry (Layer C trigger b). Best-effort: only
    # emit when LOGFIRE_TOKEN is configured; pre-commit on a fresh
    # checkout shouldn't blow up.
    if os.environ.get("LOGFIRE_TOKEN"):
        try:
            sys.path.insert(0, str(REPO_ROOT / "scripts"))
            from shared.observability_post_llm import (
                emit_rule_outcome,  # type: ignore[import-not-found]
            )

            emit_rule_outcome(
                "precommit_allowlist",
                "unclassified",
                agent="precommit",
                reason="allowlist_size",
                boundary="classifier",
                metadata={"size": len(allowlist)},
            )
        except Exception:  # noqa: BLE001
            pass

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
