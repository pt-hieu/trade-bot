"""Conservative alert derivation when positions_aggregator degrades.

Kicks in when the LLM aggregator hits a TimeoutError / ProviderUnavailable.
The fallback reads the 3 sub-analyst reports (technical, value, thesis)
and picks the most cautious per-ticker action via strict precedence:

    EXIT > TRIM > EVALUATE > HOLD

ADD is intentionally demoted to the lowest rank so the fallback NEVER
deploys new capital — LLM confirmation is required for ADD.

Notes carry the `[DERIVED_FROM_BELIEFS]` prefix so reviewers can tell a
degraded run apart from a healthy one in pipeline-review bundles.
"""

from __future__ import annotations

import logging

from shared.rules.audit_tags import DERIVED_FROM_BELIEFS

from .belief_collection import collect_beliefs_from_views
from .positions_ensemble_models import AnalystReport, AnalystView
from .positions_ensemble_rules import _calc_consensus, _get_dissent

logger = logging.getLogger(__name__)

# ADD=0 is load-bearing: fallback collapses ADD → HOLD downstream,
# but also needs ADD to lose every tie-break so a lone ADD never wins
# over a HOLD peer.
_FALLBACK_ACTION_RANK: dict[str, int] = {
    "EXIT": 4,
    "TRIM": 3,
    "EVALUATE": 2,
    "HOLD": 1,
    "ADD": 0,
}


def collect_ticker_union(
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
) -> set[str]:
    """Union of tickers seen across the 3 analyst reports."""
    tickers: set[str] = set()
    for report in (technical, value, thesis):
        for view in report.views:
            if view.ticker:
                tickers.add(view.ticker.upper())
    return tickers


def _urgency_from_confidence(max_confidence: int) -> str:
    if max_confidence >= 8:
        return "high"
    if max_confidence >= 5:
        return "medium"
    return "low"


def _first_dissenting_reason(
    ranked: list[tuple[int, AnalystView]],
    dominant_action: str,
) -> str | None:
    for _, view in ranked[1:]:
        if (view.action or "HOLD").upper() == dominant_action:
            continue
        if view.reasoning:
            return view.reasoning.strip()[:200]
    return None


def derive_alerts_from_subreports(
    *,
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
    degradation_type: str,
) -> dict:
    """Build conservative per-ticker alerts from sub-agent views.

    Sub-agent beliefs are passed through so downstream persistence and
    calibration keep working during degradation.
    """
    views_by_ticker: dict[str, list[AnalystView]] = {}
    for report in (technical, value, thesis):
        for view in report.views:
            if not view.ticker:
                continue
            views_by_ticker.setdefault(view.ticker.upper(), []).append(view)

    alerts_out: list[dict] = []
    beliefs_out = collect_beliefs_from_views(
        [("technical", technical), ("value", value), ("thesis", thesis)],
        agent_key_prefix="positions",
        scope_name="positions:fallback",
        logger=logger,
    )

    for ticker, views in views_by_ticker.items():
        ranked = [
            (_FALLBACK_ACTION_RANK.get((view.action or "HOLD").upper(), 1), view) for view in views
        ]
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        _, dominant = ranked[0]
        dominant_action = (dominant.action or "HOLD").upper()
        # Fallback never deploys capital — ADD collapses to HOLD.
        if dominant_action == "ADD":
            dominant_action = "HOLD"

        matching = [v for v in views if (v.action or "HOLD").upper() == dominant_action]
        confidences = [int(v.confidence or 0) for v in matching]
        urgency = _urgency_from_confidence(max(confidences) if confidences else 0)

        from shared.text_utils import split_first_sentence

        reasoning_excerpt = split_first_sentence(dominant.reasoning, max_len=180)
        # Rationale is reader-facing. The degradation_type + fallback
        # provenance go into `source_note` (internal only) so readers see
        # clean belief-derived reasoning, not internal failure tags.
        reason = (
            f"{DERIVED_FROM_BELIEFS} {reasoning_excerpt}"
            if reasoning_excerpt
            else f"{DERIVED_FROM_BELIEFS} committee view"
        )
        source_note = f"positions_aggregator degraded ({degradation_type})"

        alerts_out.append(
            {
                "ticker": ticker,
                "action": dominant_action,
                "urgency": urgency,
                "reason": reason,
                "source_note": source_note,
                "target": "N/A",
                "stop": "N/A",
                "entry_price": None,
                "current_price": None,
                "pct_from_entry": None,
                "weight_pct": None,
                "volume_signal": None,
                "counter_thesis": _first_dissenting_reason(ranked, dominant_action),
                "consensus": _calc_consensus(ticker, dominant_action, technical, value, thesis),
                "dissenting_views": _get_dissent(ticker, dominant_action, technical, value, thesis),
            }
        )

    return {
        "alerts": alerts_out,
        "summary": (
            f"{DERIVED_FROM_BELIEFS} positions_aggregator degraded "
            f"({degradation_type}); {len(alerts_out)} alerts via conservative "
            "precedence (EXIT > TRIM > EVALUATE > HOLD; ADD blocked)."
        ),
        "beliefs": beliefs_out,
    }
