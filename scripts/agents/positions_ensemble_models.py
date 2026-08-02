"""
Pydantic models for the positions ensemble analyst committee.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .belief_models import TickerBelief


class AnalystView(BaseModel):
    """Single analyst's view on one position."""

    ticker: str
    action: str  # EXIT, HOLD, TRIM, ADD, EVALUATE
    confidence: int  # 1-10
    reasoning: str = Field(max_length=300)  # 2-3 sentences max
    counter_thesis: str | None = Field(default=None, max_length=200)  # 1 sentence
    belief: TickerBelief  # REQUIRED — see BELIEF OUTPUT FORMAT in agent yaml


class AnalystReport(BaseModel):
    """Full report from one analyst covering all positions."""

    views: list[AnalystView]
    summary: str = Field(max_length=500)  # 2-3 sentences overview
