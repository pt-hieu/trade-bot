"""SWI-193: filter_vn_only is fail-closed when universe is None."""

from __future__ import annotations

from shared.vn_universe import VN_INDEX_PLACEHOLDER, filter_vn_only


def test_filter_vn_only_drops_all_when_universe_is_none() -> None:
    result = filter_vn_only(
        ["VCB", "BOJ", "ECB", "FPT", VN_INDEX_PLACEHOLDER],
        None,
        context="test_fail_closed",
    )
    assert result == []


def test_filter_vn_only_keeps_known_when_universe_present() -> None:
    universe = frozenset({"VCB", "FPT"})
    result = filter_vn_only(
        ["VCB", "BOJ", "ECB", "FPT"],
        universe,
        context="test_normal",
    )
    assert sorted(result) == ["FPT", "VCB"]


def test_filter_vn_only_empty_input_no_alert() -> None:
    # Empty input must short-circuit BEFORE the fail-closed alert path.
    assert filter_vn_only([], None, context="test_empty") == []
    assert filter_vn_only(None, None, context="test_none_input") == []
