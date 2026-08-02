"""Phase 1 and Phase 2: Parallel agent execution.

Module layout (post-modularisation, SWI-212):
  * ``utils.py`` — _API_SEMAPHORE singleton + _run_with_semaphore + _collect_sector_outputs.
  * ``phase1.py`` — run_phase1_parallel (independent global agents).
  * ``phase2.py`` — run_phase2_parallel (sector + longterm + positions).
  * ``__init__.py`` — re-exports the public surface.

Singleton invariant (tests/unit/test_phase_parallel_singleton.py): the
``_API_SEMAPHORE`` lives in ``utils.py`` only; ``phase1`` and ``phase2``
import it via ``from .utils import _run_with_semaphore`` (never re-bind).
"""

from __future__ import annotations

from .phase1 import run_phase1_parallel
from .phase2 import run_phase2_parallel
from .utils import _API_SEMAPHORE, _collect_sector_outputs, _run_with_semaphore

__all__ = [
    "_API_SEMAPHORE",
    "_collect_sector_outputs",
    "_run_with_semaphore",
    "run_phase1_parallel",
    "run_phase2_parallel",
]
