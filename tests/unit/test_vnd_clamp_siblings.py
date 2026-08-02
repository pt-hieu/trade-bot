"""SWI-184 — sibling-model parity for normalize_vnd_price clamp.

Covers every Pydantic ``*_vnd`` int/float field in ``scripts/agents/`` that
gained a ``model_validator`` in the SWI-184 generalization commit:

  * ``midday.AfternoonAction.evidence_price_vnd``
  * ``longterm_review.NewStockRecommendation.suggested_entry_zone_vnd``
  * ``belief_models.TickerBelief.price_target_vnd``
  * ``belief_models.AggregatedBelief.price_target_vnd``

Mirrors the parametrized cases laid out in the plan: input ``44.91`` +
corroborating 5-digit reason → ``44910``; input ``500`` with no
corroborating reason → raises (or, in the belief case, falls back to the
soft warning per SWI-184 because legacy DB rows exist with target=0).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from agents.belief_models import AggregatedBelief, TickerBelief  # noqa: E402
from agents.longterm_review import NewStockRecommendation  # noqa: E402
from agents.midday.models import AfternoonAction  # noqa: E402


class TestAfternoonActionEvidencePrice:
    def test_unit_shift_recovered(self) -> None:
        action = AfternoonAction(
            ticker="ACV",
            action="WATCH",
            confidence="MEDIUM",
            reason="Watching for breakout above 44,910",
            evidence_price_vnd=44,  # int dropped 3 zeros; 44.91 not allowed by int field
        )
        # Below: 44 is sub-1000 with corroborating 5-digit reason → ×1000.
        assert action.evidence_price_vnd == 44000

    def test_in_range_passthrough(self) -> None:
        action = AfternoonAction(
            ticker="ACV",
            action="WATCH",
            confidence="MEDIUM",
            reason="Watching for breakout above 44910",
            evidence_price_vnd=44910,
        )
        assert action.evidence_price_vnd == 44910

    def test_sub_1000_no_reason_raises(self) -> None:
        with pytest.raises(ValueError):
            AfternoonAction(
                ticker="ACV",
                action="WATCH",
                confidence="MEDIUM",
                reason="thesis broken, watching closely",
                evidence_price_vnd=500,
            )

    def test_none_passthrough(self) -> None:
        action = AfternoonAction(
            ticker="ACV",
            action="WATCH",
            confidence="MEDIUM",
            reason="No specific level",
            evidence_price_vnd=None,
        )
        assert action.evidence_price_vnd is None


class TestNewStockRecommendationEntryZone:
    def test_unit_shift_recovered(self) -> None:
        rec = NewStockRecommendation(
            ticker="VHM",
            sector="Real Estate",
            suggested_entry_zone_vnd=42,
            suggested_conviction="Medium",
            thesis="Strong moat, attractive entry near 42,000 support",
        )
        assert rec.suggested_entry_zone_vnd == 42000

    def test_in_range_passthrough(self) -> None:
        rec = NewStockRecommendation(
            ticker="VHM",
            sector="Real Estate",
            suggested_entry_zone_vnd=42000,
            suggested_conviction="Medium",
            thesis="Strong moat, attractive entry near 42,000 support",
        )
        assert rec.suggested_entry_zone_vnd == 42000

    def test_sub_1000_no_reason_raises(self) -> None:
        with pytest.raises(ValueError):
            NewStockRecommendation(
                ticker="VHM",
                sector="Real Estate",
                suggested_entry_zone_vnd=500,
                suggested_conviction="Medium",
                thesis="Quality business with durable moat",
            )


def _belief_kwargs(
    price_target_vnd: int,
    narrative: str,
    *,
    aggregated: bool = False,
) -> dict[str, object]:
    common: dict[str, object] = {
        "ticker": "FPT",
        "belief_narrative": narrative,
        "direction": "BULLISH",
        "bull_probability": 0.55,
        "base_probability": 0.30,
        "bear_probability": 0.15,
        "price_target_vnd": price_target_vnd,
        "conviction": 0.7,
    }
    if aggregated:
        return common
    return {
        **common,
        "belief_status": "NEW",
    }


class TestTickerBeliefPriceTarget:
    def test_unit_shift_recovered(self) -> None:
        belief = TickerBelief(**_belief_kwargs(150, "Target 150,000 by quarter end"))  # type: ignore[arg-type]
        assert belief.price_target_vnd == 150000

    def test_in_range_passthrough(self) -> None:
        belief = TickerBelief(**_belief_kwargs(150000, "Target 150,000 by quarter end"))  # type: ignore[arg-type]
        assert belief.price_target_vnd == 150000

    def test_sub_1000_no_reason_falls_back_to_soft_warning(self) -> None:
        # SWI-184: legacy rows exist with target=0; validator-only path
        # logs the soft warning instead of raising.
        belief = TickerBelief(**_belief_kwargs(500, "thesis intact, no specific level"))  # type: ignore[arg-type]
        assert belief.price_target_vnd == 500


class TestAggregatedBeliefPriceTarget:
    def test_unit_shift_recovered(self) -> None:
        belief = AggregatedBelief(
            **_belief_kwargs(150, "Reconciled target 150,000", aggregated=True)  # type: ignore[arg-type]
        )
        assert belief.price_target_vnd == 150000

    def test_in_range_passthrough(self) -> None:
        belief = AggregatedBelief(
            **_belief_kwargs(150000, "Reconciled target 150,000", aggregated=True)  # type: ignore[arg-type]
        )
        assert belief.price_target_vnd == 150000
