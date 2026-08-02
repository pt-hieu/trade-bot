"""Parity test: skip_selector output == recommendation_builder SKIP_THESE output.

Both the morning brief renderer and the daily_recommendations DB writer go
through `select_skip_tickers` with identical inputs. This test asserts the
two never drift. If the test fails, the invariant that underpins
MON-2026-04-23-001 (brief and DB list the same SKIP tickers every run) has
been broken and must be restored before merge.
"""

from __future__ import annotations

from agents.retro.parser import SECTION_SKIP_THESE
from pipeline.recommendation_builder import build_structured_recommendations
from shared.rules.skip_selector import select_skip_tickers


def _fixture_inputs():
    sector_signals = [
        {
            "ticker": "MBB",
            "signal": "AVOID",
            "note": "Foreign selling accelerating",
            "key_risk": "Bank index rolling over",
            "confidence": "HIGH",
        },
        {
            "ticker": "NLG",
            "signal": "SKIP",
            "note": "Revenue pressure",
            "confidence": "MEDIUM",
        },
        {
            "ticker": "PVI",
            "signal": "AVOID",
            "note": "Sector headwind",
            "confidence": "MEDIUM",
        },
        # A BUY signal — must be excluded from SKIP
        {"ticker": "FPT", "signal": "BUY", "note": "Breakout", "confidence": "HIGH"},
        # A WATCH signal — must be excluded from SKIP
        {"ticker": "HPG", "signal": "WATCH", "note": "Range", "confidence": "LOW"},
    ]
    gated_tickers = [
        {
            "ticker": "ABC",
            "gated_by": "bear_advocate",
            "bear_arguments": ["Earnings miss", "Valuation stretched"],
        },
    ]
    holdings = [
        # Ticker in holdings must be excluded from SKIP even if sector says AVOID.
        {"ticker": "VIC", "plan_type": "SWING", "avg_cost": 45000},
    ]
    return sector_signals, gated_tickers, holdings


def test_select_skip_tickers_matches_rec_builder_skip_section() -> None:
    sector_signals, gated_tickers, holdings = _fixture_inputs()
    # Add a held ticker that has a sector AVOID signal — rec-builder
    # excludes via seen_by_section[MY_HOLDINGS], selector excludes via
    # the exclusions argument. Both must behave identically.
    sector_signals.append(
        {"ticker": "VIC", "signal": "AVOID", "note": "Held but weak", "confidence": "LOW"}
    )

    picks: list[dict] = []  # no TOP PICKS in this fixture
    recs = build_structured_recommendations(
        pre_computed_picks=picks,
        position_alerts={"alerts": []},
        sector_signals=sector_signals,
        holdings=holdings,
        trading_mode=None,
        gated_tickers=gated_tickers,
    )
    rec_skip_set = {r["ticker"] for r in recs if r["section"] == SECTION_SKIP_THESE}

    exclusions = {(h.get("ticker") or "").upper() for h in holdings}
    entries = select_skip_tickers(sector_signals, gated_tickers, exclusions)
    selector_skip_set = {entry["ticker"] for entry in entries}

    assert rec_skip_set == selector_skip_set, (
        f"Parity broken: rec-builder SKIP={sorted(rec_skip_set)} vs "
        f"selector SKIP={sorted(selector_skip_set)}. A divergence here means "
        f"the brief renderer and the DB rec table will emit different SKIP lists."
    )
    # Confirm the basics — SKIP contains AVOID/SKIP sector tickers + gated,
    # excluding holdings, BUY, and WATCH.
    assert "MBB" in selector_skip_set
    assert "NLG" in selector_skip_set
    assert "PVI" in selector_skip_set
    assert "ABC" in selector_skip_set
    assert "FPT" not in selector_skip_set
    assert "HPG" not in selector_skip_set
    assert "VIC" not in selector_skip_set


def test_select_skip_tickers_handles_empty_inputs() -> None:
    assert select_skip_tickers(None, None, set()) == []
    assert select_skip_tickers([], [], set()) == []


def test_select_skip_tickers_dedupes_sector_then_gated() -> None:
    sector_signals = [{"ticker": "XYZ", "signal": "AVOID", "note": "sector AVOID"}]
    gated_tickers = [{"ticker": "XYZ", "bear_arguments": ["gated"]}]
    entries = select_skip_tickers(sector_signals, gated_tickers, set())
    assert len(entries) == 1
    assert entries[0]["source"] == "sector_signals"  # sector wins over gated on dedup
