"""SWI-198: catalyst_classifier coverage + sentinel tests."""

from __future__ import annotations

from shared.rules.catalyst_classifier import _VALID_TYPES, classify_catalyst_type


def _classify(event: str, candidate: str = "regulatory", has_phases: bool = False):
    return classify_catalyst_type(event, candidate, has_phases)


def test_uae_quits_opec_classified_geopolitical() -> None:
    effective, outcome, reason = _classify(
        "UAE quits OPEC over oil supply dispute",
        candidate="regulatory",
        has_phases=True,
    )
    assert effective == "geopolitical"
    assert outcome == "coerced"
    assert reason == "geopolitical_subject"


def test_imf_gdp_cut_classified_macro() -> None:
    effective, outcome, _reason = _classify("IMF cuts global GDP outlook for 2026")
    assert effective == "macro"
    assert outcome == "coerced"


def test_idemitsu_classified_commodity() -> None:
    effective, outcome, _reason = _classify("Idemitsu commissions 4M barrels refinery upgrade")
    assert effective == "commodity"
    assert outcome == "coerced"


def test_vn_decree_kept_regulatory() -> None:
    effective, outcome, _reason = _classify("Decree 142 on AML rules")
    assert effective == "regulatory"
    assert outcome == "kept"


def test_blank_candidate_unclassified_when_no_rule_fires() -> None:
    # Agent emitted nothing; no rule fires → sentinel.
    effective, outcome, reason = _classify("Generic VN domestic news no rules match", candidate="")
    assert effective == "unclassified"
    assert outcome == "coerced"
    assert reason == "unclassified_default"


def test_explicit_regulatory_kept_when_no_rule_fires() -> None:
    # Agent typed regulatory explicitly — trust it.
    effective, outcome, _reason = _classify("Some VN regulatory event", candidate="regulatory")
    assert effective == "regulatory"
    assert outcome == "kept"


def test_drawing_down_stockpiles_classified_geopolitical() -> None:
    effective, outcome, _reason = _classify(
        "Major importer drawing down crude stockpiles amid supply disruption",
        candidate="commodity",
        has_phases=True,
    )
    assert effective == "geopolitical"
    assert outcome == "coerced"


def test_sanctions_waiver_classified_geopolitical() -> None:
    effective, outcome, _reason = _classify(
        "Treasury announces sanctions waiver expires next quarter",
        candidate="regulatory",
        has_phases=True,
    )
    assert effective == "geopolitical"
    assert outcome == "coerced"


def test_policy_exemption_classified_geopolitical() -> None:
    effective, outcome, _reason = _classify(
        "Administration extending policy exemption on oil imports",
        candidate="regulatory",
        has_phases=True,
    )
    assert effective == "geopolitical"
    assert outcome == "coerced"


def test_geopolitical_missing_phases_rejected() -> None:
    effective, outcome, reason = _classify(
        "UAE quits OPEC", candidate="regulatory", has_phases=False
    )
    assert outcome == "rejected"
    assert reason == "missing_phases"


def test_valid_types_matches_migration_334_allowlist() -> None:
    """Drift guard — Python ↔ migration 334 CHECK constraint must agree."""
    assert (
        frozenset(
            {
                "regulatory",
                "earnings",
                "macro",
                "rating",
                "geopolitical",
                "corporate_action",
                "legal",
                "commodity",
                "unclassified",
            }
        )
        == _VALID_TYPES
    )
