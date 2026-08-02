"""ENTRY CRITERIA TODAY reads POST-composition R:R, not urgency input.

Before 2026-04-22, the brief said `Min R:R: 2.0` while the gate decision
held `effective_rr_floor=2.5`. Defect class: the section reader pulled
`constraints["min_rr"]` (URGENCY input) instead of the composer output.
Fix ripples the composed values via `inject_gate_composition` into
`effective_min_rr` / `effective_max_new_entries`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from shared.rules.constraints import PipelineConstraints, inject_gate_composition
from shared.rules.recommendation_gate import RecommendationGateDecision


def _fake_gate(floor: float, max_entries: int) -> RecommendationGateDecision:
    return RecommendationGateDecision(
        effective_rr_floor=floor,
        max_new_entries=max_entries,
        entries_allowed=True,
        entries_blocked_reason=None,
        applied_rules=(),
    )


@pytest.mark.asyncio
async def test_entry_criteria_uses_effective_min_rr_after_inject(mock_trading_config):
    """With effective_min_rr=2.5 and min_rr=2.0, rendered line shows 2.5."""
    from agents.strategy_sections import build_deterministic_sections

    constraints: PipelineConstraints = PipelineConstraints(
        min_rr=2.0,
        max_new_entries=5,
        urgency_tier="NORMAL",
        budget_vnd=50_000_000,
        entries_allowed=True,
    )
    inject_gate_composition(constraints, _fake_gate(floor=2.5, max_entries=3))

    with patch(
        "agents.strategy_sections.get_position_scale_factor",
        AsyncMock(return_value={}),
    ):
        rendered = await build_deterministic_sections(
            goals=[],
            cash={"deployable": 50_000_000, "min_reserve": 0},
            constraints=constraints,
            phase1={},
        )

    # Post-composition R:R surfaces on the ENTRY CRITERIA line.
    assert "Min R:R: 2.5" in rendered
    # Urgency input value (2.0) must NOT leak onto the visible line.
    assert "Min R:R: 2.0" not in rendered
    # Max entries reads the composed value (3), not the urgency input (5).
    assert "Max entries: 3" in rendered
    assert "Max entries: 5" not in rendered
