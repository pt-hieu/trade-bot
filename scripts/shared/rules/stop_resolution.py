"""Stop-price resolution for HOLD/EVALUATE/TRIM/EXIT recommendation rows.

Single source of truth for answering "what stop price should this rec carry?"
when the LLM layer forgot to emit one. Called at rec-build time in
`scripts/pipeline/recommendation_builder.py` to backfill
`daily_recommendations.stop_price_vnd` for any rec covering a held position.

Separate from `shared/rules/exit_strategy.py::ExitStrategy.alert_condition()`
— that polymorphism lives at live-breach-evaluation time. This module
answers the orthogonal question of stop *selection* at persistence
boundaries.

Pure deterministic Python: no async, no DB, no LLM.

Precedence (first match wins):
    1. ATR_TRAIL strategy + active atr_trail_state  → TRAIL price
    2. Open SWING holding with breakeven_stop       → holding.breakeven_stop
    3. Open LONGTERM holding with catastrophic_stop → holding.catastrophic_stop
    4. Brief-explicit stop (fresh BUY not yet held) → brief_stop_vnd
    5. None                                         → None (fail-loud at caller)

The ATR trail precedes the SWING breakeven so that once a
trend/breakout/momentum position has locked a trail above entry, the rec
surfaces the trail rather than a stale breakeven.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from shared.rules.exit_strategy import ATR_TRAIL_STRATEGIES, ExitState

StopSource = Literal[
    "BREAKEVEN_HOLDING",
    "CATASTROPHIC_FLOOR",
    "ATR_TRAIL",
    "BRIEF_EXPLICIT",
]

PlanType = Literal["SWING", "LONGTERM"]


class StopResolutionInput(TypedDict, total=False):
    """Narrow view of a `portfolio_holdings` slice used by `resolve_stop_for_rec`.

    Distinct from the canonical `shared.neon.HoldingData` — the resolver
    only reads four fields and tolerates a stop being absent, while the
    canonical type requires `breakeven_stop: int` and a full slice shape.
    The adapter in `pipeline/recommendation_builder.py::_holding_data_from_slice`
    projects canonical holdings into this shape.
    """

    ticker: str
    plan_type: PlanType
    breakeven_stop: int | None
    catastrophic_stop: int | None


@dataclass(frozen=True)
class ResolvedStop:
    """Output of `resolve_stop_for_rec` — the authoritative stop for a rec."""

    price_vnd: int
    source: StopSource
    plan_type: PlanType | None


def _is_atr_trail(strategy: str | None) -> bool:
    return bool(strategy) and strategy.upper() in ATR_TRAIL_STRATEGIES  # type: ignore[union-attr]


def resolve_stop_for_rec(
    *,
    plan_type: PlanType | None,
    holding: StopResolutionInput | None,
    brief_stop_vnd: int | None,
    atr_trail_state: ExitState | None,
) -> ResolvedStop | None:
    """Resolve the authoritative stop for a rec.

    Returns None when no precedence tier produces a stop. Callers own the
    fail-loud log for held SWING positions — they carry the ticker context
    and the rec source needed for a useful error.
    """
    if atr_trail_state is not None and _is_atr_trail(atr_trail_state.get("strategy")):
        trail_price = atr_trail_state.get("stop_price")
        if isinstance(trail_price, int) and trail_price > 0:
            return ResolvedStop(
                price_vnd=trail_price,
                source="ATR_TRAIL",
                plan_type=plan_type,
            )

    if holding is not None:
        holding_plan = holding.get("plan_type") or plan_type
        breakeven = holding.get("breakeven_stop")
        catastrophic = holding.get("catastrophic_stop")

        if holding_plan == "SWING" and isinstance(breakeven, int) and breakeven > 0:
            return ResolvedStop(
                price_vnd=breakeven,
                source="BREAKEVEN_HOLDING",
                plan_type="SWING",
            )
        if holding_plan == "LONGTERM" and isinstance(catastrophic, int) and catastrophic > 0:
            return ResolvedStop(
                price_vnd=catastrophic,
                source="CATASTROPHIC_FLOOR",
                plan_type="LONGTERM",
            )

    if isinstance(brief_stop_vnd, int) and brief_stop_vnd > 0:
        return ResolvedStop(
            price_vnd=brief_stop_vnd,
            source="BRIEF_EXPLICIT",
            plan_type=plan_type,
        )

    return None


__all__ = [
    "PlanType",
    "ResolvedStop",
    "StopResolutionInput",
    "StopSource",
    "resolve_stop_for_rec",
]
