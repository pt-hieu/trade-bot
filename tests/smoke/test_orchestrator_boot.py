"""Boot-time smoke harness for the orchestrator import graph (SWI-181).

Wave 1 lands ~24 fixes across the pipeline, agent, and rules layers. This
harness protects every later commit from import-graph regressions: it spawns
a subprocess that imports the orchestrator entry-point modules exactly the way
``llm_analysis.py`` does (package warm-up first), and asserts a clean exit.

Mirrors ``tests/unit/test_orchestrator_imports.py`` (the SWI-175 guard):
``subprocess.run([sys.executable, "-c", program])`` with ``scripts`` on the
path. One test additionally seeds ``mock_trading_config`` to prove that boot
paths reaching ``get_trading_config()`` do not ``RuntimeError`` when the cache
is pre-populated.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def test_orchestrator_boot_imports_clean() -> None:
    """Entry-point modules import without error when the package is warmed first."""
    program = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(SCRIPTS_DIR)!r})
        import pipeline  # warm package init like llm_analysis.py does
        from pipeline import load_db_context  # noqa: F401
        from agents.picks import extract_top_picks  # noqa: F401
        import llm_analysis  # noqa: F401  -- orchestrator entry module
        """
    ).strip()
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"orchestrator boot import failed:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )


def test_orchestrator_boot_with_mock_config(mock_trading_config) -> None:
    """Config-dependent boot survives when the trading-config cache is seeded.

    ``mock_trading_config`` pre-populates the in-process cache, but the
    subprocess is a fresh interpreter — so this primarily proves the import
    graph itself is config-tolerant at module-load time (no top-level
    ``get_trading_config()`` call that raises ``RuntimeError`` during import).
    """
    program = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(SCRIPTS_DIR)!r})
        import pipeline  # noqa: F401
        from pipeline import load_db_context  # noqa: F401
        from agents.picks import extract_top_picks  # noqa: F401
        """
    ).strip()
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"config-dependent boot import failed:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )
