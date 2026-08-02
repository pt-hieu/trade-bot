"""Coverage for the DEF-005 per-ticker R:R floor adjustment on CatalystBoost.

HIGH/POSITIVE → 0.5, MEDIUM/POSITIVE → 0.25, otherwise 0. Drives the
per-candidate gate discount so catalyst beneficiaries clear a lower floor
than neutrals on the same scan day.
"""

from __future__ import annotations

from shared.rules.catalyst_override import CatalystInput, get_catalyst_boosted_tickers


def _catalyst(
    *,
    catalyst_key: str = "c1",
    event: str = "fuel tax 0%",
    impact: str = "POSITIVE",
    confidence: str = "HIGH",
    affected_tickers: list[str] | None = None,
    phases: dict | None = None,
    supporting_article_count: int = 3,
) -> CatalystInput:
    return {
        "catalyst_key": catalyst_key,
        "event": event,
        "impact": impact,
        "confidence": confidence,
        "affected_tickers": affected_tickers or ["PLX", "BSR"],
        "phases": phases,
        "supporting_article_count": supporting_article_count,
    }


class TestRrFloorAdjustment:
    def test_high_positive_carries_half_point_discount(self) -> None:
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="HIGH")])
        assert set(boosted) == {"PLX", "BSR"}
        assert boosted["PLX"]["rr_floor_adjustment"] == 0.5
        assert boosted["BSR"]["rr_floor_adjustment"] == 0.5

    def test_medium_positive_carries_quarter_point_discount(self) -> None:
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="MEDIUM")])
        assert set(boosted) == {"PLX", "BSR"}
        assert boosted["PLX"]["rr_floor_adjustment"] == 0.25

    def test_low_positive_without_phase_stays_out(self) -> None:
        # Without phases, LOW confidence is rejected by the existing gate —
        # no ticker boosts at all.
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="LOW")])
        assert boosted == {}

    def test_negative_impact_produces_no_boost(self) -> None:
        boosted = get_catalyst_boosted_tickers([_catalyst(impact="NEGATIVE", confidence="HIGH")])
        assert boosted == {}

    def test_neutral_impact_produces_no_boost(self) -> None:
        boosted = get_catalyst_boosted_tickers([_catalyst(impact="NEUTRAL", confidence="HIGH")])
        assert boosted == {}

    def test_high_priority_upsert_preserves_adjustment(self) -> None:
        # Two catalysts on same ticker — higher priority lifecycle wins.
        # The resulting adjustment must reflect the winning catalyst's
        # confidence tier, not leak a default zero.
        from datetime import date, timedelta

        today = date.today()
        start = today - timedelta(days=5)
        phases_active = {
            "immediate": {
                "period": f"{start.strftime('%b %-d').replace(' 0', ' ')}, {start.year}+",
                "behavior": "active",
                "impact": "POSITIVE",
            }
        }
        strong = _catalyst(
            catalyst_key="strong",
            confidence="HIGH",
            affected_tickers=["PLX"],
            phases=phases_active,
        )
        weak = _catalyst(
            catalyst_key="weak",
            confidence="MEDIUM",
            affected_tickers=["PLX"],
        )
        boosted = get_catalyst_boosted_tickers([weak, strong])
        assert boosted["PLX"]["rr_floor_adjustment"] == 0.5
        assert boosted["PLX"]["catalyst_key"] == "strong"
