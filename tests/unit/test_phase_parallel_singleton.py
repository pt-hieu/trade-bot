"""Singleton invariant for the pipeline/phase_parallel package (SWI-212 FIX 6).

After splitting ``pipeline/phase_parallel.py`` into a package
(``utils.py`` + ``phase1.py`` + ``phase2.py``) the ``_API_SEMAPHORE``
must remain a single Semaphore object so the rate limit (4 concurrent
API calls) is shared across both phases.

Without this test, an accidental ``_API_SEMAPHORE = asyncio.Semaphore(4)``
re-binding inside any submodule would silently double the concurrent
call ceiling and reintroduce the rate-limit bypass class.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_api_semaphore_is_single_object():
    from pipeline import phase_parallel
    from pipeline.phase_parallel import phase1, phase2, utils

    canonical = utils._API_SEMAPHORE
    assert phase_parallel._API_SEMAPHORE is canonical, (
        "pipeline.phase_parallel._API_SEMAPHORE must be the same Semaphore "
        "object as pipeline.phase_parallel.utils._API_SEMAPHORE."
    )
    # phase1 + phase2 use _run_with_semaphore (not the bare semaphore) so
    # walking their dependency chain confirms they reach utils._API_SEMAPHORE.
    assert phase1._run_with_semaphore is utils._run_with_semaphore, (
        "phase1 imports _run_with_semaphore from utils; re-binding breaks the singleton."
    )
    assert phase2._run_with_semaphore is utils._run_with_semaphore, (
        "phase2 imports _run_with_semaphore from utils; re-binding breaks the singleton."
    )
