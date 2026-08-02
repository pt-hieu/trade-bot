"""Audit-trail invariant: every aggregator → published action mismatch must
cite a deterministic resolving rule.

When the position aggregator emits EXIT/TRIM but the published
``daily_recommendations.action`` differs, the rec must cite a deterministic
Python rule (a known marker in the rationale or an explicit
``resolving_rule`` field). A mismatch with no cited rule is a silent
downgrade — auditable failure mode, never an acceptable steady state.

The auditor walks ``position_alerts.alerts`` and compares each ticker's
published rec action. When they differ, one ``published_action_audit``
span is emitted carrying the alert action, the published action, and
whichever resolving rule the rec carries. Markers reuse the
rec-builder / validator strip vocabulary (``shared.rules.audit_tags`` +
the gate-block strings) so any rec built through the deterministic path
already cites a rule.

Under ``ADVOCATE_GATE_MODE=enforce`` (production workflow yml) AND a
downgrade lacks any resolving rule, the auditor raises ``RuntimeError``
instead of letting the silent downgrade ship.
"""

from __future__ import annotations

import logging
import os
from datetime import date

from shared.observability import span as logfire_span
from shared.rules.audit_tags import (
    AGGREGATOR_PASSTHROUGH,
    COVERAGE_GAP_OVERRIDE,
    DERIVED_FROM_BELIEFS,
    DETERMINISTIC_ONLY,
    NO_BELIEF_NO_REC,
    PARTIAL_COVERAGE,
    RECONCILED_FROM_BELIEFS,
)

logger = logging.getLogger(__name__)

# Markers any rec built via the deterministic path already carries. Presence
# of any one of these proves a Python rule, not an LLM whim, decided the
# published action.
_DOWNGRADE_RESOLVING_MARKERS: tuple[str, ...] = (
    "[CONCENTRATION OVERRIDE]",
    PARTIAL_COVERAGE,
    NO_BELIEF_NO_REC,
    DETERMINISTIC_ONLY,
    RECONCILED_FROM_BELIEFS,
    DERIVED_FROM_BELIEFS,
    AGGREGATOR_PASSTHROUGH,
    COVERAGE_GAP_OVERRIDE,
    "[GATE_BLOCK]",
    "[GATED]",
)


def _normalize_action(value: object) -> str:
    return str(value or "").strip().upper()


def audit_action_downgrades(
    *,
    scan_date: date,
    validated_recommendations: list[dict],
    position_alerts: dict,
) -> None:
    """Emit ``published_action_audit`` span per aggregator → published mismatch.

    ``ADVOCATE_GATE_MODE=enforce`` raises on any unaudited downgrade so a
    silent FPT-EXIT-becomes-HOLD regression cannot ship without surfacing.
    """
    enforce_mode = os.environ.get("ADVOCATE_GATE_MODE", "").strip().lower() == "enforce"

    rec_by_ticker: dict[str, dict] = {}
    for rec in validated_recommendations or []:
        ticker_key = (rec.get("ticker") or "").upper()
        if ticker_key:
            rec_by_ticker[ticker_key] = rec

    unaudited: list[tuple[str, str, str]] = []

    for alert in (position_alerts or {}).get("alerts") or []:
        ticker = (alert.get("ticker") or "").upper()
        if not ticker:
            continue
        aggregator_action = _normalize_action(alert.get("action"))
        if not aggregator_action:
            continue
        rec = rec_by_ticker.get(ticker)
        if rec is None:
            continue
        published_action = _normalize_action(rec.get("action"))
        if published_action == aggregator_action:
            continue

        rationale_text = f"{rec.get('rationale') or ''} {rec.get('verdict') or ''}"
        explicit_rule = rec.get("resolving_rule")
        marker_hit = next(
            (marker for marker in _DOWNGRADE_RESOLVING_MARKERS if marker in rationale_text),
            None,
        )
        resolving_rule = explicit_rule or marker_hit
        with logfire_span(
            "published_action_audit",
            scan_date=str(scan_date),
            ticker=ticker,
            aggregator_action=aggregator_action,
            published_action=published_action,
            resolving_rule=resolving_rule,
        ):
            if resolving_rule:
                logger.info(
                    "published_action_audit %s aggregator=%s -> published=%s rule=%s",
                    ticker,
                    aggregator_action,
                    published_action,
                    resolving_rule,
                )
            else:
                unaudited.append((ticker, aggregator_action, published_action))
                logger.error(
                    "PUBLISHED_ACTION_DOWNGRADE_UNAUDITED ticker=%s "
                    "aggregator=%s published=%s — no resolving rule cited",
                    ticker,
                    aggregator_action,
                    published_action,
                )

    if unaudited and enforce_mode:
        raise RuntimeError(
            "PUBLISHED_ACTION_DOWNGRADE_UNAUDITED: "
            f"{len(unaudited)} aggregator action(s) silently downgraded with "
            f"no resolving rule under ADVOCATE_GATE_MODE=enforce — "
            f"{unaudited[:5]}"
        )
