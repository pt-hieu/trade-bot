"""Macro signal transmission for ticker briefings.

Cross-references company macro_sensitivities against live macro_metrics
signals to produce per-ticker TAILWIND/HEADWIND labels. Geo-exposure
classification (GEO_BENEFICIARY / GEO_VICTIM / GEO_MIXED / GEO_EXPOSED)
is owned by `shared.rules.catalyst_override.classify_geo_label`; the
briefing renderer pre-computes a labels dict once per sector call and
passes per-ticker labels directly into `format_ticker_briefing`.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Maps macro_sensitivities factor names to live macro_metrics signals.
# Each entry defines which signal values indicate a negative or positive move.
# Cross-referenced with sensitivity direction to produce TAILWIND/HEADWIND.
FACTOR_TO_MACRO_SIGNAL: dict[str, dict] = {
    "usd_vnd": {
        "key": "usd_vnd_signal",
        "negative_signals": ["PRESSURE", "FLIGHT"],
        "positive_signals": ["STABLE"],
    },
    "vix": {
        "key": "vix_signal",
        "negative_signals": ["HIGH", "EXTREME"],
        "positive_signals": ["LOW"],
    },
    "global_risk": {
        "key": "global_risk_regime",
        "negative_signals": ["ELEVATED", "CRISIS"],
        "positive_signals": ["CALM"],
    },
    "dxy": {
        "key": "dxy_signal",
        "negative_signals": ["STRONG"],
        "positive_signals": ["WEAK"],
    },
}

MAGNITUDE_WEIGHTS: dict[str, float] = {"HIGH": 2, "MEDIUM": 1, "LOW": 0.5}


def format_dual_regime_labels(
    *,
    global_risk_regime: str | None,
    technical_regime: str | None,
    technical_confidence: float | None = None,
    style: str = "block",
) -> str:
    """Single source of truth for the dual-regime context block (Phase 2 §2.8).

    Every regime-emitting agent (entry_strategist, critic, sector_rotation,
    meta_controller) renders the same authoritative/context pairing. Centralising
    the wording here means a future tweak to the AUTHORITATIVE phrasing
    propagates without combing N writers.

    Styles:
      * ``"block"`` — multiline; used in entry_strategist's MARKET REGIME
        injection where the model needs the explicit AUTHORITATIVE marker.
      * ``"compact"`` — ``"X (technical: Y)"``; used by meta_controller's
        ``context_summary`` for the routing log line.
      * ``"pair"`` — two ``"Label: VALUE"`` lines; used by critic's
        ``context_parts`` list which is later joined.
    """
    risk = global_risk_regime or "CAUTIOUS"
    technical = technical_regime or "NEUTRAL"
    if style == "compact":
        return f"{risk} (technical: {technical})"
    if style == "pair":
        return (
            f"Global Risk Regime (AUTHORITATIVE): {risk}\n"
            f"Technical Market Regime (context only): {technical}"
        )
    confidence_suffix = (
        f" ({technical_confidence:.0%})" if isinstance(technical_confidence, (int, float)) else ""
    )
    return (
        "GLOBAL RISK REGIME (AUTHORITATIVE — emit this label): "
        f"{risk}\n"
        f"Technical market regime (CONTEXT ONLY): {technical}{confidence_suffix}"
    )


def format_vnindex_catalyst_lines(catalysts: list[dict] | None) -> list[str]:
    """Render VN-INDEX-positive macro catalysts for the macro brief (SWI-204).

    Filter: ``affected_tickers == ['VN-INDEX']`` AND ``impact == 'POSITIVE'``
    AND ``confidence ∈ {HIGH, MEDIUM}`` AND ``expected_status ∈ {IMMINENT, ACTIVE}``.
    Returns ``["Macro+: <event> (<confidence>)"]`` lines so the consumer can
    splice directly into the regime block. Empty list when no rows pass.
    """
    if not catalysts:
        return []
    lines: list[str] = []
    for catalyst in catalysts:
        affected = catalyst.get("affected_tickers") or catalyst.get("affected") or []
        if list(affected) != ["VN-INDEX"]:
            continue
        if (catalyst.get("impact") or "").upper() != "POSITIVE":
            continue
        confidence = (catalyst.get("confidence") or "").upper()
        if confidence not in {"HIGH", "MEDIUM"}:
            continue
        status = (catalyst.get("expected_status") or "").upper()
        if status not in {"IMMINENT", "ACTIVE"}:
            continue
        event = (catalyst.get("event") or "").strip()
        if not event:
            continue
        lines.append(f"Macro+: {event[:80]} ({confidence})")
    return lines


def format_macro_signal_transmission(
    sensitivities: list[dict],
    macro_metrics: dict,
) -> list[str]:
    """Build TAILWIND/HEADWIND parts for non-commodity macro factors.

    Cross-references macro_sensitivities against live macro_metrics signals.
    Only emits for factors with a clear directional signal (not neutral).
    """
    parts: list[str] = []
    for sensitivity in sensitivities:
        factor = sensitivity.get("factor") or ""
        direction = (sensitivity.get("direction") or "").upper()
        if direction not in ("POSITIVE", "NEGATIVE"):
            continue

        signal_config = FACTOR_TO_MACRO_SIGNAL.get(factor)
        if not signal_config:
            continue

        signal_value = macro_metrics.get(signal_config["key"])
        if not signal_value:
            continue
        signal_value = str(signal_value).upper()

        negative_signals = signal_config.get("negative_signals") or []
        positive_signals = signal_config.get("positive_signals") or []

        is_negative_move = signal_value in negative_signals
        is_positive_move = signal_value in positive_signals

        if not is_negative_move and not is_positive_move:
            continue

        # POSITIVE sensitivity + negative move = HEADWIND (and vice versa)
        # NEGATIVE sensitivity + negative move = TAILWIND (inverse relationship)
        if direction == "POSITIVE":
            impact = "HEADWIND" if is_negative_move else "TAILWIND"
        else:  # NEGATIVE
            impact = "TAILWIND" if is_negative_move else "HEADWIND"

        label = factor.replace("_", "/").upper()
        parts.append(f"{label}: {signal_value} -> {impact}")
    return parts
