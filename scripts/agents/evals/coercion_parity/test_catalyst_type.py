"""Value-parity tests for catalyst_classifier (SWI-206)."""

from __future__ import annotations

import pytest

from shared.rules.catalyst_classifier import classify_catalyst_type


class TestCatalystOutcomeMapping:
    def test_kept_no_emit(self, capture_emits: list[dict]) -> None:
        eff, outcome, reason = classify_catalyst_type(
            "VPB confirms strategic partnership", "corporate_action", False
        )
        assert (eff, outcome, reason) == ("corporate_action", "kept", None)
        assert capture_emits == []

    def test_macro_subject_coerced(self, capture_emits: list[dict]) -> None:
        eff, outcome, reason = classify_catalyst_type(
            "Fed Beige Book signals slowdown", "regulatory", False
        )
        assert eff == "macro"
        assert outcome == "coerced"
        assert reason == "macro_subject"
        assert any(e["reason"] == "macro_subject" for e in capture_emits)

    def test_geopolitical_missing_phases_rejected(self, capture_emits: list[dict]) -> None:
        eff, outcome, reason = classify_catalyst_type(
            "Hormuz blockade after ceasefire collapse", "regulatory", False
        )
        assert outcome == "rejected"
        assert reason == "missing_phases"
        assert eff == "regulatory"
        assert any(
            e["outcome"] == "rejected" and e["reason"] == "missing_phases" for e in capture_emits
        )

    def test_geopolitical_with_phases_coerced(self, capture_emits: list[dict]) -> None:
        eff, outcome, reason = classify_catalyst_type(
            "Iran-Israel war enters second week", "regulatory", True
        )
        assert eff == "geopolitical"
        assert outcome == "coerced"
        assert reason == "geopolitical_subject"

    def test_commodity_subject_coerced(self, capture_emits: list[dict]) -> None:
        eff, outcome, reason = classify_catalyst_type(
            "Brent crude price hits 6-month high", "regulatory", False
        )
        assert eff == "commodity"
        assert outcome == "coerced"
        assert reason == "commodity_subject"

    def test_vn_regulatory_overrides_wrong_macro(self, capture_emits: list[dict]) -> None:
        eff, outcome, reason = classify_catalyst_type(
            "Prime Minister issues Decree 46 on food registration", "macro", False
        )
        assert eff == "regulatory"
        assert outcome == "coerced"
        assert reason == "vn_regulatory_subject"


@pytest.mark.parametrize(
    "event,candidate,phases,want_eff,want_out",
    [
        ("Fed Governor Waller speech", "regulatory", False, "macro", "coerced"),
        ("IMF cuts global GDP outlook", "regulatory", False, "macro", "coerced"),
        ("ECB holds rates", "regulatory", False, "macro", "coerced"),
        (
            "Russia sanctions cut crude supply",
            "regulatory",
            True,
            "geopolitical",
            "coerced",
        ),
        ("US oil exports record high", "regulatory", False, "commodity", "coerced"),
        (
            "Bộ Tài chính ban hành Nghị định 137",
            "regulatory",
            False,
            "regulatory",
            "kept",
        ),
        (
            "ambiguous event no rule match",
            "earnings",
            False,
            "earnings",
            "kept",
        ),
    ],
)
def test_branch_coverage(
    event: str, candidate: str, phases: bool, want_eff: str, want_out: str
) -> None:
    eff, outcome, _ = classify_catalyst_type(event, candidate, phases)
    assert eff == want_eff
    assert outcome == want_out
