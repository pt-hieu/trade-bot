"""Regression: check_rr_literals hook also scans generated morning briefs.

Invariant: only two canonical floors per brief (effective_rr_floor +
shock_rr_floor). Retrospective context (MINDSET, "Similar days n=...") is
exempt — those legitimately cite past floors.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HOOK_PATH = Path(__file__).parent.parent.parent / "scripts" / "hooks" / "check_rr_literals.py"


@pytest.fixture
def hook_module():
    spec = importlib.util.spec_from_file_location("check_rr_literals", _HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_rr_literals"] = module
    spec.loader.exec_module(module)
    return module


def _write_brief(tmp_path: Path, body: str) -> Path:
    dated = tmp_path / "2026-04-22"
    dated.mkdir(parents=True, exist_ok=True)
    brief = dated / "morning-brief.md"
    brief.write_text(body)
    return brief


def test_single_floor_brief_passes(hook_module, tmp_path):
    brief = _write_brief(
        tmp_path,
        "\n".join(
            [
                "# Morning Brief",
                "",
                "STANCE",
                "Discipline: any new BUY must clear R:R >= 2.0",
                "KEY RISK",
                "Mitigation: require R:R >= 2.0 even for beneficiaries",
                "WHAT TO DO TODAY",
                "- WAIT: no setups meet R:R >= 2.0 today",
            ]
        ),
    )
    violations = hook_module._scan_brief(brief, str(brief))
    assert violations == []


def test_retrospective_floor_is_exempt(hook_module, tmp_path):
    """3.5 cited in MINDSET / 'Similar days' lines is historical — not drift."""
    brief = _write_brief(
        tmp_path,
        "\n".join(
            [
                "# Morning Brief",
                "",
                "MINDSET",
                "- Prior week used R:R >= 3.5 on similar regime days",
                "",
                "MARKET MOOD",
                "- Similar days: 75% win rate (n=3) -- confirmed R:R >= 3.5 discipline",
                "",
                "STANCE",
                "Discipline: any new BUY must clear R:R >= 2.0",
            ]
        ),
    )
    violations = hook_module._scan_brief(brief, str(brief))
    assert violations == []


def test_two_floor_pair_passes(hook_module, tmp_path):
    """effective_rr_floor + shock_rr_floor pair is the ceiling."""
    brief = _write_brief(
        tmp_path,
        "\n".join(
            [
                "# Morning Brief",
                "",
                "STANCE",
                "Discipline: shock-phase non-beneficiaries need R:R >= 3.0",
                "Discipline: other BUYs clear R:R >= 2.5",
            ]
        ),
    )
    violations = hook_module._scan_brief(brief, str(brief))
    assert violations == []


def test_three_distinct_floors_flags_drift(hook_module, tmp_path):
    brief = _write_brief(
        tmp_path,
        "\n".join(
            [
                "# Morning Brief",
                "",
                "STANCE",
                "Discipline: R:R >= 2.0",
                "KEY RISK",
                "Mitigation: require R:R >= 3.0",
                "ENTRY CRITERIA TODAY",
                "- R:R >= 3.5 floor",
            ]
        ),
    )
    violations = hook_module._scan_brief(brief, str(brief))
    assert violations
    # Every forward-looking literal reported
    assert len(violations) == 3


def test_hook_allow_marker_skips_line(hook_module, tmp_path):
    brief = _write_brief(
        tmp_path,
        "\n".join(
            [
                "# Morning Brief",
                "",
                "STANCE",
                "Discipline: R:R >= 2.0",
                "KEY RISK",
                "Mitigation: require R:R >= 3.0",
                "FOOTNOTE  # HOOK-ALLOW: rr-literal reason=comparison-to-historical",
                "- R:R >= 3.5 comparison  # HOOK-ALLOW: rr-literal reason=comparison-to-historical",
            ]
        ),
    )
    violations = hook_module._scan_brief(brief, str(brief))
    # Only 2 distinct floors in non-exempt lines → no violation
    assert violations == []
