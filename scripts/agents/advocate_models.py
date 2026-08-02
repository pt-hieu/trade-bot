"""
Advocate reviewer output models.

Bull and bear reviewers produce AdvocateReport containing per-ticker
AdvocateReview verdicts. These sit downstream of beliefs — reviewers
consume aggregated beliefs but do not produce new ones.
"""

from typing import Literal

from pydantic import BaseModel, Field


class AdvocateReview(BaseModel):
    """Single ticker review from an advocate reviewer."""

    ticker: str
    verdict: Literal["AGREE", "CHALLENGE", "MIXED"] = Field(
        description=(
            "AGREE: evidence strongly supports the pick. "
            "CHALLENGE: genuine counter-evidence or blind spots found. "
            "MIXED: some support but notable concerns."
        )
    )
    confidence: float = Field(description="Decimal 0.0-1.0. How confident in this review verdict.")
    key_arguments: list[str] = Field(
        description="Specific evidence supporting the verdict. Cite data, not generalities."
    )
    blind_spots: list[str] | None = Field(
        default=None,
        description="What the original analysis might be missing, even on AGREE verdicts.",
    )


class AdvocateReport(BaseModel):
    """Batch review of all pick candidates from one advocate perspective."""

    reviews: list[AdvocateReview]


def _format_review_side(label: str, review: dict, lines: list[str]) -> None:
    """Format one side (bull or bear) of an advocate review into lines."""
    verdict = review.get("verdict") or "N/A"
    confidence = review.get("confidence") or 0
    lines.append(f"{label}: {verdict} (confidence {confidence:.1f})")
    if verdict == "CHALLENGE":
        for argument in review.get("key_arguments") or []:
            lines.append(f"  - {argument}")


def format_advocate_reviews(reviews: dict) -> str:
    """Format bull/bear advocate reviews for synthesis context injection.

    Args:
        reviews: {"bull": [review_dicts], "bear": [review_dicts]}

    Returns:
        Formatted string for synthesis context. Empty string if no reviews.
    """
    bull_reviews = reviews.get("bull") or []
    bear_reviews = reviews.get("bear") or []

    if not bull_reviews and not bear_reviews:
        return ""

    # Index reviews by ticker for side-by-side comparison
    bull_by_ticker = {review.get("ticker"): review for review in bull_reviews}
    bear_by_ticker = {review.get("ticker"): review for review in bear_reviews}
    all_tickers = list(
        dict.fromkeys(
            [review.get("ticker") for review in bull_reviews]
            + [review.get("ticker") for review in bear_reviews]
        )
    )

    lines = []
    for ticker in all_tickers:
        if not ticker:
            continue
        bull = bull_by_ticker.get(ticker)
        bear = bear_by_ticker.get(ticker)

        lines.append(f"### {ticker}")

        if bull:
            _format_review_side("Bull", bull, lines)
        if bear:
            _format_review_side("Bear", bear, lines)

        # Surface blind spots from either reviewer
        blind_spots = []
        for review in [bull, bear]:
            if review:
                for spot in review.get("blind_spots") or []:
                    if spot not in blind_spots:
                        blind_spots.append(spot)
        if blind_spots:
            lines.append("Blind spots:")
            for spot in blind_spots:
                lines.append(f"  - {spot}")

        lines.append("")

    return "\n".join(lines)
