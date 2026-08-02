"""verb_mismatches() — pure-function tests.

Mirrors the structural-gate enforced inside ``synthesis_writers._run_holdings_writer``.
The deterministic header verb (HoldingAction.bullet_verb) is authoritative;
the thesis paragraph MUST start with the same verb. Anything else is the
FPT 2026-05-07 class of brief-shipping defect.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.rules.synthesis_verb_match import verb_mismatches


@dataclass(frozen=True)
class _Thesis:
    ticker: str
    paragraph: str


def test_match_paragraph_starts_with_expected_verb_returns_no_mismatch() -> None:
    theses = [_Thesis("FPT", "HOLD — thesis intact, deeper consolidation OK.")]
    assert verb_mismatches(theses, {"FPT": "HOLD"}) == []


def test_mismatch_paragraph_uses_dissenting_verb() -> None:
    theses = [_Thesis("FPT", "TRIM — thesis intact... position reduction.")]
    assert verb_mismatches(theses, {"FPT": "HOLD"}) == [("FPT", "TRIM", "HOLD")]


def test_paragraph_without_recognized_leading_verb_is_skipped() -> None:
    theses = [_Thesis("FPT", "Strong fundamentals — keep position.")]
    assert verb_mismatches(theses, {"FPT": "HOLD"}) == []


def test_unknown_ticker_in_expected_dict_is_skipped() -> None:
    theses = [_Thesis("XYZ", "TRIM — exit slowly.")]
    assert verb_mismatches(theses, {"FPT": "HOLD"}) == []


def test_case_insensitive_match() -> None:
    theses = [_Thesis("fpt", "hold — thesis intact.")]
    assert verb_mismatches(theses, {"FPT": "HOLD"}) == []


def test_evaluate_verb_supported() -> None:
    theses = [_Thesis("VHM", "EVALUATE — wait for catalyst.")]
    assert verb_mismatches(theses, {"VHM": "EVALUATE"}) == []


def test_multiple_mismatches_returned() -> None:
    theses = [
        _Thesis("FPT", "TRIM — should be HOLD."),
        _Thesis("VHM", "EXIT — should be ADD."),
        _Thesis("ACV", "HOLD — correct."),
    ]
    expected = {"FPT": "HOLD", "VHM": "ADD", "ACV": "HOLD"}
    result = verb_mismatches(theses, expected)
    assert ("FPT", "TRIM", "HOLD") in result
    assert ("VHM", "EXIT", "ADD") in result
    assert len(result) == 2
