"""SWI-183 — audit invariant accepts authority markers.

Regression net for the dropped step (e): DERIVED_FROM_BELIEFS must remain
on the authority allow-list, otherwise the pipeline hard-aborts under
ADVOCATE_GATE_MODE=enforce on every belief-derived rec.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from pipeline.published_action_audit import audit_action_downgrades  # noqa: E402
from shared.rules.audit_tags import (  # noqa: E402
    AGGREGATOR_PASSTHROUGH,
    COVERAGE_GAP_OVERRIDE,
    DERIVED_FROM_BELIEFS,
)


def _enforce(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADVOCATE_GATE_MODE", "enforce")


def _alerts(action: str = "EXIT") -> dict:
    return {"alerts": [{"ticker": "FPT", "action": action}]}


def test_audit_accepts_aggregator_passthrough_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enforce(monkeypatch)
    recs = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "rationale": f"{AGGREGATOR_PASSTHROUGH} prior preserved",
        }
    ]
    # Should NOT raise — marker present.
    audit_action_downgrades(
        scan_date=date(2026, 4, 28),
        validated_recommendations=recs,
        position_alerts=_alerts("EXIT"),
    )


def test_audit_accepts_coverage_gap_override_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enforce(monkeypatch)
    recs = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "rationale": f"{COVERAGE_GAP_OVERRIDE} prior 1/3 EXIT vs current 3/3 HOLD",
        }
    ]
    audit_action_downgrades(
        scan_date=date(2026, 4, 28),
        validated_recommendations=recs,
        position_alerts=_alerts("EXIT"),
    )


def test_audit_accepts_derived_from_beliefs_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: must NOT remove DERIVED_FROM_BELIEFS from allow-list (SWI-183 §7)."""
    _enforce(monkeypatch)
    recs = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "rationale": f"{DERIVED_FROM_BELIEFS} no sub-agent views",
        }
    ]
    audit_action_downgrades(
        scan_date=date(2026, 4, 28),
        validated_recommendations=recs,
        position_alerts=_alerts("EXIT"),
    )


def test_audit_raises_on_unaudited_downgrade_under_enforce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enforce(monkeypatch)
    recs = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "rationale": "no marker, just plain prose",
        }
    ]
    with pytest.raises(RuntimeError, match="PUBLISHED_ACTION_DOWNGRADE_UNAUDITED"):
        audit_action_downgrades(
            scan_date=date(2026, 4, 28),
            validated_recommendations=recs,
            position_alerts=_alerts("EXIT"),
        )


def test_audit_no_raise_when_actions_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enforce(monkeypatch)
    recs = [{"ticker": "FPT", "action": "EXIT", "rationale": "agreed"}]
    audit_action_downgrades(
        scan_date=date(2026, 4, 28),
        validated_recommendations=recs,
        position_alerts=_alerts("EXIT"),
    )


def test_audit_no_raise_outside_enforce_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without enforce, unaudited downgrades log but do not raise."""
    monkeypatch.delenv("ADVOCATE_GATE_MODE", raising=False)
    recs = [{"ticker": "FPT", "action": "HOLD", "rationale": "no marker"}]
    audit_action_downgrades(
        scan_date=date(2026, 4, 28),
        validated_recommendations=recs,
        position_alerts=_alerts("EXIT"),
    )
