"""SWI-200: pure narrative_sector_filter rule tests."""

from __future__ import annotations

from shared.rules.narrative_sector_filter import filter_tickers_by_sector

_SECTOR_MAP: dict[str, str | None] = {
    "HPG": "steel",
    "TCB": "banks",
    "MSN": "consumer",
    "FPT": "technology",
}


def test_strict_mode_drops_cross_sector() -> None:
    result = filter_tickers_by_sector(["HPG", "TCB", "MSN"], "earnings", ["steel"], _SECTOR_MAP)
    assert result == ["HPG"]


def test_strict_mode_keeps_in_sector() -> None:
    result = filter_tickers_by_sector(["HPG"], "earnings", ["steel"], _SECTOR_MAP)
    assert result == ["HPG"]


def test_macro_mode_skips_filter() -> None:
    result = filter_tickers_by_sector(["HPG", "TCB", "MSN"], "macro", ["steel"], _SECTOR_MAP)
    assert result == ["HPG", "TCB", "MSN"]


def test_geopolitical_mode_skips_filter() -> None:
    result = filter_tickers_by_sector(["HPG", "TCB"], "geopolitical", [], _SECTOR_MAP)
    assert result == ["HPG", "TCB"]


def test_missing_sector_dropped_under_strict() -> None:
    sector_map: dict[str, str | None] = {"HPG": "steel", "UNKNOWN": None}
    result = filter_tickers_by_sector(["HPG", "UNKNOWN"], "earnings", ["steel"], sector_map)
    assert result == ["HPG"]


def test_empty_affected_sectors_keeps_all() -> None:
    # Caller hadn't classified yet — don't over-filter at creation time.
    result = filter_tickers_by_sector(["HPG", "TCB"], "earnings", [], _SECTOR_MAP)
    assert result == ["HPG", "TCB"]


def test_empty_input_returns_empty() -> None:
    assert filter_tickers_by_sector([], "earnings", ["steel"], _SECTOR_MAP) == []
