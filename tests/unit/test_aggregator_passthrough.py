"""Phase 2 §2.4 — cross-run urgency preservation rule.

Reproduces the 2026-04-28 silent FPT EXIT→HOLD: prior run emitted EXIT,
current fallback voted HOLD; the rule must preserve EXIT and tag the
override with the [AGGREGATOR_PASSTHROUGH] resolving rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from shared.rules.aggregator_passthrough import (  # noqa: E402
    PASSTHROUGH_RULE_TAG,
    preserve_higher_urgency,
)
from shared.rules.audit_tags import COVERAGE_GAP_OVERRIDE  # noqa: E402


def test_no_prior_alerts_returns_current_unchanged() -> None:
    current = [{"ticker": "FPT", "action": "HOLD", "reason": "fine"}]
    assert preserve_higher_urgency(None, current) == current


def test_higher_prior_action_preserved() -> None:
    prior = [{"ticker": "FPT", "action": "EXIT", "reason": "thesis broke"}]
    current = [{"ticker": "FPT", "action": "HOLD", "reason": "stable"}]
    merged = preserve_higher_urgency(prior, current)
    assert len(merged) == 1
    assert merged[0]["action"] == "EXIT"
    assert merged[0]["resolving_rule"] == "AGGREGATOR_PASSTHROUGH"
    assert PASSTHROUGH_RULE_TAG in merged[0]["reason"]


def test_lower_prior_action_yields_to_current() -> None:
    prior = [{"ticker": "FPT", "action": "HOLD", "reason": "wait"}]
    current = [{"ticker": "FPT", "action": "EXIT", "reason": "thesis broke"}]
    merged = preserve_higher_urgency(prior, current)
    assert len(merged) == 1
    assert merged[0]["action"] == "EXIT"
    # Current was already at higher rank; no passthrough tag attached.
    assert merged[0].get("resolving_rule") != "AGGREGATOR_PASSTHROUGH"


def test_ticker_dropped_in_current_preserves_prior() -> None:
    prior = [{"ticker": "FPT", "action": "TRIM", "reason": "concentration"}]
    current: list[dict] = []
    merged = preserve_higher_urgency(prior, current)
    assert len(merged) == 1
    assert merged[0]["action"] == "TRIM"
    assert merged[0]["resolving_rule"] == "AGGREGATOR_PASSTHROUGH"
    assert "dropped ticker" in merged[0]["reason"]


def test_ticker_only_in_current_kept_as_is() -> None:
    prior: list[dict] = []
    current = [{"ticker": "TCB", "action": "HOLD", "reason": "stable"}]
    merged = preserve_higher_urgency(prior, current)
    assert len(merged) == 1
    assert merged[0] == current[0]


def test_multiple_tickers_independent_resolution() -> None:
    prior = [
        {"ticker": "FPT", "action": "EXIT", "reason": "broke"},
        {"ticker": "TCB", "action": "TRIM", "reason": "size"},
        {"ticker": "ACV", "action": "HOLD", "reason": "wait"},
    ]
    current = [
        {"ticker": "FPT", "action": "HOLD", "reason": "stable"},  # downgrade
        {"ticker": "TCB", "action": "EXIT", "reason": "broke"},  # upgrade
        {"ticker": "ACV", "action": "HOLD", "reason": "wait"},  # equal
    ]
    merged = preserve_higher_urgency(prior, current)
    actions = {a["ticker"]: a["action"] for a in merged}
    assert actions["FPT"] == "EXIT"
    assert actions["TCB"] == "EXIT"
    assert actions["ACV"] == "HOLD"


def test_2026_04_28_fpt_tcb_repro() -> None:
    """Reproduce the actual incident: FPT/TCB downgraded silently.

    Run 1 (success): FPT EXIT, TCB TRIM.
    Run 2 (fallback): both HOLD because sub-agents alone didn't converge
    on EXIT/TRIM in committee view.
    Expected: FPT remains EXIT, TCB remains TRIM, both with passthrough
    tag.
    """
    prior = [
        {"ticker": "FPT", "action": "EXIT", "reason": "stop breached"},
        {"ticker": "TCB", "action": "TRIM", "reason": "concentration > 35%"},
    ]
    current = [
        {"ticker": "FPT", "action": "HOLD", "reason": "BROAD_MARKET context"},
        {"ticker": "TCB", "action": "HOLD", "reason": "below 15% trim threshold"},
    ]
    merged = preserve_higher_urgency(prior, current)
    actions = {a["ticker"]: a["action"] for a in merged}
    assert actions["FPT"] == "EXIT"
    assert actions["TCB"] == "TRIM"
    for alert in merged:
        assert alert["resolving_rule"] == "AGGREGATOR_PASSTHROUGH"
        assert PASSTHROUGH_RULE_TAG in alert["reason"]


def test_coverage_gap_overrides_higher_urgency() -> None:
    """SWI-183 — attempt-1 1/3 EXIT vs attempt-2 3/3 HOLD: HOLD wins."""
    prior = [
        {
            "ticker": "FPT",
            "action": "EXIT",
            "reason": "ADX bearish",
            "coverage_responding": 1,
            "coverage_total": 3,
        }
    ]
    current = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "reason": "floor intact, divergence forming",
            "coverage_responding": 3,
            "coverage_total": 3,
        }
    ]
    merged = preserve_higher_urgency(prior, current)
    assert len(merged) == 1
    assert merged[0]["action"] == "HOLD"
    assert merged[0]["resolving_rule"] == "COVERAGE_GAP_OVERRIDE"
    assert COVERAGE_GAP_OVERRIDE in merged[0]["reason"]


def test_coverage_tie_higher_urgency_wins() -> None:
    """Equal coverage on both sides → action-rank decides (existing behavior)."""
    prior = [
        {
            "ticker": "FPT",
            "action": "EXIT",
            "reason": "broke",
            "coverage_responding": 3,
            "coverage_total": 3,
        }
    ]
    current = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "reason": "stable",
            "coverage_responding": 3,
            "coverage_total": 3,
        }
    ]
    merged = preserve_higher_urgency(prior, current)
    assert merged[0]["action"] == "EXIT"
    assert merged[0]["resolving_rule"] == "AGGREGATOR_PASSTHROUGH"


def test_coverage_gap_one_step_does_not_flip() -> None:
    """Gap of 1 (2/3 vs 3/3) is below threshold → EXIT preserved."""
    prior = [
        {
            "ticker": "FPT",
            "action": "EXIT",
            "reason": "broke",
            "coverage_responding": 2,
            "coverage_total": 3,
        }
    ]
    current = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "reason": "stable",
            "coverage_responding": 3,
            "coverage_total": 3,
        }
    ]
    merged = preserve_higher_urgency(prior, current)
    assert merged[0]["action"] == "EXIT"
    assert merged[0]["resolving_rule"] == "AGGREGATOR_PASSTHROUGH"


def test_legacy_null_coverage_skips_override() -> None:
    """Legacy rows (NULL coverage) fall through to action-rank only."""
    prior = [
        {
            "ticker": "FPT",
            "action": "EXIT",
            "reason": "broke",
            # no coverage fields — predates migration 339
        }
    ]
    current = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "reason": "stable",
            "coverage_responding": 3,
            "coverage_total": 3,
        }
    ]
    merged = preserve_higher_urgency(prior, current)
    assert merged[0]["action"] == "EXIT"
    assert merged[0]["resolving_rule"] == "AGGREGATOR_PASSTHROUGH"
