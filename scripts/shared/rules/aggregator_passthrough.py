"""Cross-run urgency preservation for positions_aggregator.

Phase 2 §2.4 — the 2026-04-28 silent FPT EXIT→HOLD shipped because the
positions_aggregator ran twice on the same scan_date: the first run
succeeded with EXIT FPT / TRIM TCB; the second run failed and the
fallback (`derive_alerts_from_subreports`) voted HOLD because the
sub-agent committee on its own had not converged on EXIT for that day.

The fallback rank table at ``positions_ensemble_fallback._FALLBACK_ACTION_RANK``
preserves the most-cautious action across the THREE sub-agent views, but
not across the TWO aggregator runs. This module is the deterministic
rule that does the latter.

Contract:
    prior_alerts (from a successful earlier run in the same scan_date)
    + current_alerts (from a fallback / retry run)
    →
    merged alerts where each ticker carries the HIGHER-urgency action,
    citing the resolving rule in the rationale so audit can attribute.

Precedence reuses ``_FALLBACK_ACTION_RANK`` from
``positions_ensemble_fallback`` so cross-run merging stays consistent
with the within-run rank.

Pure deterministic Python — no async / DB / LLM.
"""

from __future__ import annotations

import logging
from typing import TypedDict

from shared.rules.audit_tags import (
    AGGREGATOR_PASSTHROUGH,
    COVERAGE_GAP_OVERRIDE,
    RECONCILED_FROM_BELIEFS,
)

logger = logging.getLogger(__name__)


# Mirrors `_FALLBACK_ACTION_RANK` from `positions_ensemble_fallback.py`.
# Kept module-local to avoid an import cycle (the fallback module imports
# from `shared.rules.audit_tags`; we co-locate the rank with the rule
# layer so it can ship before the fallback module is even loaded).
_ACTION_RANK: dict[str, int] = {
    "EXIT": 4,
    "TRIM": 3,
    "EVALUATE": 2,
    "HOLD": 1,
    "ADD": 0,
    "WAIT": 0,
    "WATCH": 0,
}

PASSTHROUGH_RULE_TAG = AGGREGATOR_PASSTHROUGH


class _Alert(TypedDict, total=False):
    ticker: str
    action: str
    urgency: str
    reason: str
    source_note: str
    coverage_responding: int
    coverage_total: int


def _rank(action: str | None) -> int:
    return _ACTION_RANK.get((action or "HOLD").upper(), 1)


def _coverage_known(alert: dict) -> tuple[int, int] | None:
    """Return (responding, total) when both fields are sane integers.

    NULL on either side means the row predates migration 339; in that case
    the merge falls through to action-rank only (no COVERAGE_GAP_OVERRIDE).
    """
    responding = alert.get("coverage_responding")
    total = alert.get("coverage_total")
    if (
        isinstance(responding, int)
        and isinstance(total, int)
        and not isinstance(responding, bool)
        and not isinstance(total, bool)
        and 1 <= responding <= total
    ):
        return (responding, total)
    return None


# Coverage-gap heuristic from the SWI-183 incident: attempt-1 1/3 EXIT vs
# attempt-2 3/3 HOLD. Require at least 2 more responding analysts before
# the higher-coverage HOLD overrides the lower-coverage EXIT — small gaps
# (1-step) are not enough evidence to flip a higher-urgency action.
_COVERAGE_GAP_OVERRIDE_MIN: int = 2


def preserve_higher_urgency(
    prior_alerts: list[dict] | None,
    current_alerts: list[dict] | None,
) -> list[dict]:
    """Return merged alerts where higher-urgency action wins per ticker.

    When prior_alerts and current_alerts disagree on a ticker, the
    HIGHER-urgency action is preserved and the resolving_rule is set to
    ``[AGGREGATOR_PASSTHROUGH]`` so ``published_action_audit`` attributes
    the override to this deterministic rule (not a silent downgrade).

    ``prior_alerts is None`` (no successful earlier run) → return
    current_alerts unchanged.

    Tickers in prior but not in current are appended to the result.
    Tickers in current but not in prior are kept as-is.
    """
    current_list = list(current_alerts or [])
    if not prior_alerts:
        return current_list

    by_ticker_current: dict[str, dict] = {
        (a.get("ticker") or "").upper(): a for a in current_list if a.get("ticker")
    }
    merged: list[dict] = []
    seen: set[str] = set()

    for prior in prior_alerts:
        ticker = (prior.get("ticker") or "").upper()
        if not ticker:
            continue
        seen.add(ticker)
        current = by_ticker_current.get(ticker)
        if current is None:
            # Prior had a view, current run dropped the ticker entirely
            # (e.g. fallback didn't see the ticker in any sub-report).
            # Preserve prior with passthrough tag.
            merged.append(_with_passthrough_tag(prior, prior, dropped_in_current=True))
            continue
        winner, rule = _decide(prior, current)
        merged.append(winner)
        if rule == "AGGREGATOR_PASSTHROUGH":
            logger.error(
                "aggregator_passthrough: ticker=%s prior=%s > current=%s — "
                "preserving prior with [AGGREGATOR_PASSTHROUGH] resolving rule",
                ticker,
                prior.get("action"),
                current.get("action"),
            )
        elif rule == "COVERAGE_GAP_OVERRIDE":
            logger.error(
                "aggregator_passthrough: ticker=%s prior=%s (cov %s/%s) "
                "yields to current=%s (cov %s/%s) under [COVERAGE_GAP_OVERRIDE] "
                "— higher-coverage attempt wins",
                ticker,
                prior.get("action"),
                prior.get("coverage_responding"),
                prior.get("coverage_total"),
                current.get("action"),
                current.get("coverage_responding"),
                current.get("coverage_total"),
            )

    # Tickers in current that prior didn't have — keep as-is.
    for ticker, alert in by_ticker_current.items():
        if ticker not in seen:
            merged.append(alert)

    return merged


def _decide(prior: dict, current: dict) -> tuple[dict, str]:
    """Return (winning_alert_with_tag, resolving_rule_name).

    Three branches:
      - COVERAGE_GAP_OVERRIDE: current has materially higher coverage AND prior
        outranks current → current wins (with override tag citing the gap).
      - AGGREGATOR_PASSTHROUGH: prior outranks current and gap rule does not
        apply → prior wins (with passthrough tag).
      - CURRENT: current matches or outranks prior → current wins as-is.
    """
    prior_rank = _rank(prior.get("action"))
    current_rank = _rank(current.get("action"))
    prior_cov = _coverage_known(prior)
    current_cov = _coverage_known(current)

    if (
        prior_cov is not None
        and current_cov is not None
        and prior_rank > current_rank
        and current_cov[0] - prior_cov[0] >= _COVERAGE_GAP_OVERRIDE_MIN
    ):
        return _with_coverage_gap_override_tag(current, prior), "COVERAGE_GAP_OVERRIDE"

    if prior_rank > current_rank:
        return _with_passthrough_tag(prior, current), "AGGREGATOR_PASSTHROUGH"

    return current, "CURRENT"


def _with_coverage_gap_override_tag(current: dict, prior: dict) -> dict:
    """Clone current with coverage-gap override citation in the reason."""
    prior_resp = prior.get("coverage_responding")
    prior_total = prior.get("coverage_total")
    curr_resp = current.get("coverage_responding")
    curr_total = current.get("coverage_total")
    suffix = (
        f" {COVERAGE_GAP_OVERRIDE} prior aggregator run had "
        f"{prior_resp}/{prior_total} coverage emitting {prior.get('action')}; "
        f"current run has {curr_resp}/{curr_total} coverage emitting "
        f"{current.get('action')}; preferring higher-coverage attempt."
    )
    enriched = dict(current)
    enriched["resolving_rule"] = "COVERAGE_GAP_OVERRIDE"
    enriched["reason"] = f"{(current.get('reason') or '').strip()}{suffix}"
    if "source_note" not in enriched:
        enriched["source_note"] = "aggregator_passthrough coverage-gap override"
    return enriched


def _with_passthrough_tag(
    prior: dict,
    current: dict,
    *,
    dropped_in_current: bool = False,
) -> dict:
    """Clone prior with `resolving_rule` and a citation in the reason.

    Keeps audit observability: published_action_audit walks
    `position_alerts.alerts`, sees the prior action (which differs from
    whatever the LLM re-emitted on a later phase), and attributes the
    flip to a deterministic rule rather than flagging silent downgrade.
    """
    if dropped_in_current:
        current_clause = "dropped ticker"
    else:
        current_action = current.get("action")
        current_clause = f"voted {current_action}"
    suffix = (
        f" {PASSTHROUGH_RULE_TAG} prior aggregator run preserved "
        f"({prior.get('action')}); current run {current_clause}."
    )
    enriched = dict(prior)
    enriched["resolving_rule"] = "AGGREGATOR_PASSTHROUGH"
    enriched["reason"] = f"{RECONCILED_FROM_BELIEFS} {(prior.get('reason') or '').strip()}{suffix}"
    if "source_note" not in enriched:
        enriched["source_note"] = "aggregator_passthrough cross-run preservation"
    return enriched


__all__ = [
    "PASSTHROUGH_RULE_TAG",
    "preserve_higher_urgency",
]
