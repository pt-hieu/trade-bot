"""Auto-injection guardrails for midday recommendation overrides."""

from __future__ import annotations

import logging

from .models import RecommendationOverride

logger = logging.getLogger(__name__)


def resolve_plan_type_for_ticker(
    ticker: str,
    holdings_by_ticker: dict[str, list[dict]] | None,
) -> str | None:
    """Resolve plan_type from holdings by ticker.

    Single SWING/LONGTERM holding -> that plan_type.
    Dual-listed (SWING + LONGTERM) -> "BOTH".
    Not held -> None (caller decides whether to raise).

    Freshness contract (SWI-254): callers MUST source `holdings_by_ticker`
    from a `get_holdings_async()` call within the same midday request.
    A stale broker sync will silently miscoalesce — resolution is only as
    fresh as the snapshot.
    """
    if not holdings_by_ticker:
        return None
    rows = holdings_by_ticker.get(ticker.upper()) or holdings_by_ticker.get(ticker) or []
    plan_types = {(row.get("plan_type") or "").upper() for row in rows if row.get("plan_type")}
    plan_types.discard("")
    if not plan_types:
        return None
    if len(plan_types) >= 2:
        return "BOTH"
    return next(iter(plan_types))


def _append_override(
    qualitative,
    *,
    ticker: str,
    plan_type: str | None,
    morning_action: str,
    reason: str,
    revised_stop: float | None = None,
    holdings_by_ticker: dict[str, list[dict]] | None = None,
) -> None:
    """Append a CANCEL override for (ticker, plan_type) if not already present.

    Dedupe key is (ticker, plan_type) so a STOP_BREACHED CANCEL at ticker-scope
    and a per-plan MAX LOSS CANCEL can coexist on a dual-listed ticker.
    """
    resolved_plan = plan_type
    if resolved_plan is None:
        resolved_plan = resolve_plan_type_for_ticker(ticker, holdings_by_ticker)
    normalised_plan = (resolved_plan or "").upper() or None
    for existing in qualitative.recommendation_overrides:
        existing_plan = (existing.plan_type or "").upper() or None
        if existing.ticker == ticker and existing_plan == normalised_plan:
            return
    qualitative.recommendation_overrides.append(
        RecommendationOverride(
            ticker=ticker,
            plan_type=normalised_plan,
            morning_action=morning_action,
            midday_status="CANCEL",
            reason=reason,
            revised_stop=revised_stop,
        )
    )
    scope = f" {normalised_plan}" if normalised_plan else ""
    logger.warning("Auto-injected CANCEL override for %s%s", ticker, scope)
