"""Tests for shared.rules.catalyst_classifier.classify_catalyst_type.

Defense-in-depth reclassifier for LLM-authored catalyst_type enums.
Mirrors the four worked examples the YAML prompt teaches.
"""

from __future__ import annotations

import pytest

from shared.rules.catalyst_classifier import classify_catalyst_type


class TestMacroReclassification:
    @pytest.mark.parametrize(
        "event",
        [
            "Cleveland Fed President Hammack expects Fed rates to stay on hold 'for a good while'",
            "Fed Beige Book reports US businesses cutting hiring and spending",
            "Fed Governor Waller states Iran war and labor market risks keeping Fed on hold",
            "New York Fed President Williams warns Iran war will slow growth",
            "IMF cut global GDP outlook to 3.1% (from 3.4%)",
            "FOMC statement signals rate pause through Q3",
            "Global central bankers survey identifies stagflation as top concern",
            "ECB holds rate at 4.0% amid mixed inflation signals",
        ],
    )
    def test_fed_imf_ecb_reclassified_to_macro(self, event: str) -> None:
        effective, outcome, _ = classify_catalyst_type(
            event=event, candidate_type="regulatory", has_phases=False
        )
        assert effective == "macro"
        assert outcome == "coerced"

    def test_macro_already_tagged_is_kept(self) -> None:
        effective, outcome, _ = classify_catalyst_type(
            event="IMF cuts growth outlook",
            candidate_type="macro",
            has_phases=False,
        )
        assert effective == "macro"
        assert outcome == "kept"

    def test_macro_wins_even_with_geopolitical_context(self) -> None:
        """Fed statement with Iran context is still macro (subject = Fed)."""
        effective, _, _ = classify_catalyst_type(
            event="Fed Governor Waller cites Iran war risks to rate path",
            candidate_type="regulatory",
            has_phases=False,
        )
        assert effective == "macro"


class TestGeopoliticalReclassification:
    def test_hormuz_force_majeure_reclassified(self) -> None:
        effective, outcome, _ = classify_catalyst_type(
            event="Kuwait declares force majeure on crude shipments as Hormuz blockade holds",
            candidate_type="regulatory",
            has_phases=True,
        )
        assert effective == "geopolitical"
        assert outcome == "coerced"

    def test_missing_phases_rejects(self) -> None:
        """Agent must retry with a phases dict before reclassify succeeds."""
        effective, outcome, _ = classify_catalyst_type(
            event="Trump declares Hormuz blockade after ceasefire talks collapse",
            candidate_type="regulatory",
            has_phases=False,
        )
        assert outcome == "rejected"
        assert effective == "regulatory"  # caller's type unchanged

    def test_already_geopolitical_no_rejection_on_missing_phases(self) -> None:
        """If agent already tagged geopolitical, don't reject on phases alone.

        Phases is still required by shape validators elsewhere; the
        classifier only rejects when it is *flipping* the type into
        geopolitical (which is the stricter case).
        """
        effective, outcome, _ = classify_catalyst_type(
            event="Hormuz blockade — sustained pressure phase",
            candidate_type="geopolitical",
            has_phases=False,
        )
        assert effective == "geopolitical"
        assert outcome == "kept"

    @pytest.mark.parametrize(
        "event",
        [
            "Russia sanctions cut off European crude supply",
            "OPEC announces surprise production cut amid Middle East war",
            "Iran-Israel war enters second week",
            "Taiwan strait tension spikes after naval exercise",
            "Red Sea attack disrupts major shipping lanes",
        ],
    )
    def test_other_geopolitical_triggers(self, event: str) -> None:
        effective, _, _ = classify_catalyst_type(
            event=event, candidate_type="regulatory", has_phases=True
        )
        assert effective == "geopolitical"


class TestCommodityReclassification:
    def test_oil_price_no_geopolitical_trigger(self) -> None:
        effective, outcome, _ = classify_catalyst_type(
            event="US oil exports hit record high on strong domestic output",
            candidate_type="regulatory",
            has_phases=False,
        )
        assert effective == "commodity"
        assert outcome == "coerced"

    def test_oil_with_hormuz_is_geopolitical_not_commodity(self) -> None:
        """Geopolitical rule runs before commodity — `Middle East` wins."""
        effective, _, _ = classify_catalyst_type(
            event="Oil exports rise as Middle East supply disrupted by Hormuz blockade",
            candidate_type="regulatory",
            has_phases=True,
        )
        assert effective == "geopolitical"

    def test_brent_price_alone_is_commodity(self) -> None:
        effective, _, _ = classify_catalyst_type(
            event="Brent crude price hits 6-month high on demand recovery",
            candidate_type="regulatory",
            has_phases=False,
        )
        assert effective == "commodity"


class TestRegulatoryKept:
    @pytest.mark.parametrize(
        "event",
        [
            "Government Resolution 109/NQ-CP establishes 5-year plan 2026-2030",
            "Prime Minister directs State Bank to manage interest rates flexibly",
            "Ministry of Finance proposing to extend 0% preferential import tax on fuel",
            "State Bank of Vietnam new regulation on AML compliance for interbank transfers",
            "Thủ tướng yêu cầu ưu tiên tăng trưởng tín dụng",
            "Bộ Tài chính ban hành Nghị định 137 về đa cấp",
        ],
    )
    def test_vn_actors_stay_regulatory(self, event: str) -> None:
        effective, outcome, _ = classify_catalyst_type(
            event=event, candidate_type="regulatory", has_phases=False
        )
        assert effective == "regulatory"
        assert outcome == "kept"

    def test_vn_actor_overrides_wrong_macro_tag(self) -> None:
        """When LLM wrongly tags a VN regulatory event as macro, flip to regulatory."""
        effective, outcome, _ = classify_catalyst_type(
            event="Prime Minister issues Decree 46 on food registration",
            candidate_type="macro",
            has_phases=False,
        )
        assert effective == "regulatory"
        assert outcome == "coerced"


class TestFallthrough:
    def test_ambiguous_event_keeps_candidate(self) -> None:
        """Novel events with no rule match keep the caller's type."""
        effective, outcome, _ = classify_catalyst_type(
            event="VPB confirms strategic partnership with Singapore fintech firm",
            candidate_type="corporate_action",
            has_phases=False,
        )
        assert effective == "corporate_action"
        assert outcome == "kept"

    def test_invalid_candidate_falls_back_to_regulatory(self) -> None:
        effective, _, _ = classify_catalyst_type(
            event="ambiguous event without rule match",
            candidate_type="gibberish",
            has_phases=False,
        )
        assert effective == "regulatory"
