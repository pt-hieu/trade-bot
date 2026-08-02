"""Shared types + constants for catalyst-override package."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from ..catalyst_lifecycle import LifecycleState

# Catalyst-type enum kept in sync with the DB CHECK constraint and with
# ``agents.catalysts.CatalystType``. Duplicated here to avoid a cycle
# (agents depends on shared.rules, not vice versa).
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

# Lifecycle states a CatalystBoost can carry. Extends the DB-facing
# ``LifecycleState`` with boost-only values ``STATIC`` (non-phased catalyst)
# and ``MACRO_BLANKET`` (VN-INDEX fan-out boost) so pyright can statically
# reject a typo in either callsite.
BoostLifecycle = LifecycleState | Literal["STATIC", "MACRO_BLANKET"]


class CatalystInput(TypedDict):
    """Typed input for catalyst override logic. Subset of DB catalyst row."""

    catalyst_key: str
    event: str
    impact: str  # POSITIVE, NEGATIVE, NEUTRAL
    confidence: str  # HIGH, MEDIUM, LOW
    affected_tickers: list[str]
    phases: dict | None
    supporting_article_count: int
    catalyst_type: CatalystType | str
    expected_status: NotRequired[str]


class CatalystBoost(TypedDict):
    """A ticker boosted by an active positive catalyst."""

    ticker: str
    catalyst_key: str
    catalyst_event: str
    phase_lifecycle: BoostLifecycle
    phase_name: str
    reason: str
    rr_floor_adjustment: float


GeoLabel = Literal["GEO_BENEFICIARY", "GEO_VICTIM", "GEO_EXPOSED", "GEO_MIXED"]


# Stacked-positive-catalyst threshold. Used by the GEO_MIXED tie-break
# (``classify_geo_label``) AND by the per-candidate `stacked_shock_relief`
# gate flag (L2, 2026-04-27). Single source of truth — both consumers
# import ``STACKED_POSITIVE_MIN_CATALYSTS``.
STACKED_POSITIVE_MIN_CATALYSTS: int = 2
_MIXED_ELIGIBLE_CONFIDENCE: frozenset[str] = frozenset({"HIGH", "MEDIUM"})
