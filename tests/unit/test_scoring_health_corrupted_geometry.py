"""SWI-355: scoring_health corrupted-geometry predicate.

Unit-level: assert the SQL string carries the predicate; integration in
the scoring_health backfill against Neon proves the end-to-end behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

SCORING_HEALTH = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "scoring_health.py"


def _source() -> str:
    return SCORING_HEALTH.read_text()


def test_corrupted_geometry_query_present():
    """Predicate fingerprint (rr > 20 AND sim = 0) is in source."""
    source = _source()
    assert "corrupted_geometry_rows" in source
    assert re.search(r"risk_reward'\)::float\s*>\s*20", source)
    assert "sim_p_target" in source


def test_corrupted_geometry_includes_degenerate_risk_diag():
    """SWI-358 tightening: predicate ORs in degenerate_risk diagnostic."""
    source = _source()
    assert "degenerate_risk" in source
    assert "'true'" in source


def test_corrupted_geometry_appended_to_failures():
    """Block surfaces as a `failures.append(...)` ticker list."""
    source = _source()
    assert "Corrupted-geometry regression" in source
