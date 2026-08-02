#!/usr/bin/env python3
"""
Belief models — structured predictions from agent personas.

Each agent forms a belief about what will happen to a ticker,
persisted across runs for continuity, tracked for accuracy.
"""

from __future__ import annotations

import logging
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator

from shared.observability_post_llm import emit_rule_outcome
from shared.post_llm_types import RuleAgent
from shared.rules.vnd_price_clamp import normalize_vnd_price

logger = logging.getLogger(__name__)


# Vietnamese market base rates — FALLBACK ONLY.
# Production uses dynamic rates from compute_empirical_base_rates().
# These exist solely for unit tests and environments with no scored beliefs.
BASE_RATE_BULL = 0.24
BASE_RATE_NEUTRAL = 0.68
BASE_RATE_BEAR = 0.08

# Field descriptions for LLM schema guidance (shared across TickerBelief and AggregatedBelief)
_BULL_PROB_DESC = "Decimal 0.0-1.0 (NOT percentage). P(price up >1.5%). 0.45 means 45% chance."
_BASE_PROB_DESC = "Decimal 0.0-1.0 (NOT percentage). P(within +/-1.5%). 0.35 means 35% chance."
_BEAR_PROB_DESC = "Decimal 0.0-1.0 (NOT percentage). P(price down >1.5%). 0.20 means 20% chance."
_CONVICTION_DESC = "Decimal 0.0-1.0. How strongly you commit to this view."
_PRICE_TARGET_DESC = (
    "Your predicted VND price at horizon end. "
    "Must be a realistic stock price (typically 5000-500000)."
)

# Minimum probability required for a directional (BULLISH/BEARISH) label.
# Near-uniform distributions (common after base rate anchoring) resolve to NEUTRAL.
MIN_DIRECTIONAL_PROBABILITY = 0.40

# Lazy NEUTRAL detection: base_probability above this with low conviction = no signal.
# Threshold raised to 0.75 because actual NEUTRAL rate is ~68% — base > 0.55 is CORRECT.
# Only flag as lazy when base > 0.75 with low conviction (truly defaulting without analysis).
LAZY_NEUTRAL_BASE_THRESHOLD = 0.75
LAZY_NEUTRAL_CONVICTION_THRESHOLD = 0.5

# Price targets below this are suspiciously low for VND stocks
UNREALISTIC_PRICE_TARGET_THRESHOLD = 1000


DirectionLiteral = Literal["BULLISH", "BEARISH", "NEUTRAL"]

# Staleness decay: beliefs held >2 days get decayed conviction
STALENESS_GRACE_DAYS = 2
STALENESS_DECAY_FACTOR = 0.85


def decay_belief_conviction(conviction: float, days_held: int) -> float:
    """Apply staleness decay to belief conviction.

    Beliefs held ≤2 days keep full conviction. Beyond that, conviction
    decays by 0.85^(excess days) to break self-reinforcing feedback loops.
    """
    if days_held <= STALENESS_GRACE_DAYS:
        return conviction
    return round(conviction * STALENESS_DECAY_FACTOR ** (days_held - STALENESS_GRACE_DAYS), 3)


def derive_direction_from_probabilities(bull: float, base: float, bear: float) -> DirectionLiteral:
    """Deterministic direction from probabilities via argmax + minimum confidence gate.

    BULLISH/BEARISH require the top probability to be >= MIN_DIRECTIONAL_PROBABILITY.
    Near-uniform distributions (common after base rate anchoring) resolve to NEUTRAL,
    preventing fabricated directional labels from noise.
    """
    probabilities: dict[DirectionLiteral, float] = {
        "BULLISH": bull,
        "NEUTRAL": base,
        "BEARISH": bear,
    }
    top_direction = cast(DirectionLiteral, max(probabilities, key=probabilities.get))  # type: ignore[arg-type]
    top_probability = probabilities[top_direction]

    # Directional labels require minimum confidence; NEUTRAL has no gate
    if top_direction != "NEUTRAL" and top_probability < MIN_DIRECTIONAL_PROBABILITY:
        return "NEUTRAL"
    return top_direction


def _normalize_belief_probabilities(model: TickerBelief | AggregatedBelief) -> None:
    """Shared normalization: renormalize probabilities to sum=1.0, clamp conviction.

    Handles three cases:
    1. Percentage-scale (sum 50-150): LLM output 45/35/20 instead of 0.45/0.35/0.20 — rescue by /100
    2. Valid range (sum 0.5-1.5): renormalize to exactly 1.0
    3. Garbage (sum <0.5 or >1.5 after rescue): fall back to base rates

    Modifies the model in place.
    """
    total = model.bull_probability + model.base_probability + model.bear_probability

    # Rescue percentage-scale outputs (LLM output 45/35/20 instead of 0.45/0.35/0.20)
    # Range [50, 150] is unambiguous: valid decimals max at ~3.0, percentages min at ~50
    if 50 <= total <= 150:
        emit_rule_outcome(
            "belief_probabilities",
            "coerced",
            agent=type(model).__name__,
            reason="percentage_rescue",
            fields_changed=("bull_probability", "base_probability", "bear_probability"),
            boundary="validator",
            metadata={"ticker": model.ticker, "sum": float(total)},
        )
        model.bull_probability /= 100
        model.base_probability /= 100
        model.bear_probability /= 100
        total = model.bull_probability + model.base_probability + model.bear_probability

    if total < 0.5 or total > 1.5:
        emit_rule_outcome(
            "belief_probabilities",
            "coerced",
            agent=type(model).__name__,
            reason="garbage_fallback",
            fields_changed=("bull_probability", "base_probability", "bear_probability"),
            boundary="validator",
            metadata={
                "ticker": model.ticker,
                "sum": float(total),
                "bull": float(model.bull_probability),
                "base": float(model.base_probability),
                "bear": float(model.bear_probability),
            },
        )
        model.bull_probability = BASE_RATE_BULL
        model.base_probability = BASE_RATE_NEUTRAL
        model.bear_probability = BASE_RATE_BEAR
    elif abs(total - 1.0) > 0.001:
        model.bull_probability = round(model.bull_probability / total, 4)
        model.base_probability = round(model.base_probability / total, 4)
        model.bear_probability = round(1.0 - model.bull_probability - model.base_probability, 4)

    model.conviction = max(0.0, min(1.0, model.conviction))

    # Auto-correct direction to match probabilities (deterministic, Rule 9)
    computed_direction = derive_direction_from_probabilities(
        model.bull_probability, model.base_probability, model.bear_probability
    )
    if model.direction != computed_direction:
        emit_rule_outcome(
            "belief_probabilities",
            "coerced",
            agent=type(model).__name__,
            reason="direction_correction",
            fields_changed=("direction",),
            boundary="validator",
            metadata={
                "ticker": model.ticker,
                "from": model.direction,
                "to": computed_direction,
                "bull": float(model.bull_probability),
                "base": float(model.base_probability),
                "bear": float(model.bear_probability),
            },
        )
        model.direction = computed_direction

    # Unit-shift recovery — best-effort. ``Field(ge=1)`` tolerates sub-1000
    # because legacy DB rows exist with target=0; on recovery refusal we keep
    # the original value and rely on the soft warning below.
    agent_label = cast(RuleAgent, type(model).__name__)
    try:
        normalized_target = normalize_vnd_price(
            model.price_target_vnd,
            model.belief_narrative,
            agent=agent_label,
        )
        if normalized_target is not None and normalized_target != model.price_target_vnd:
            model.price_target_vnd = normalized_target
    except ValueError as exc:
        logger.warning(
            "normalize_vnd_price refused recovery for %s ticker=%s price_target_vnd=%r: %s",
            agent_label,
            model.ticker,
            model.price_target_vnd,
            exc,
        )

    if model.price_target_vnd < UNREALISTIC_PRICE_TARGET_THRESHOLD:
        logger.warning(
            "Suspiciously low price_target_vnd=%d for %s — verify correctness",
            model.price_target_vnd,
            model.ticker,
        )

    if (
        model.base_probability > LAZY_NEUTRAL_BASE_THRESHOLD
        and model.conviction < LAZY_NEUTRAL_CONVICTION_THRESHOLD
    ):
        logger.warning(
            "Lazy NEUTRAL detected for %s: base=%.2f conv=%.2f — non-committal",
            model.ticker,
            model.base_probability,
            model.conviction,
        )


class TickerBelief(BaseModel):
    """A single agent's belief about a ticker's near-term trajectory."""

    ticker: str
    belief_narrative: str = Field(max_length=300)  # 2 sentences max
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    bull_probability: float = Field(description=_BULL_PROB_DESC)
    base_probability: float = Field(description=_BASE_PROB_DESC)
    bear_probability: float = Field(description=_BEAR_PROB_DESC)
    price_target_vnd: int = Field(ge=1, description=_PRICE_TARGET_DESC)
    timeframe_days: int = 5
    conviction: float = Field(description=_CONVICTION_DESC)
    belief_status: Literal["NEW", "REAFFIRMED", "UPDATED", "REVERSED"]
    update_reason: str | None = Field(default=None, max_length=200)  # 1 sentence

    @model_validator(mode="after")
    def normalize_probabilities(self) -> TickerBelief:
        _normalize_belief_probabilities(self)
        return self


class AggregatedBelief(BaseModel):
    """Aggregator's reconciled belief after examining sub-agent beliefs."""

    ticker: str
    belief_narrative: str = Field(max_length=300)  # 2 sentences max
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    bull_probability: float = Field(description=_BULL_PROB_DESC)
    base_probability: float = Field(description=_BASE_PROB_DESC)
    bear_probability: float = Field(description=_BEAR_PROB_DESC)
    price_target_vnd: int = Field(ge=1, description=_PRICE_TARGET_DESC)
    timeframe_days: int = 5
    conviction: float = Field(description=_CONVICTION_DESC)
    disagreement_note: str | None = Field(default=None, max_length=200)  # 1 sentence max

    @model_validator(mode="after")
    def normalize_probabilities(self) -> AggregatedBelief:
        _normalize_belief_probabilities(self)
        return self
