"""Pydantic schemas for the catalyst-discovery agent.

CatalystType + CatalystFactor + CatalystDriver are kept in sync with DB
CHECK constraints (catalysts_factors_allowed migration 322 + the
catalyst_type VARCHAR(50) column). Use Literal so pyright + pydantic
reject typos at the producer.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, ValidationInfo, field_validator

from pipeline.types import CatalystFactor
from shared.post_llm_types import CatalystDriver, CatalystReason
from shared.rules.geopolitical import validate_phase_shape

_CONFIDENCE_RANKS = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

CatalystType = Literal[
    "regulatory",
    "earnings",
    "macro",
    "rating",
    "geopolitical",
    "corporate_action",
    "legal",
    "commodity",
]

DetectionKeyword = Annotated[
    str,
    StringConstraints(min_length=3, strip_whitespace=True, to_lower=True),
]


def _confidence_rank(confidence: str) -> int:
    """Numeric rank for confidence level comparison."""
    return _CONFIDENCE_RANKS.get(confidence, 0)


class CatalystAddition(BaseModel):
    """A new catalyst discovered from news.

    See module docstring for ticker discipline + corroboration semantics.
    """

    event: str
    affected: list[str]
    expected: str
    impact: str  # POSITIVE, NEGATIVE, NEUTRAL
    confidence: str  # HIGH, MEDIUM, LOW
    source: str
    catalyst_type: CatalystType
    driver: CatalystDriver
    phases: dict[str, dict[str, str]] | None = None
    supporting_article_ids: list[str] | None = None
    official_document_flag: bool = False
    catalyst_factors: list[CatalystFactor] = []
    detection_keywords: list[DetectionKeyword] = Field(..., min_length=2, max_length=6)

    @field_validator("phases")
    @classmethod
    def _validate_phases(
        cls, value: dict[str, dict[str, str]] | None
    ) -> dict[str, dict[str, str]] | None:
        if value is None:
            return None
        validate_phase_shape(value)
        return value


class CatalystUpdate(BaseModel):
    """An update to an existing catalyst.

    `new_value` is widened to accept dict/list so the agent can push phase
    transitions instead of being limited to string-only field tweaks.
    """

    catalyst_id: str
    field: str
    new_value: str | dict[str, object] | list[object]
    reason: str

    @field_validator("new_value")
    @classmethod
    def _validate_phases_value(
        cls,
        value: str | dict[str, object] | list[object],
        info: ValidationInfo,
    ) -> str | dict[str, object] | list[object]:
        """When ``field='phases'``, validate the dict shape."""
        field_name = info.data.get("field") if info.data else None
        if field_name != "phases":
            return value
        if not isinstance(value, dict):
            raise ValueError("field='phases' requires new_value to be a dict")
        validate_phase_shape(value)
        return value


class CatalystCompletion(BaseModel):
    """A catalyst that has been completed."""

    catalyst_id: str
    outcome: str
    actual_date: str


class CatalystDiscovery(BaseModel):
    """Complete catalyst discovery result."""

    additions: list[CatalystAddition]
    updates: list[CatalystUpdate]
    completions: list[CatalystCompletion]


__all__ = [
    "CatalystAddition",
    "CatalystCompletion",
    "CatalystDiscovery",
    "CatalystDriver",
    "CatalystFactor",
    "CatalystReason",
    "CatalystType",
    "CatalystUpdate",
    "DetectionKeyword",
    "_CONFIDENCE_RANKS",
    "_confidence_rank",
]
