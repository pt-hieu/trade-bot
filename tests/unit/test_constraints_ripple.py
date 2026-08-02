"""inject_gate_composition writes effective_* keys without clobbering inputs.

The reader-facing ENTRY CRITERIA line (brief, synthesis) must read the
POST-composition values (`effective_min_rr`, `effective_max_new_entries`)
while the PRE-composition urgency inputs (`min_rr`, `max_new_entries`)
stay intact as the producer contract — avoids circular composer-input
contamination called out in Challenge Agent 1 F4.
"""

from __future__ import annotations

from shared.rules.constraints import PipelineConstraints, inject_gate_composition
from shared.rules.recommendation_gate import RecommendationGateDecision


def _fake_gate(effective_floor: float, max_entries: int) -> RecommendationGateDecision:
    return RecommendationGateDecision(
        effective_rr_floor=effective_floor,
        max_new_entries=max_entries,
        entries_allowed=True,
        entries_blocked_reason=None,
        applied_rules=(),
    )


def test_inject_gate_composition_writes_effective_keys():
    """effective_min_rr + effective_max_new_entries mirror gate_decision output."""
    constraints: PipelineConstraints = PipelineConstraints(
        min_rr=2.0,
        max_new_entries=5,
        urgency_tier="DETERMINED",
    )
    gate = _fake_gate(effective_floor=2.5, max_entries=3)

    inject_gate_composition(constraints, gate)

    assert constraints["effective_min_rr"] == 2.5
    assert constraints["effective_max_new_entries"] == 3


def test_inject_gate_composition_preserves_pre_composition_inputs():
    """`min_rr` / `max_new_entries` stay unchanged — producer contract preserved."""
    constraints: PipelineConstraints = PipelineConstraints(
        min_rr=2.0,
        max_new_entries=5,
    )
    gate = _fake_gate(effective_floor=2.5, max_entries=3)

    inject_gate_composition(constraints, gate)

    # Urgency inputs unchanged — downstream consumers that still read the
    # pre-composition values (legacy replay paths) keep working.
    assert constraints["min_rr"] == 2.0
    assert constraints["max_new_entries"] == 5
