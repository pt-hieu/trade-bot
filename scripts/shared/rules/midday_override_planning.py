"""Deterministic plan_type inference for midday overrides.

VND-price unit-shift recovery moved to ``shared/rules/vnd_price_clamp.py``
in SWI-184 so siblings (longterm, beliefs, afternoon plan) can reuse it.
This module re-exports ``normalize_vnd_price`` for ONE merge cycle so
in-flight callers don't break; follow-up SWI removes the shim and points
every consumer at the new module path.

What stays here: ``infer_plan_type(ticker, dual_listed_tickers, holding_scope)``
returns ``"SWING" | "LONG_TERM" | "BOTH"``. Pattern from
``shared/rules/catalyst_classifier.py`` — deterministic, no LLM. Reused
at the persistence boundary (``shared/neon/insert_content.py``) as
defense-in-depth so dicts built without going through the Pydantic model
still land valid rows.
"""

from __future__ import annotations

from typing import Literal

# Re-export shim — remove after one merge cycle (SWI-184 follow-up).
from shared.rules.vnd_price_clamp import normalize_vnd_price

__all__ = ["PlanType", "infer_plan_type", "normalize_vnd_price"]

PlanType = Literal["SWING", "LONG_TERM", "BOTH"]


def infer_plan_type(
    ticker: str,
    dual_listed_tickers: frozenset[str] | set[str],
    holding_scope: str | None = None,
) -> PlanType:
    """Return the plan_type slice the midday override targets.

    Rules (deterministic, no LLM):
      * If ticker is dual-listed (in ``portfolio_holdings`` as both SWING
        and LONGTERM rows) AND no ``holding_scope`` hint → ``"BOTH"``.
      * If dual-listed AND ``holding_scope`` is one of SWING/LONGTERM →
        return that scope.
      * If single-listed → return the actual scope; default ``"SWING"``
        when scope unknown (matches midday legacy default).
    """
    ticker_upper = ticker.upper()
    scope_norm = (holding_scope or "").strip().upper()
    # Accept "LONGTERM" alias for "LONG_TERM" — DB column has historically
    # used both spellings; canonicalize to "LONG_TERM".
    if scope_norm == "LONGTERM":
        scope_norm = "LONG_TERM"

    is_dual = ticker_upper in dual_listed_tickers

    if is_dual:
        if scope_norm in ("SWING", "LONG_TERM"):
            return scope_norm  # type: ignore[return-value]
        return "BOTH"

    if scope_norm in ("SWING", "LONG_TERM"):
        return scope_norm  # type: ignore[return-value]
    return "SWING"
