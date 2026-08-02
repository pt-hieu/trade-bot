"""Type-only taxonomy for the post-LLM rule telemetry surface (SWI-206).

Importable by both `shared/rules/*` and `shared/observability_post_llm.py`
without dragging Logfire/logger into the rules layer (preserves the
"Pipeline Decision Rules" purity from CLAUDE.md — rules import types,
not observability).

Adding a new rule: extend the appropriate `*Reason` Literal AND the
`RuleReason` union. Pyright catches typos at every call site.
"""

from __future__ import annotations

from typing import Literal

CatalystReason = Literal[
    "missing_phases",
    "macro_subject",
    "geopolitical_subject",
    "commodity_subject",
    "vn_regulatory_subject",
    "unclassified_default",
]

# Structured "primary force" the catalysts agent commits to before picking
# catalyst_type. Driver names the upstream actor, catalyst_type names the
# downstream classification. DB CHECK constraint in migration 335 mirrors
# this allowlist — extend both together.
CatalystDriver = Literal[
    "state_actor",
    "commodity_supply",
    "company_action",
    "regulator",
    "earnings_cycle",
]
CriticReason = Literal["severity_with_empty_issues"]
SynthesisVerbMatchReason = Literal["paragraph_verb_diverged", "fallback_after_retry"]
VndPriceReason = Literal[
    "unit_shift_x1000",
    "above_max",
    "sub_1000_unjustified",
    "non_finite",
    "non_positive",
]
RetroReason = Literal[
    "unknown_action",
    "unknown_rule",
    "longterm_catastrophic",
    "trade_executed_zero_pnl",
]
BeliefReason = Literal[
    "percentage_rescue",
    "garbage_fallback",
    "direction_correction",
]
WatchlistScoreReason = Literal["recompute_from_reasons"]
PrecommitReason = Literal["allowlist_size"]

# News v2 (SWI-243) — Stage 2 LLM emits `str` for enum fields; the
# coercion layer in `shared/rules/news_v2_coercion.py` maps unknown values
# to the `unclassified` sentinel and emits via this reason.
NewsV2Reason = Literal["out_of_set", "blank_input"]

RuleReason = (
    CatalystReason
    | CriticReason
    | SynthesisVerbMatchReason
    | VndPriceReason
    | RetroReason
    | BeliefReason
    | WatchlistScoreReason
    | PrecommitReason
    | NewsV2Reason
    | None
)

RuleOutcome = Literal[
    "kept", "coerced", "rejected", "unclassified", "raised_retry", "fallback_applied"
]
# "display" (SWI-326): a non-persisting render boundary (e.g. the degraded
# fallback brief) that tolerates malformed prices rather than raising.
RuleBoundary = Literal["validator", "persistence", "classifier", "output_validator", "display"]
# Per-agent attribution for VND-price clamp telemetry. Drives the
# ``agent=`` breakdown in Logfire so we can see which agent is producing
# the unit-shift defect class. Extend together with the call sites under
# ``shared/rules/vnd_price_clamp.py``.
RuleAgent = Literal[
    "midday_override",
    "midday_afternoon",
    "longterm_review",
    "TickerBelief",
    "AggregatedBelief",
    # SWI-326: structured-recommendation persistence + fallback display.
    "recommendation",
]
RuleId = Literal[
    "catalyst_type",
    "critic_severity",
    "retro_rule",
    "vnd_price",
    "belief_probabilities",
    "watchlist_score",
    "precommit_allowlist",
    "synthesis_verb_match",
    # News v2 — one rule_id per Stage 2 enum field
    "news_v2_catalyst_type",
    "news_v2_catalyst_impact",
    "news_v2_catalyst_confidence",
    "news_v2_narrative_type",
    "news_v2_sentiment_confidence",
    "news_v2_capital_event_type",
    "news_v2_link_kind",
    # SWI-195: narrative affected-ticker scope backstop (macro/geopolitical →
    # ["VN-INDEX"]).
    "narrative_affected_scope",
]
