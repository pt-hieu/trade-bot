"""Sector analysis structured output models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from shared.rules.plan_shape import PlanShape

from .belief_models import AggregatedBelief


class TickerSignal(BaseModel):
    """Signal for a single stock from sector analysis."""

    ticker: str
    signal: Literal["BUY", "WATCH", "WAIT", "AVOID"]
    note: str = Field(max_length=200)  # brief reasoning (1-2 sentences)
    confidence: Literal["HIGH", "MEDIUM", "LOW"] | None = None  # calibrated signal strength
    key_risk: str | None = Field(default=None, max_length=200)  # strongest counter-argument
    # WATCH/WAIT carry a structured re-evaluation trigger labeled by the LLM.
    # Python computes the price levels; the model only labels shape.
    plan_shape: PlanShape | None = None

    @model_validator(mode="after")
    def _default_plan_shape_for_watch(self) -> TickerSignal:
        # Fail-closed: WATCH/WAIT default plan_shape=NONE so the builder's
        # classifier fallback runs cleanly without a KeyError.
        if self.signal in ("WATCH", "WAIT") and self.plan_shape is None:
            self.plan_shape = "NONE"
        return self


class SectorAnalysisResult(BaseModel):
    """Structured sector analysis with per-ticker signals."""

    signals: list[TickerSignal] = Field(max_length=8)  # split_sectors caps at 5
    summary: str = Field(max_length=500)  # sector-level overview (2-3 sentences)
    # HOOK-ALLOW: empty-output-permitted (sectors without aggregated beliefs are valid — coverage check elsewhere)
    beliefs: list[AggregatedBelief] = Field(default_factory=list, max_length=8)
