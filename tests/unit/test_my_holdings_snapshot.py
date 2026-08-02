"""SWI-121: MY HOLDINGS carries a "Prices last written" header + ellipsis-truncated thesis."""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline.rendering.models import HoldingAction
from pipeline.rendering.my_holdings import render_my_holdings


def _action(ticker: str = "FPT") -> HoldingAction:
    return HoldingAction(
        ticker=ticker,
        verb="HOLD",
        qty_pct=100,
        urgency="MEDIUM",
        entry_price_vnd=100_000,
        current_price_vnd=105_000,
        pnl_pct=5.0,
        stop_price_vnd=95_000,
        rationale="No action required today",
    )


def test_render_includes_prices_last_written_header() -> None:
    out = render_my_holdings(
        [_action()],
        {"FPT": "Thesis text."},
        snapshot_at=datetime(2026, 5, 12, 23, 12, tzinfo=UTC),
    )
    assert "Prices last written: 2026-05-12 23:12 UTC" in out


def test_render_omits_header_when_snapshot_none() -> None:
    out = render_my_holdings([_action()], {"FPT": "Thesis text."})
    assert "Prices last written" not in out


def test_thesis_truncates_with_ellipsis_at_600() -> None:
    long_thesis = "alpha bravo charlie " * 100  # 2000 chars
    out = render_my_holdings([_action()], {"FPT": long_thesis})
    thesis_line = [line for line in out.splitlines() if "alpha bravo" in line][0]
    # 2-char indent + payload
    assert len(thesis_line.strip()) <= 600
    assert thesis_line.rstrip().endswith("...")


def test_short_thesis_passes_through_without_ellipsis() -> None:
    out = render_my_holdings([_action()], {"FPT": "Short thesis."})
    assert "Short thesis." in out
    assert "..." not in out.split("Short thesis.")[1].split("\n")[0]
