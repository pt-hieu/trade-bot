"""Agent-agnostic VND-price unit-shift-recovering clamp (SWI-184).

Generalizes the midday `revised_*` defect (LLM emits ``44.91`` when the
canonical VND value is ``44910``) to every Pydantic ``*_vnd`` int/float
field in ``scripts/agents/``. Original home was
``shared/rules/midday_override_planning.py``; moved here so siblings —
``AfternoonAction.evidence_price_vnd``, ``NewStockRecommendation.suggested_entry_zone_vnd``,
``TickerBelief.price_target_vnd``, ``AggregatedBelief.price_target_vnd`` —
can reuse the same recovery without dragging the midday-only plan_type
inference along.

Contract:

    ``normalize_vnd_price(value, reason_text, *, agent, boundary)``
    returns a positive integer ``>= 1000`` or ``None``. When the LLM
    emits a sub-1000 value AND the reason text cites a 5-digit VND
    price, scale by ×1000. Else clamp the value or raise ``ValueError``
    so the agent retry surfaces.

The midday persistence boundary (``shared/neon/insert_midday.py``) keeps
calling this for defense-in-depth.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from shared.observability_post_llm import emit_rule_outcome
from shared.post_llm_types import RuleAgent, RuleBoundary, VndPriceReason

logger = logging.getLogger(__name__)

# 4- or 5-digit price token (e.g. ``44,910`` / ``44910`` / ``86000``).
# Comma-tolerant so we match both prose and numeric forms.
_FIVE_DIGIT_PRICE = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{4,5}\b")

_MIN_VND_PRICE = 1000
_MAX_VND_PRICE = 1_000_000

# Threshold below which we suspect a unit-shift (decimal-shifted ×1000).
_UNIT_SHIFT_SUSPECT_THRESHOLD = 1000


def _reason_cites_five_digit_price(reason_text: str | None) -> bool:
    if not reason_text:
        return False
    return bool(_FIVE_DIGIT_PRICE.search(reason_text))


def normalize_vnd_price(
    value: float | int | None,
    reason_text: str | None,
    *,
    agent: RuleAgent,
    boundary: RuleBoundary = "validator",
) -> int | None:
    """Return a positive integer VND price ``>= 1000`` or ``None``.

    Behaviour:
      * ``None`` input → ``None`` output (caller field is optional).
      * ``value >= 1000`` and ``<= 1_000_000`` → cast to ``int``, return.
      * ``value < 1000`` AND ``reason_text`` cites a 5-digit price →
        multiply by 1000, validate range, return as ``int``. (Catches
        the LLM dropped-zeros pattern: ``44.91`` for ``44,910``.)
      * ``value < 1000`` and no corroborating reason → emit + raise.
      * ``value > 1_000_000`` → emit + raise.

    ``agent`` tags the calling agent so downstream queries can break out
    coercion volume per-agent (midday vs longterm vs belief). ``boundary``
    tags where the call site sits so downstream queries can dedup the
    defense-in-depth pair (validator + persistence). Defaults match the
    midday primary caller for backward compatibility.

    Raises:
      ValueError when the price is out of range and the reason text does
      not justify a unit-shift correction.
    """
    if value is None:
        return None

    numeric = float(value)
    if numeric != numeric or numeric == float("inf") or numeric == float("-inf"):
        _emit_vnd_rejected(value, reason_text, agent, boundary, "non_finite")
        raise ValueError(f"normalize_vnd_price: non-finite value {value!r}")

    if numeric <= 0:
        _emit_vnd_rejected(value, reason_text, agent, boundary, "non_positive")
        raise ValueError(f"normalize_vnd_price: non-positive value {value!r}")

    # Branch 1: in-range integer-shaped value.
    if numeric >= _MIN_VND_PRICE and numeric <= _MAX_VND_PRICE:
        return int(round(numeric))

    # Branch 2: suspect unit-shift (LLM dropped 3 zeros).
    if numeric < _UNIT_SHIFT_SUSPECT_THRESHOLD:
        if _reason_cites_five_digit_price(reason_text):
            shifted = numeric * 1000.0
            if shifted < _MIN_VND_PRICE or shifted > _MAX_VND_PRICE:
                _emit_vnd_rejected(value, reason_text, agent, boundary, "above_max")
                raise ValueError(
                    f"normalize_vnd_price: unit-shifted value {shifted!r} still "
                    f"out of range [{_MIN_VND_PRICE}, {_MAX_VND_PRICE}] "
                    f"(original={value!r}, reason={reason_text!r})"
                )
            corrected = int(round(shifted))
            emit_rule_outcome(
                "vnd_price",
                "coerced",
                agent=agent,
                reason="unit_shift_x1000",
                fields_changed=("value",),
                boundary=boundary,
                metadata={"original": float(value), "corrected": corrected},
            )
            return corrected
        _emit_vnd_rejected(value, reason_text, agent, boundary, "sub_1000_unjustified")
        raise ValueError(
            f"normalize_vnd_price: sub-1000 value {value!r} with no 5-digit "
            f"price in reason text — refusing to scale (reason={reason_text!r})"
        )

    # Branch 3: above max, refuse.
    _emit_vnd_rejected(value, reason_text, agent, boundary, "above_max")
    raise ValueError(f"normalize_vnd_price: value {value!r} exceeds max {_MAX_VND_PRICE}")


def clamp_vnd_field(
    model: BaseModel,
    field_name: str,
    reason_text: str | None,
    *,
    agent: RuleAgent,
) -> None:
    """Recover a single VND field on ``model`` in place via the unit-shift clamp.

    Used by every sibling Pydantic validator: ``getattr`` → recover →
    ``object.__setattr__``. Centralizes the pattern so we don't drift
    across ``midday/models.py``, ``longterm_review.py``, and
    ``belief_models.py`` validators.
    """
    current = getattr(model, field_name)
    normalized = normalize_vnd_price(current, reason_text, agent=agent)
    if normalized != current:
        object.__setattr__(model, field_name, normalized)


def _emit_vnd_rejected(
    value: float | int | None,
    reason_text: str | None,
    agent: RuleAgent,
    boundary: RuleBoundary,
    reason: VndPriceReason,
) -> None:
    emit_rule_outcome(
        "vnd_price",
        "rejected",
        agent=agent,
        reason=reason,
        boundary=boundary,
        metadata={
            "value": str(value),
            "reason_text": (reason_text or "")[:80],
        },
    )
