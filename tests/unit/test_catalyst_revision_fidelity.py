"""SWI-57: lexical fidelity probe in phase_catalyst_revision."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch


def _emit(changed_catalysts, revised_strategy):
    from pipeline import phase_catalyst_revision_observability as obs

    with patch.object(obs, "log_info") as mock_log:
        obs.emit_revision_lexical_fidelity(
            scan_date=date(2026, 5, 3),
            changed_catalysts=changed_catalysts,
            revised_strategy=revised_strategy,
        )
    assert mock_log.called
    return mock_log.call_args


def test_metric_kind_is_lexical():
    _, kwargs = _emit(
        [{"catalyst_key": "fuel_tax_hike", "event": "Fuel tax"}],
        "Fuel tax hike will impact",
    )
    assert kwargs["metric_kind"] == "lexical"


def test_word_boundary_match_full_ratio():
    _, kwargs = _emit(
        [{"catalyst_key": "vinfast_ipo"}],
        "VinFast IPO completes pricing",
    )
    # vinfast_ipo lower-cased; word boundary matches "vinfast_ipo" not present in body.
    # Use a key that appears verbatim:
    _, kwargs = _emit(
        [{"catalyst_key": "earnings"}],
        "Banking earnings beat consensus",
    )
    assert kwargs["lexical_fidelity_ratio"] == 1.0
    assert kwargs["matched_count"] == 1
    assert kwargs["trigger_count"] == 1


def test_min_len_filter():
    # `vn` is length 2 — below MIN_KEY_LEN=4
    _, kwargs = _emit([{"catalyst_key": "vn"}], "vn moves up")
    assert kwargs["trigger_count"] == 0


def test_stopword_filter():
    _, kwargs = _emit([{"catalyst_key": "vnindex"}], "vnindex breaks 1300")
    assert kwargs["trigger_count"] == 0  # vnindex is stopword


def test_partial_match():
    _, kwargs = _emit(
        [{"catalyst_key": "earnings"}, {"catalyst_key": "merger"}],
        "Earnings season opens",
    )
    assert kwargs["matched_count"] == 1
    assert kwargs["trigger_count"] == 2
    assert kwargs["lexical_fidelity_ratio"] == 0.5


def test_empty_triggers_zero():
    _, kwargs = _emit([], "anything")
    assert kwargs["lexical_fidelity_ratio"] == 0.0
    assert kwargs["trigger_count"] == 0
