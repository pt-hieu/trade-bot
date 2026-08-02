"""Sector evaluator output schema."""

from __future__ import annotations

from pydantic import BaseModel

from ..watchlist_update import StockScore


class SectorEvaluation(BaseModel):
    """Output from one sector evaluator agent."""

    sector_summary: str  # 2-3 sentences on this sector group
    hot_sectors: list[str]
    cold_sectors: list[str]
    removals: list[StockScore]
    additions: list[StockScore]
    conflicts_identified: list[str]  # enumerated signal conflicts
