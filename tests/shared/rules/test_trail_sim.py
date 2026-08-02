"""Pure trail simulator tests — no DB, no async."""

from __future__ import annotations

import pytest

from shared.rules.trail_sim import simulate_atr_trail


def _bar(date: str, o: int, h: int, low: int, c: int) -> dict:
    return {"date": date, "open": o, "high": h, "low": low, "close": c}


def test_requires_positive_atr() -> None:
    with pytest.raises(ValueError):
        simulate_atr_trail(
            bars=[_bar("2026-01-02", 50, 51, 49, 50)],
            entry_price=50,
            stop_price=45,
            atr_at_entry=0,
            trail_mult=2.5,
            entry_date="2026-01-02",
        )


def test_monotonic_rally_pends() -> None:
    bars = [
        _bar("2026-01-02", 50_000, 51_000, 49_500, 50_800),
        _bar("2026-01-03", 51_000, 52_000, 50_500, 51_800),
        _bar("2026-01-06", 52_000, 53_000, 51_500, 52_800),
    ]
    result = simulate_atr_trail(
        bars=bars,
        entry_price=50_000,
        stop_price=47_000,
        atr_at_entry=1_000,
        trail_mult=2.5,
        entry_date="2026-01-02",
    )
    assert result.status == "PENDING"
    assert result.peak_price == 53_000


def test_pullback_fires_trail_win() -> None:
    bars = [
        _bar("2026-01-02", 50_000, 60_000, 49_800, 59_500),
        # Pullback on day 2: low crosses trail (peak 60_000 − 2.5×1_000 = 57_500)
        _bar("2026-01-03", 59_000, 59_500, 57_000, 57_200),
    ]
    result = simulate_atr_trail(
        bars=bars,
        entry_price=50_000,
        stop_price=47_000,
        atr_at_entry=1_000,
        trail_mult=2.5,
        entry_date="2026-01-02",
    )
    assert result.status == "WIN"
    assert result.exit_price == 57_500
    assert result.pnl_percent == pytest.approx(15.0, rel=0.01)


def test_gap_down_exit_at_open() -> None:
    bars = [
        _bar("2026-01-02", 50_000, 60_000, 49_800, 59_500),
        # Gap-down below trail level → exit at open (56_000 < trail 57_500)
        _bar("2026-01-03", 56_000, 56_500, 55_500, 55_800),
    ]
    result = simulate_atr_trail(
        bars=bars,
        entry_price=50_000,
        stop_price=47_000,
        atr_at_entry=1_000,
        trail_mult=2.5,
        entry_date="2026-01-02",
    )
    assert result.status == "WIN"
    assert result.exit_price == 56_000


def test_hard_stop_beats_trail() -> None:
    bars = [
        _bar("2026-01-02", 50_000, 50_200, 49_900, 50_100),
        # Plunge to stop — trail hasn't armed yet (peak == entry)
        _bar("2026-01-03", 48_000, 48_100, 46_500, 46_800),
    ]
    result = simulate_atr_trail(
        bars=bars,
        entry_price=50_000,
        stop_price=47_000,
        atr_at_entry=1_000,
        trail_mult=2.5,
        entry_date="2026-01-02",
    )
    assert result.status == "LOSS"
    # Gap opens below the hard stop — exit at open (cheaper than stop).
    assert result.exit_price == 47_000 or result.exit_price == 48_000


def test_entry_never_hit_missed() -> None:
    bars = [
        _bar("2026-01-02", 52_000, 53_000, 51_000, 52_500),  # low never <= 50_000
    ]
    result = simulate_atr_trail(
        bars=bars,
        entry_price=50_000,
        stop_price=47_000,
        atr_at_entry=1_000,
        trail_mult=2.5,
        entry_date="2026-01-02",
    )
    assert result.status == "MISSED"
    assert result.days_in_trade == 0


def test_hose_floor_lock() -> None:
    bars = [
        _bar("2026-01-02", 50_000, 60_000, 49_800, 59_000),  # close 59_000
        # Floor limit = round(59_000 × 0.93) = 54_870. Open at floor.
        _bar("2026-01-03", 54_870, 54_870, 54_870, 54_870),
    ]
    result = simulate_atr_trail(
        bars=bars,
        entry_price=50_000,
        stop_price=47_000,
        atr_at_entry=1_000,
        trail_mult=2.5,
        entry_date="2026-01-02",
    )
    assert result.status == "TRAIL_FLOOR_LOCK"
    assert result.exit_price == 54_870


def test_suspension_counted() -> None:
    bars = [
        _bar("2026-01-02", 50_000, 51_000, 49_500, 50_800),
        {"date": "2026-01-03", "open": None, "high": None, "low": None, "close": None},
        _bar("2026-01-06", 51_000, 52_000, 50_500, 51_800),
    ]
    result = simulate_atr_trail(
        bars=bars,
        entry_price=50_000,
        stop_price=47_000,
        atr_at_entry=1_000,
        trail_mult=2.5,
        entry_date="2026-01-02",
    )
    assert result.status == "PENDING"
    assert result.suspended_days == 1
