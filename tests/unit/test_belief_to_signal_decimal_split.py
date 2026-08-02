"""Test that the belief_to_signal excerpt keeps decimal points intact.

A naive ``reasoning.split(".", 1)[0]`` truncates excerpts at decimal
points — "RSI 55.3 and above 20DMA" becomes "RSI 55". The regex split
keeps the number intact.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.rules.belief_to_signal import derive_signal_from_views


@dataclass
class _FakeView:
    ticker: str
    signal: str
    confidence: int
    reasoning: str


def test_excerpt_keeps_decimal_point_intact():
    view = _FakeView(
        ticker="FPT",
        signal="BUY",
        confidence=8,
        reasoning="RSI 55.3 and above 20DMA — momentum confirmed.",
    )
    signal, note = derive_signal_from_views([view])
    assert signal == "BUY"
    # Excerpt must NOT cut at "55" — the decimal point must survive.
    assert "55.3" in note
    assert "[DERIVED_FROM_BELIEFS]" in note


def test_excerpt_splits_at_sentence_end():
    view = _FakeView(
        ticker="VCB",
        signal="WATCH",
        confidence=6,
        reasoning="Price near 95k support. Volume declining.",
    )
    _, note = derive_signal_from_views([view])
    # Splits at "95k support." → excerpt is the first sentence only.
    assert "95k support" in note
    assert "Volume declining" not in note


def test_excerpt_handles_parenthetical_decimal():
    view = _FakeView(
        ticker="TCB",
        signal="BUY",
        confidence=7,
        reasoning="Conviction (0.45) with MACD cross confirmed.",
    )
    _, note = derive_signal_from_views([view])
    assert "(0.45)" in note
