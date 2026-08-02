"""Unit tests for scripts/hooks/_baseline.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "scripts")

from hooks._baseline import load_baseline, regress_diff, write_baseline


def test_new_file_with_violations_fails(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.txt"
    write_baseline(baseline_path, {"scripts/a.py": 3})
    baseline = load_baseline(baseline_path)
    current = {"scripts/a.py": 3, "scripts/b.py": 2}
    regressions = regress_diff(current, baseline)
    assert regressions == [("scripts/b.py", 0, 2)]


def test_same_count_passes(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.txt"
    write_baseline(baseline_path, {"scripts/a.py": 3, "scripts/b.py": 2})
    baseline = load_baseline(baseline_path)
    current = {"scripts/a.py": 3, "scripts/b.py": 2}
    assert regress_diff(current, baseline) == []


def test_lower_count_passes(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.txt"
    write_baseline(baseline_path, {"scripts/a.py": 5})
    baseline = load_baseline(baseline_path)
    current = {"scripts/a.py": 2}
    assert regress_diff(current, baseline) == []


def test_higher_count_fails(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.txt"
    write_baseline(baseline_path, {"scripts/a.py": 5})
    baseline = load_baseline(baseline_path)
    current = {"scripts/a.py": 7}
    assert regress_diff(current, baseline) == [("scripts/a.py", 5, 7)]


def test_removed_file_silently_dropped(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.txt"
    write_baseline(baseline_path, {"scripts/a.py": 5, "scripts/gone.py": 3})
    baseline = load_baseline(baseline_path)
    current = {"scripts/a.py": 5}
    assert regress_diff(current, baseline) == []


def test_write_baseline_sorted(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.txt"
    write_baseline(baseline_path, {"scripts/z.py": 1, "scripts/a.py": 2, "scripts/m.py": 3})
    content = baseline_path.read_text(encoding="utf-8")
    assert content == "scripts/a.py:2\nscripts/m.py:3\nscripts/z.py:1\n"


def test_load_baseline_skips_comments_and_blanks(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.txt"
    baseline_path.write_text(
        "# comment\n\nscripts/a.py:4\n# another\nscripts/b.py:2\n",
        encoding="utf-8",
    )
    assert load_baseline(baseline_path) == {"scripts/a.py": 4, "scripts/b.py": 2}


def test_write_baseline_skips_zero_counts(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.txt"
    write_baseline(baseline_path, {"scripts/a.py": 0, "scripts/b.py": 2})
    assert baseline_path.read_text(encoding="utf-8") == "scripts/b.py:2\n"
