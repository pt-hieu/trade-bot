"""Pydantic schemas for the midday agent: RecommendationOverride, AfternoonAction, MiddayQualitative."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, model_validator

from shared.neon import AfternoonActionConfidence, AfternoonActionKind
from shared.rules.vnd_price_clamp import clamp_vnd_field

MiddayStatus = Literal["CONFIRM", "ADJUST", "CANCEL"]

# Substrings in `reason` that imply the cancel is driven by a stop-level
# decision. Matched against the casefolded `reason`.
STOP_REASON_TOKENS: tuple[str, ...] = ("stop",)

_PRICE_TOKEN_RE = re.compile(r"\b\d{1,3}(?:[.,]\d{1,3})?k?\b")


def override_reason_mentions_stop(reason: str | None) -> bool:
    """True when a midday override rationale cites a stop-level decision."""
    if not reason:
        return False
    lowered = reason.casefold()
    return any(token in lowered for token in STOP_REASON_TOKENS)


class RecommendationOverride(BaseModel):
    """Per-ticker midday status vs morning recommendation.

    `plan_type` is REQUIRED when the ticker is dual-listed in `portfolio_holdings`
    (SWING + LONGTERM rows) so the override scopes to the correct slice.
    """

    ticker: str
    morning_action: str
    midday_status: MiddayStatus
    reason: str
    plan_type: str | None = None
    revised_entry: float | None = None
    revised_stop: float | None = None
    revised_target: float | None = None

    @model_validator(mode="after")
    def _normalize_revised_vnd_fields(self) -> RecommendationOverride:
        """Catch the LLM dropped-zeros defect (44.91 vs 44910)."""
        for field_name in ("revised_entry", "revised_stop", "revised_target"):
            clamp_vnd_field(self, field_name, self.reason, agent="midday_override")
        return self

    @model_validator(mode="after")
    def _require_stop_when_cancelling_on_stop(self) -> RecommendationOverride:
        if self.midday_status != "CANCEL":
            return self
        if override_reason_mentions_stop(self.reason) and self.revised_stop is None:
            raise ValueError(
                "RecommendationOverride: midday_status='CANCEL' with a stop-"
                "referencing reason requires `revised_stop` to be populated. "
                f"ticker={self.ticker!r} reason={self.reason!r}"
            )
        return self


class AfternoonAction(BaseModel):
    """Structured afternoon plan entry (migration 316)."""

    ticker: str | None = None
    action: AfternoonActionKind
    confidence: AfternoonActionConfidence
    reason: str
    evidence_price_vnd: int | None = None

    @model_validator(mode="after")
    def _normalize_evidence_price_vnd(self) -> AfternoonAction:
        """Catch dropped-zeros defect (44 → 44000) on evidence_price_vnd."""
        clamp_vnd_field(self, "evidence_price_vnd", self.reason, agent="midday_afternoon")
        return self

    @model_validator(mode="after")
    def _require_evidence_when_reason_cites_price(self) -> AfternoonAction:
        if self.ticker or self.evidence_price_vnd is not None:
            return self
        if _PRICE_TOKEN_RE.search(self.reason or ""):
            raise ValueError(
                "AfternoonAction: reason cites a price token but ticker is "
                "unset and evidence_price_vnd is null — populate "
                "evidence_price_vnd with the cited price (VND integer)."
            )
        return self


class MiddayQualitative(BaseModel):
    """LLM-generated qualitative analysis. No numeric fields that could hallucinate."""

    morning_reflection: str
    afternoon_plan: list[AfternoonAction] = []
    afternoon_note: str | None = None
    capital_note: str
    recommendation_overrides: list[RecommendationOverride] = []
