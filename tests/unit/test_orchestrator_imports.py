"""Lock-in for ``scripts/hooks/check_orchestrator_imports.py`` (SWI-175 guard).

The hook spawns a subprocess that imports the orchestrator entry-point
modules. These tests assert:

1. The hook exits 0 on a clean main (production-shaped graph).
2. The hook exits 1 on the SWI-175 fingerprint: an annotation referencing
   a name imported only under ``if TYPE_CHECKING:`` AND a module missing
   ``from __future__ import annotations``.

The fingerprint test runs the same subprocess machinery the hook uses but
points it at a temporary fixture file, so the test does not require
mutating any module on the real import graph.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "scripts" / "hooks" / "check_orchestrator_imports.py"


def test_orchestrator_smoke_check_clean_main_exits_zero() -> None:
    """The hook must pass on the current main branch state."""
    completed = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"Smoke check failed unexpectedly:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )


def test_swi_175_fingerprint_subprocess_raises_name_error(tmp_path: Path) -> None:
    """SWI-175 fingerprint: TYPE_CHECKING-only import + no ``from __future__``.

    Build a temp module that mirrors the original failure shape: declare a
    function annotation against ``ScoreRecorder`` imported under
    ``if TYPE_CHECKING:`` AND omit ``from __future__ import annotations``.
    A direct ``python -c "import fixture"`` MUST raise NameError; this is the
    behaviour the orchestrator smoke check relies on.

    Re-adding ``from __future__ import annotations`` switches the import to
    succeed — verifying the fix path the hook directs operators toward.
    """
    fixture_dir = tmp_path / "swi175_fixture"
    fixture_dir.mkdir()
    (fixture_dir / "__init__.py").write_text("")

    broken_source = textwrap.dedent(
        """
        # Intentionally NO `from __future__ import annotations` here.
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from typing import Protocol

            class ScoreRecorder(Protocol):
                ...

        def use_recorder(score_recorder: ScoreRecorder | None = None) -> None:
            return None
        """
    ).strip()
    (fixture_dir / "broken.py").write_text(broken_source)

    completed = subprocess.run(
        [sys.executable, "-c", "import swi175_fixture.broken"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0, "broken fixture must fail at import time"
    assert "NameError" in (completed.stderr or "")

    fixed_source = "from __future__ import annotations\n\n" + broken_source
    (fixture_dir / "broken.py").write_text(fixed_source)
    completed_fixed = subprocess.run(
        [sys.executable, "-c", "import swi175_fixture.broken"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed_fixed.returncode == 0, (
        f"fixed fixture must import cleanly, got stderr={completed_fixed.stderr}"
    )


@pytest.mark.parametrize(
    "module_name",
    [
        "agents.picks",
        "agents.positions_ensemble",
        "agents.sector",
        "agents.synthesis_writers",
        "pipeline.phase_orchestration",
        "pipeline.phase_recommendations",
    ],
)
def test_each_orchestrator_module_imports_without_error(module_name: str) -> None:
    """Each orchestrator-graph module imports cleanly when the package is loaded first."""
    program = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(REPO_ROOT / "scripts")!r})
        import pipeline  # warm package init like llm_analysis.py does
        import {module_name}
        """
    ).strip()
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, f"{module_name} failed to import: stderr={completed.stderr}"
