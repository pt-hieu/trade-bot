"""Computed-field tests for watchlist_update.StockScore (SWI-295).

`score` is a Pydantic v2 @computed_field derived from `(+N)`/`(-N)` tags
in `reasons`. The LLM never authors it, so there is no coerced-emit to
test; we test the computation contract instead.
"""

from __future__ import annotations

from agents.watchlist_update import StockScore


def test_computed_field_sums_tags() -> None:
    score = StockScore(
        ticker="FPT",
        sector="Tech",
        confidence="high",
        reasons=["good earnings (+10)", "strong momentum (+15)", "rich valuation (-5)"],
    )
    assert score.score == 20


def test_computed_field_handles_no_tags() -> None:
    score = StockScore(
        ticker="FPT",
        sector="Tech",
        confidence="medium",
        reasons=["plain text with no tag"],
    )
    assert score.score == 0


def test_computed_field_serializes_in_model_dump() -> None:
    score = StockScore(
        ticker="FPT",
        sector="Tech",
        confidence="high",
        reasons=["earnings (+10)"],
    )
    dumped = score.model_dump()
    assert dumped["score"] == 10


def test_constructor_ignores_score_kwarg() -> None:
    """Pydantic v2 — extra `score` kwarg is silently dropped; computed_field wins.

    LLM-emitted `score` (if any) cannot override the deterministic computation;
    that's the SWI-295 invariant.
    """
    payload = {
        "ticker": "FPT",
        "sector": "Tech",
        "score": 50,
        "confidence": "high",
        "reasons": ["foo (+10)"],
    }
    score = StockScore.model_validate(payload)
    assert score.score == 10  # NOT 50
