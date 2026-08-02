"""Ticker briefing surfaces raw ADX + catalyst attachment for sector prompts."""

from __future__ import annotations

from pipeline.context_blocks_ticker import format_ticker_briefing, format_ticker_briefings
from shared.rules.catalyst_override import CatalystBoost


def _boost(ticker: str) -> CatalystBoost:
    return CatalystBoost(
        ticker=ticker,
        catalyst_key="ftse_2026",
        catalyst_event="FTSE Emerging Market upgrade approaching",
        phase_lifecycle="APPROACHING_RESOLUTION",
        phase_name="immediate_shock",
        reason="upgrade decision within 3 days",
    )


def test_briefing_exposes_raw_adx_strength():
    tech = {"close": 45_000, "adx": 28.5, "adx_dmp": 22.1, "adx_dmn": 14.3}
    out = format_ticker_briefing(ticker="VHM", technicals=tech)
    assert "ADX: 28" in out
    assert "strong" in out
    assert "DM+/DM-: 22/14 (bullish)" in out


def test_briefing_tags_weak_adx_without_strong_marker():
    tech = {"close": 45_000, "adx": 18.0, "adx_dmp": 12.0, "adx_dmn": 15.0}
    out = format_ticker_briefing(ticker="VHM", technicals=tech)
    assert "ADX: 18" in out
    assert "strong" not in out
    assert "DM+/DM-: 12/15 (bearish)" in out


def test_briefing_includes_catalyst_line_when_boost_present():
    tech = {"close": 45_000, "adx": 28.0, "adx_dmp": 20.0, "adx_dmn": 14.0}
    out = format_ticker_briefing(ticker="VHM", technicals=tech, catalyst_boost=_boost("VHM"))
    assert "CATALYST: ftse_2026" in out
    assert "lifecycle=APPROACHING_RESOLUTION" in out
    assert "FTSE Emerging Market upgrade approaching" in out


def test_briefing_omits_catalyst_line_when_no_boost():
    out = format_ticker_briefing(ticker="VHM", technicals={"close": 45_000})
    assert "CATALYST:" not in out


def test_batch_briefings_attach_catalyst_by_upper_ticker():
    tech = {
        "VHM": {"close": 45_000, "adx": 28.0, "adx_dmp": 20.0, "adx_dmn": 14.0},
        "VIC": {"close": 40_000, "adx": 22.0, "adx_dmp": 18.0, "adx_dmn": 15.0},
    }
    boosted = {"VHM": _boost("VHM")}
    out = format_ticker_briefings(
        tickers=["VHM", "VIC"],
        technicals=tech,
        catalyst_boosted=boosted,
    )
    assert "VHM" in out and "CATALYST: ftse_2026" in out
    # VIC block should not carry the catalyst line
    vic_block = out.split("## VIC")[1] if "## VIC" in out else ""
    assert "CATALYST:" not in vic_block
