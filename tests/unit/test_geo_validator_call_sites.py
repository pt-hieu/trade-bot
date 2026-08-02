"""SWI-16: grep guard — validator must be wired into the 3 pipeline entry points."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPECTED_FILES = (
    "scripts/daily_scan.py",
    "scripts/midday_check.py",
    "scripts/retrospective.py",
)
NEEDLE = "_validate_geo_factor_map_once"


def test_validator_invoked_in_all_three_entry_points():
    missing = []
    for relative in EXPECTED_FILES:
        path = REPO / relative
        assert path.exists(), f"Expected pipeline entry file missing: {relative}"
        if NEEDLE not in path.read_text(encoding="utf-8"):
            missing.append(relative)
    assert not missing, (
        f"Geo factor-map validator wiring missing from: {missing}. "
        "Each pipeline entry must call `_validate_geo_factor_map_once()`."
    )
