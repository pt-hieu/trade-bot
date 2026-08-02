"""Tests for shared.rules.catalyst_override.

Covers the catalyst boost set (legacy behavior) and the Fix 1 (2026-04-21)
`classify_geo_label` aggregator — notably the GEO_MIXED tie-break that
breaks the shock-vs-stacked-positive deadlock.
"""

from __future__ import annotations

from shared.rules.catalyst_override import (
    CatalystBoost,
    CatalystInput,
    classify_geo_label,
    count_high_positive_per_ticker,
    get_catalyst_boosted_tickers,
)


def _make_catalyst(
    *,
    catalyst_key: str = "c1",
    event: str = "catalyst event",
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
        "affected_tickers": affected_tickers or [],
        "phases": phases,
        "supporting_article_count": supporting_article_count,
    }


def _make_shock(
    *,
    phase_name: str = "immediate_shock",
    catalyst_key: str = "hormuz_closure_2026",
    affected_tickers: list[str] | None = None,
) -> dict:
    return {
        "phase_name": phase_name,
        "catalyst_event": "Hormuz closure",
        "behavior": "risk-off",
        "impact": "NEGATIVE",
        "affected_tickers": affected_tickers or [],
        "notes": "",
        "catalyst_key": catalyst_key,
        "days_active": 1,
        "phase_stale": False,
    }


class TestClassifyGeoLabelBasic:
    def test_no_shock_returns_none(self) -> None:
        assert (
            classify_geo_label(
                ticker="POW",
                macro_sensitivities=[],
                geopolitical_shock=None,
                positive_catalyst_boosts={},
            )
            is None
        )

    def test_non_active_phase_returns_none(self) -> None:
        shock = _make_shock(phase_name="resolved")
        assert (
            classify_geo_label(
                ticker="POW",
                macro_sensitivities=[],
                geopolitical_shock=shock,  # type: ignore[arg-type]
                positive_catalyst_boosts={},
            )
            is None
        )

    def test_beneficiary_score_wins(self) -> None:
        """POSITIVE sensitivity to oil_price on an oil shock → GEO_BENEFICIARY."""
        shock = _make_shock(affected_tickers=["POW", "GAS"])
        sensitivities = [{"factor": "oil_price", "direction": "POSITIVE", "magnitude": "HIGH"}]
        result = classify_geo_label(
            ticker="GAS",
            macro_sensitivities=sensitivities,
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
        )
        assert result == "GEO_BENEFICIARY"

    def test_victim_score_wins(self) -> None:
        shock = _make_shock(affected_tickers=["HVN"])
        sensitivities = [{"factor": "oil_price", "direction": "NEGATIVE", "magnitude": "HIGH"}]
        result = classify_geo_label(
            ticker="HVN",
            macro_sensitivities=sensitivities,
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
        )
        assert result == "GEO_VICTIM"

    def test_exposed_fallback_when_affected_but_no_sensitivity(self) -> None:
        shock = _make_shock(affected_tickers=["VNM"])
        result = classify_geo_label(
            ticker="VNM",
            macro_sensitivities=[],
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
        )
        assert result == "GEO_EXPOSED"


class TestGeoMixedTiebreak:
    """Fix 1 tie-break: shock-victim + ≥2 stacked HIGH/MEDIUM POSITIVE catalysts."""

    def test_two_high_positive_catalysts_trigger_mixed(self) -> None:
        shock = _make_shock(affected_tickers=["POW"])
        sensitivities = [{"factor": "oil_price", "direction": "NEGATIVE", "magnitude": "MEDIUM"}]
        active = [
            _make_catalyst(
                catalyst_key="pm_rate_directive",
                impact="POSITIVE",
                confidence="HIGH",
                affected_tickers=["POW"],
            ),
            _make_catalyst(
                catalyst_key="fuel_tax_cut",
                impact="POSITIVE",
                confidence="MEDIUM",
                affected_tickers=["POW"],
            ),
        ]
        result = classify_geo_label(
            ticker="POW",
            macro_sensitivities=sensitivities,
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
            active_catalysts=active,
        )
        assert result == "GEO_MIXED"

    def test_single_positive_catalyst_still_victim(self) -> None:
        """Only one stacked positive catalyst → threshold not met → still victim."""
        shock = _make_shock(affected_tickers=["POW"])
        sensitivities = [{"factor": "oil_price", "direction": "NEGATIVE", "magnitude": "HIGH"}]
        active = [
            _make_catalyst(impact="POSITIVE", confidence="HIGH", affected_tickers=["POW"]),
        ]
        result = classify_geo_label(
            ticker="POW",
            macro_sensitivities=sensitivities,
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
            active_catalysts=active,
        )
        assert result == "GEO_VICTIM"

    def test_low_confidence_positive_catalysts_do_not_stack(self) -> None:
        shock = _make_shock(affected_tickers=["POW"])
        sensitivities = [{"factor": "oil_price", "direction": "NEGATIVE", "magnitude": "HIGH"}]
        active = [
            _make_catalyst(
                catalyst_key="c1",
                impact="POSITIVE",
                confidence="LOW",
                affected_tickers=["POW"],
            ),
            _make_catalyst(
                catalyst_key="c2",
                impact="POSITIVE",
                confidence="LOW",
                affected_tickers=["POW"],
            ),
        ]
        result = classify_geo_label(
            ticker="POW",
            macro_sensitivities=sensitivities,
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
            active_catalysts=active,
        )
        assert result == "GEO_VICTIM"

    def test_mixed_not_fired_when_no_victim_signal(self) -> None:
        """No victim-score → mixed tie-break doesn't apply; beneficiary wins."""
        shock = _make_shock(affected_tickers=["POW"])
        sensitivities = [{"factor": "oil_price", "direction": "POSITIVE", "magnitude": "HIGH"}]
        active = [
            _make_catalyst(catalyst_key="c1", impact="POSITIVE", affected_tickers=["POW"]),
            _make_catalyst(catalyst_key="c2", impact="POSITIVE", affected_tickers=["POW"]),
        ]
        result = classify_geo_label(
            ticker="POW",
            macro_sensitivities=sensitivities,
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
            active_catalysts=active,
        )
        assert result == "GEO_BENEFICIARY"


class TestShockFactorsFallback:
    def test_unknown_catalyst_key_without_factors_falls_back_to_exposed(self) -> None:
        shock = _make_shock(catalyst_key="red_sea_2026_hypothetical", affected_tickers=["PLX"])
        result = classify_geo_label(
            ticker="PLX",
            macro_sensitivities=None,
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
            shock_factors=None,
        )
        assert result == "GEO_EXPOSED"

    def test_explicit_shock_factors_override_fallback(self) -> None:
        """Fix 2 (catalyst_factors column) supplies factors explicitly."""
        shock = _make_shock(catalyst_key="new_event_key", affected_tickers=[])
        sensitivities = [{"factor": "dxy", "direction": "NEGATIVE", "magnitude": "HIGH"}]
        result = classify_geo_label(
            ticker="SSI",
            macro_sensitivities=sensitivities,
            geopolitical_shock=shock,  # type: ignore[arg-type]
            positive_catalyst_boosts={},
            shock_factors=["dxy", "vix"],
        )
        assert result == "GEO_VICTIM"


class TestGetCatalystBoostedTickers:
    """Legacy boost logic — preserve behavior (no migration)."""

    def test_high_confidence_no_phase_boosts(self) -> None:
        catalyst = _make_catalyst(
            catalyst_key="c1",
            impact="POSITIVE",
            confidence="HIGH",
            affected_tickers=["POW", "GAS"],
            phases=None,
        )
        result = get_catalyst_boosted_tickers([catalyst])
        assert set(result.keys()) == {"POW", "GAS"}
        assert result["POW"]["phase_lifecycle"] == "STATIC"

    def test_negative_catalyst_does_not_boost(self) -> None:
        catalyst = _make_catalyst(impact="NEGATIVE", confidence="HIGH", affected_tickers=["POW"])
        assert get_catalyst_boosted_tickers([catalyst]) == {}

    def test_low_without_phase_excluded(self) -> None:
        catalyst = _make_catalyst(
            impact="POSITIVE",
            confidence="LOW",
            affected_tickers=["POW"],
            phases=None,
        )
        assert get_catalyst_boosted_tickers([catalyst]) == {}


class TestCountHighPositivePerTicker:
    """L2 (2026-04-27): per-ticker count helper for stacked-shock relief.

    Counts only POSITIVE catalysts with HIGH or MEDIUM confidence; LOW and
    NEGATIVE never contribute. VN-INDEX placeholder is excluded so a macro
    blanket catalyst doesn't double-count toward per-ticker relief.
    """

    def test_high_positive_counts_per_ticker(self) -> None:
        catalysts = [
            _make_catalyst(
                catalyst_key="c1",
                impact="POSITIVE",
                confidence="HIGH",
                affected_tickers=["PLX", "BSR"],
            ),
            _make_catalyst(
                catalyst_key="c2",
                impact="POSITIVE",
                confidence="MEDIUM",
                affected_tickers=["PLX"],
            ),
        ]
        result = count_high_positive_per_ticker(catalysts, {"PLX", "BSR"})
        assert result == {"PLX": 2, "BSR": 1}

    def test_low_confidence_excluded(self) -> None:
        catalyst = _make_catalyst(impact="POSITIVE", confidence="LOW", affected_tickers=["PLX"])
        result = count_high_positive_per_ticker([catalyst], {"PLX"})
        assert result == {}

    def test_negative_impact_excluded(self) -> None:
        catalyst = _make_catalyst(impact="NEGATIVE", confidence="HIGH", affected_tickers=["PLX"])
        result = count_high_positive_per_ticker([catalyst], {"PLX"})
        assert result == {}

    def test_universe_filter_excludes_unwanted_tickers(self) -> None:
        # Catalyst names BSR but caller's universe is {PLX} — BSR is excluded
        # from the count entirely, not just suppressed.
        catalyst = _make_catalyst(
            impact="POSITIVE",
            confidence="HIGH",
            affected_tickers=["PLX", "BSR"],
        )
        result = count_high_positive_per_ticker([catalyst], {"PLX"})
        assert result == {"PLX": 1}

    def test_vn_index_placeholder_excluded(self) -> None:
        # Macro blanket fan-out (VN-INDEX in affected_tickers) must not
        # contribute to per-ticker stacked-shock count — that's what the
        # macro path is for.
        catalyst = _make_catalyst(
            impact="POSITIVE",
            confidence="HIGH",
            affected_tickers=["VN-INDEX"],
        )
        result = count_high_positive_per_ticker([catalyst], {"VN-INDEX", "PLX"})
        assert result == {}

    def test_empty_inputs_short_circuit(self) -> None:
        assert count_high_positive_per_ticker(None, {"PLX"}) == {}
        assert count_high_positive_per_ticker([], {"PLX"}) == {}
        assert (
            count_high_positive_per_ticker([_make_catalyst(affected_tickers=["PLX"])], set()) == {}
        )


# Satisfy linter — CatalystBoost is re-exported for downstream typing
_ = CatalystBoost
