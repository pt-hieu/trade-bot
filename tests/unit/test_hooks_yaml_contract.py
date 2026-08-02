"""Regression: agent-yaml tool-surface contract hook.

Covers three checks layered onto the existing composite-vs-atomic hook:
  (1) Composite + atomic imperative coexistence (2026-04-24).
  (2) Atomic tool imperatively invoked without a `call_tools([...])` exemplar.
  (3) Tool-using config without `request_limit` (or `request_limit > 15`).

Fixtures use real tool names from the live broker catalog so the hook's
`_load_tool_catalog` integration is exercised end-to-end. Uses `main(argv)`
because the hook reports violations via stderr + non-zero exit.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HOOK_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "hooks"
    / "check_agent_yaml_composite_vs_atomic.py"
)


@pytest.fixture
def hook_module():
    spec = importlib.util.spec_from_file_location(
        "check_agent_yaml_composite_vs_atomic", _HOOK_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_agent_yaml_composite_vs_atomic"] = module
    spec.loader.exec_module(module)
    return module


def _write_config(tmp_path: Path, relative: str, body: str) -> Path:
    full = tmp_path / relative
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body)
    return full


def _run_hook(hook_module, monkeypatch, tmp_path, paths: list[Path]) -> int:
    """Run the hook with `paths` as argv, chdir'd so relative prefixes work."""
    monkeypatch.chdir(tmp_path)
    relative_paths = [str(p.relative_to(tmp_path)) for p in paths]
    return hook_module.main(["check_agent_yaml_composite_vs_atomic.py", *relative_paths])


def test_no_tools_config_exempt_from_request_limit(hook_module, monkeypatch, tmp_path):
    """Configs without any imperative tool reference skip the request_limit check."""
    config = _write_config(
        tmp_path,
        "scripts/agents/configs/prose_only.yaml",
        """agent_key: prose_only
system_prompt: |
  You write prose. No tool calls. Read the injected data directly and emit text.
""",
    )
    assert _run_hook(hook_module, monkeypatch, tmp_path, [config]) == 0


def test_tools_without_request_limit_fails(hook_module, monkeypatch, tmp_path):
    """Imperative tool reference without a `request_limit:` is rejected."""
    config = _write_config(
        tmp_path,
        "scripts/agents/configs/bad_no_limit.yaml",
        """agent_key: bad_no_limit
system_prompt: |
  Call technical.get_technicals for every ticker.

      call_tools([
        {"name": "technical.get_technicals", "args": {"tickers": ["FPT"]}}
      ])
""",
    )
    assert _run_hook(hook_module, monkeypatch, tmp_path, [config]) == 1


def test_request_limit_above_cap_fails(hook_module, monkeypatch, tmp_path):
    """`request_limit: 30` (loose default) on a tool-using config is rejected."""
    config = _write_config(
        tmp_path,
        "scripts/agents/configs/bad_loose_limit.yaml",
        """agent_key: bad_loose_limit
request_limit: 30
system_prompt: |
  Call technical.get_technicals for every ticker.

      call_tools([
        {"name": "technical.get_technicals", "args": {"tickers": ["FPT"]}}
      ])
""",
    )
    assert _run_hook(hook_module, monkeypatch, tmp_path, [config]) == 1


def test_atomic_without_exemplar_fails(hook_module, monkeypatch, tmp_path):
    """Imperative atomic reference without a `call_tools` block is rejected."""
    config = _write_config(
        tmp_path,
        "scripts/agents/configs/bad_no_exemplar.yaml",
        """agent_key: bad_no_exemplar
request_limit: 10
system_prompt: |
  Call technical.get_technicals for every ticker.
""",
    )
    assert _run_hook(hook_module, monkeypatch, tmp_path, [config]) == 1


def test_atomic_with_exemplar_and_limit_passes(hook_module, monkeypatch, tmp_path):
    """Imperative atomic reference PLUS batch exemplar PLUS bounded limit passes."""
    config = _write_config(
        tmp_path,
        "scripts/agents/configs/good.yaml",
        """agent_key: good
request_limit: 10
system_prompt: |
  Use technical.get_technicals for historical context only.

      call_tools([
        {"name": "technical.get_technicals", "args": {"tickers": ["FPT", "TCB"]}}
      ])
""",
    )
    assert _run_hook(hook_module, monkeypatch, tmp_path, [config]) == 0


def test_substring_tool_names_do_not_trigger_false_positive(hook_module, monkeypatch, tmp_path):
    """`get_valuation` must NOT match inside `get_valuation_history`."""
    config = _write_config(
        tmp_path,
        "scripts/agents/configs/substring.yaml",
        """agent_key: substring
request_limit: 10
system_prompt: |
  Call fundamental.get_valuation_history for sector comparison.

      call_tools([
        {"name": "fundamental.get_valuation_history", "args": {"tickers": ["FPT"]}}
      ])
""",
    )
    assert _run_hook(hook_module, monkeypatch, tmp_path, [config]) == 0


def test_live_configs_pass_hook(hook_module, monkeypatch):
    """The shipped `scripts/agents/configs/*.yaml` corpus must pass."""
    project_root = Path(__file__).parent.parent.parent
    monkeypatch.chdir(project_root)
    configs = sorted(
        str(path.relative_to(project_root))
        for path in (project_root / "scripts" / "agents" / "configs").glob("*.yaml")
    )
    assert configs, "no agent configs found — test harness misconfigured"
    assert hook_module.main(["check_agent_yaml_composite_vs_atomic.py", *configs]) == 0
