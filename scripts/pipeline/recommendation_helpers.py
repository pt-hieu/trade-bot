"""Deterministic helpers for recommendation enrichment.

Verdict sentence builder, confidence mapping, and counter-thesis formatting.
Pure Python — no LLM, no async, no DB dependencies.
"""

from agents.belief_mapping import _SIGNAL_CONFIDENCE_MAP
from agents.retro.parser import (
    SECTION_LONG_TERM,
    SECTION_MY_HOLDINGS,
    SECTION_SKIP_THESE,
    SECTION_TOP_PICKS,
    SECTION_WHAT_TO_DO,
)
from shared.formatting import format_price_k
from shared.rules.exit_strategy import format_rr_display, read_rr

# Reuse the single choke point from belief_mapping for signal confidence.
# Longterm conviction labels use the same scale (case-insensitive).
SIGNAL_CONFIDENCE = _SIGNAL_CONFIDENCE_MAP
CONVICTION_CONFIDENCE = {"high": 0.8, "medium": 0.5, "low": 0.3}

# Ensemble consensus → confidence (aligned with final action, not vote distribution)
CONSENSUS_CONFIDENCE = {
    "unanimous": 0.9,
    "majority": 0.7,
    "split": 0.4,
    "minority_override": 0.3,  # LLM overrode 2/3 sub-agents
    "override": 0.2,  # LLM overrode all sub-agents
    "no_data": 0.3,  # sub-agent had no views for this ticker
}


RANDOM_CHANCE_ACCURACY = 1 / 3  # direction accuracy of a random 3-class classifier
ACCURACY_RANGE = 0.54  # empirical ceiling (0.87) minus random chance (0.33)
MIN_DISCOUNT_FACTOR = 0.5  # random-chance agents get 50% confidence penalty


def accuracy_discounted_confidence(
    consensus_label: str,
    calibration_stats: dict[str, dict] | None = None,
) -> float:
    """Discount consensus confidence by analyst direction accuracy.

    Uses direction_accuracy (not Brier) to avoid double-discounting with
    belief_aggregation.py which already Brier-weights probabilities.
    """
    base_confidence = CONSENSUS_CONFIDENCE.get(consensus_label, 0.5)
    if not calibration_stats:
        return base_confidence

    accuracy_values = [
        float(s.get("direction_accuracy") or RANDOM_CHANCE_ACCURACY)
        for s in calibration_stats.values()
        if s.get("direction_accuracy") is not None
    ]
    if not accuracy_values:
        return base_confidence

    avg_accuracy = sum(accuracy_values) / len(accuracy_values)
    discount = max(
        MIN_DISCOUNT_FACTOR,
        min(1.0, (avg_accuracy - RANDOM_CHANCE_ACCURACY) / ACCURACY_RANGE + MIN_DISCOUNT_FACTOR),
    )
    return round(base_confidence * discount, 2)


def format_dissent(views: list[str] | None) -> str | None:
    """Join ensemble dissenting views into a counter-thesis string."""
    if not views:
        return None
    return "; ".join(views)


def build_verdict(
    section: str,
    action: str,
    rec_data: dict,
    holdings_data: dict | None = None,
) -> str | None:
    """Build a deterministic 1-2 sentence verdict from available data.

    Returns None only when insufficient data exists to form a meaningful sentence.
    """
    action = (action or "").upper()

    if section == SECTION_TOP_PICKS:
        return _verdict_top_picks(action, rec_data)

    if section == SECTION_MY_HOLDINGS:
        return _verdict_holdings(action, rec_data, holdings_data)

    if section in (SECTION_SKIP_THESE, SECTION_WHAT_TO_DO):
        return _verdict_sector(action, rec_data)

    if section == SECTION_LONG_TERM:
        return _verdict_longterm(rec_data)

    return None


def _verdict_top_picks(action: str, rec_data: dict) -> str | None:
    entry = rec_data.get("entry") or rec_data.get("entry_price")
    target = rec_data.get("target") or rec_data.get("target_price")
    stop = rec_data.get("stop") or rec_data.get("stop_price")
    rr = read_rr(rec_data)
    if not (entry and target and stop):
        return None
    upside_pct = round((target - entry) / entry * 100, 1) if entry else 0
    action_label = "LIMIT BUY" if action == "LIMIT_BUY" else action
    return (
        f"{action_label} at {format_price_k(entry)}, "
        f"target {format_price_k(target)} (+{upside_pct}%), "
        f"stop {format_price_k(stop)}, R:R {format_rr_display(rr, suffix=':1')}"
    )


def _verdict_holdings(action: str, rec_data: dict, holdings_data: dict | None) -> str:
    source = rec_data.get("source", "")
    pct_from_entry = (holdings_data or {}).get("pct_from_entry")
    pct_display = f"{pct_from_entry:+.1f}% from entry" if pct_from_entry is not None else ""

    if source == "auto_hold":
        suffix = f", {pct_display}" if pct_display else ""
        return f"HOLD — no alert triggered{suffix}"

    if action == "EXIT":
        return f"EXIT — {pct_display}" if pct_display else "EXIT — stop breached"
    if action == "TRIM":
        weight = (holdings_data or {}).get("weight_pct")
        weight_note = f"weight {weight:.1f}%" if weight else ""
        reason_fragment = weight_note or pct_display or "rebalance"
        return f"TRIM — {reason_fragment}"
    if action == "ADD":
        return f"ADD — {pct_display}" if pct_display else "ADD on pullback"
    # HOLD (default)
    if pct_display:
        return f"HOLD — {pct_display}"
    return "HOLD — monitoring"


def _verdict_sector(action: str, rec_data: dict) -> str:
    note = rec_data.get("note") or ""
    key_risk = rec_data.get("key_risk")
    base = f"{action} — {note}" if note else action
    if key_risk:
        base += f". Risk: {key_risk}"
    return base


def _verdict_longterm(rec_data: dict) -> str:
    entry_zone = rec_data.get("entry_zone") or 0
    conviction = rec_data.get("conviction") or "Medium"
    if entry_zone:
        return f"WATCH for entry near {format_price_k(entry_zone)} ({conviction} conviction)"
    return f"WATCH — {conviction} conviction"
