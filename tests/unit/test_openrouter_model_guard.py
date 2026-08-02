"""Pre-commit hook catches bare OpenRouterModel(...) construction outside model.py.

Synthetic violation file proves the scanner fires; a clean file proves it
stays quiet. Whitelist of `scripts/agents/model.py` itself is verified by
the clean-path case.
"""

from __future__ import annotations

from pathlib import Path

# The hook script lives outside the normal package path; import by file.
HOOK_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / "hooks"
    / ("check_openrouter_model_construction.py")
)


def _load_hook_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_openrouter_model_construction", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hook_flags_violation(tmp_path):
    """A file that constructs OpenRouterModel elsewhere must fail the hook."""
    hook = _load_hook_module()

    # Write a synthetic violator under the conventional scripts/ prefix so
    # the scanner's prefix filter accepts it.
    target_dir = tmp_path / "scripts" / "pipeline"
    target_dir.mkdir(parents=True)
    violator = target_dir / "bad_module.py"
    violator.write_text(
        "from pydantic_ai.models.openrouter import OpenRouterModel\n"
        "def go():\n"
        "    return OpenRouterModel('test/model', provider=None)\n"
    )

    # argv[0] is the hook name; payload paths follow. Use a path relative to
    # tmp_path so the "scripts/" prefix lines up.
    relative = violator.relative_to(tmp_path)
    saved_cwd = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        exit_code = hook.main(["check_openrouter_model_construction.py", str(relative)])
    finally:
        import os

        os.chdir(saved_cwd)

    assert exit_code == 1


def test_hook_permits_model_py_factory(tmp_path):
    """scripts/agents/model.py construction is whitelisted (it IS the factory)."""
    hook = _load_hook_module()

    target_dir = tmp_path / "scripts" / "agents"
    target_dir.mkdir(parents=True)
    factory = target_dir / "model.py"
    factory.write_text(
        "from pydantic_ai.models.openrouter import OpenRouterModel\n"
        "def make():\n"
        "    return OpenRouterModel('test/model', provider=None)\n"
    )

    relative = factory.relative_to(tmp_path)
    saved_cwd = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        exit_code = hook.main(["check_openrouter_model_construction.py", str(relative)])
    finally:
        import os

        os.chdir(saved_cwd)

    assert exit_code == 0
