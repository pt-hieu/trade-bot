"""SWI-261: assert catalyst_check body does not parallel-gather spike + news.

Body holds a session-scoped advisory lock_conn for its entire run. Parallel
fan-out into nested gathers inside detect_catalyst_spike +
check_catalyst_news exhausts the default 10-slot pool. Serial keeps
concurrent acquires bounded.
"""

from __future__ import annotations

import ast
import inspect

import pytest
import scripts.catalyst_check as catalyst_check
import scripts.pipeline.phase_catalyst_revision as revision_module


def _gather_calls_in(source: str) -> list[ast.Call]:
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "gather":
            calls.append(node)
    return calls


def test_body_does_not_use_gather_for_spike_and_news() -> None:
    """detect_catalyst_spike and check_catalyst_news must not be siblings of asyncio.gather."""
    source = inspect.getsource(catalyst_check._run_catalyst_check_body)
    for call in _gather_calls_in(source):
        names = {
            arg.func.id
            for arg in call.args
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
        }
        assert not ("detect_catalyst_spike" in names and "check_catalyst_news" in names), (
            "spike + news must run serially under the held lock_conn (SWI-261)"
        )


def test_step_0b_does_not_use_gather() -> None:
    """Step 0b (narratives + lifecycle) must serialize under held lock_conn."""
    source = inspect.getsource(catalyst_check._run_catalyst_check_body)
    for call in _gather_calls_in(source):
        names = {
            arg.func.id
            for arg in call.args
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
        }
        assert "_refresh_narratives" not in names and "refresh_catalyst_lifecycle" not in names, (
            "Step 0b must serialize narratives + lifecycle under held lock_conn (SWI-261 follow-up)"
        )


@pytest.mark.parametrize(
    "target",
    [
        catalyst_check._refresh_narratives,
        revision_module.run_strategy_revision,
    ],
    ids=["refresh_narratives", "run_strategy_revision"],
)
def test_function_does_not_use_gather(target) -> None:
    """Functions running under catalyst_check's held lock_conn must not fan out via gather."""
    source = inspect.getsource(target)
    assert not _gather_calls_in(source), (
        f"{target.__name__} runs under held lock_conn; inner DB fan-out exhausts pool (SWI-261 family)"
    )


def test_pool_max_size_env_var_respected() -> None:
    """Database max_size must be derivable from SWINGY_PG_POOL_MAX."""
    import scripts.shared.database as database_module

    source = inspect.getsource(database_module.Database.connect)
    assert "SWINGY_PG_POOL_MAX" in source, (
        "pool max_size must read SWINGY_PG_POOL_MAX env var (SWI-261)"
    )
