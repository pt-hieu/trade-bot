"""SWI-197: filter_vn_only universe-explicit whitelist tests."""

from __future__ import annotations

from shared.vn_universe import filter_vn_only

_UNIVERSE: frozenset[str] = frozenset({"FPT", "TCB", "HPG", "MSN"})


def test_drops_non_vn_codes() -> None:
    result = filter_vn_only(
        ["UAE", "FPT", "SPR", "TCB", "VN-INDEX"],
        _UNIVERSE,
        context="test",
    )
    assert result == ["FPT", "TCB", "VN-INDEX"]


def test_keeps_vn_index_placeholder() -> None:
    result = filter_vn_only(["VN-INDEX"], _UNIVERSE, context="test")
    assert result == ["VN-INDEX"]


def test_drops_invalid_shape() -> None:
    result = filter_vn_only(
        ["BOJ", "ECB", "USA", "FPT123"],
        _UNIVERSE,
        context="test",
    )
    # FPT123 is shape-invalid (>4 chars), BOJ/ECB/USA aren't in universe.
    assert result == []


def test_empty_input_returns_empty() -> None:
    assert filter_vn_only([], _UNIVERSE, context="test") == []
    assert filter_vn_only(None, _UNIVERSE, context="test") == []


def test_universe_none_falls_back_to_shape_only() -> None:
    # Fail-open: universe load failed → shape-only check.
    result = filter_vn_only(["FPT", "UAE"], None, context="test")
    # Both are shape-valid (3-letter uppercase), so both pass under shape-only.
    assert result == ["FPT", "UAE"]
