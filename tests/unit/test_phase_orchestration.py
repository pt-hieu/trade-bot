"""AST lint tests for pipeline/phase_orchestration.py span instrumentation.

Guards against silent regression of T08: without per-phase spans in
run_phases_3_to_6, phases 3-6 become an unattributed gap under
morning_brief_generation, making post-phase-2 debugging impossible.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE_ORCH_PATH = REPO_ROOT / "scripts" / "pipeline" / "phase_orchestration.py"

EXPECTED_PHASE_SPANS = {
    "phase3_trading_mode",
    "phase3a_constraints",
    "phase3b_picks",
    "phase3_advocates",
    "phase_strategy_synthesis",
    "phase5_alerts",
    "phase6_recommendations",
}


def _collect_span_names(tree: ast.AST) -> set[str]:
    """Collect first-arg string literals from `span(...)` and `_spanned(...)` calls."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ("span", "_spanned"):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            names.add(first_arg.value)
    return names


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found in phase_orchestration.py")


def test_run_phases_3_to_6_wraps_each_phase_in_span():
    source = PHASE_ORCH_PATH.read_text()
    tree = ast.parse(source)

    run_phases = _find_function(tree, "run_phases_3_to_6")
    span_names = _collect_span_names(run_phases)

    missing = EXPECTED_PHASE_SPANS - span_names
    assert not missing, (
        f"run_phases_3_to_6 is missing required span wrappers: {sorted(missing)}. "
        f"Each of phases 3, 3a, 3b, advocates, synthesis, 5, 6 must be wrapped in "
        f"`with span(...)`  so Logfire shows per-phase durations."
    )
    assert len(span_names) >= len(EXPECTED_PHASE_SPANS), (
        f"Expected at least {len(EXPECTED_PHASE_SPANS)} spans, found {len(span_names)}: {span_names}"
    )
