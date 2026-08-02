#!/usr/bin/env python3
"""Pre-flight orchestrator import smoke check.

SWI-175 class: a function annotation references a name imported under
``if TYPE_CHECKING:`` AND the host module is missing
``from __future__ import annotations``. Pyright evaluates the
``TYPE_CHECKING`` block statically and reports the file clean; only an
actual Python import surfaces the ``NameError`` at module load time.

Pre-commit pyright + unit tests did not load the orchestrator entry-point
chain end-to-end on 2026-04-28, so the morning brief shipped 6.5 hours
late while a one-line annotation kept the pipeline broken on main.

Strategy: a single fresh subprocess imports the full orchestrator graph
in the same order ``llm_analysis.py`` does (``pipeline`` package first,
then ``analysis.synthesis``, then the agent leaves). Annotations are
evaluated when each ``def`` runs at import time, so any
TYPE_CHECKING-only name referenced at runtime fails loud the first time
its host module loads — regardless of which import name happened to
trigger the load.

A single subprocess (rather than one-per-module) avoids re-tripping the
pre-existing ``pipeline``/``agents.picks`` circular-import ordering
constraint, which is an architectural issue out of scope for this hook.
The hook is intentionally narrow: it only catches the SWI-175 class
(unguarded annotations against TYPE_CHECKING imports).

Runs in pre-commit (local) and as the first guard step in the daily-scan
GitHub Actions job, so a broken main aborts before LLM cost is incurred.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Order mirrors ``llm_analysis.py``: ``pipeline`` first (loads phase
# modules + types), ``analysis.synthesis`` next, then the agent leaves
# that consumers of ``pipeline`` may also enter through. Annotations
# evaluated by the time the package finishes loading; a single trailing
# ``import agents.picks`` is enough to confirm the leaf module's own
# annotations resolved cleanly.
ORCHESTRATOR_IMPORT_PROGRAM: str = """
import sys
sys.path.insert(0, {scripts_dir!r})

# Mirror llm_analysis.py / daily_scan.py top-of-file ordering so we
# replicate the production load graph rather than fight the existing
# circular-import ordering.
import pipeline
import pipeline.phase_orchestration
import pipeline.phase_postprocess
import pipeline.phase_picks
import pipeline.phase_recommendations
import analysis.synthesis
import agents.picks
import agents.positions_ensemble
import agents.sector
import agents.synthesis
import agents.synthesis_writers
""".strip()


def main() -> int:
    program = ORCHESTRATOR_IMPORT_PROGRAM.format(scripts_dir=str(SCRIPTS_DIR))
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print(
            "Orchestrator import smoke check FAILED — at least one entry-point "
            "module raises at import time. This is the SWI-175 class: a runtime "
            "name reference whose import is gated by `if TYPE_CHECKING:`. "
            "Add `from __future__ import annotations` to the offending module, "
            "or move the import out of the TYPE_CHECKING block.",
            file=sys.stderr,
        )
        if completed.stderr:
            print("\n--- subprocess stderr ---", file=sys.stderr)
            sys.stderr.write(completed.stderr)
        if completed.stdout:
            print("\n--- subprocess stdout ---", file=sys.stderr)
            sys.stderr.write(completed.stdout)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
