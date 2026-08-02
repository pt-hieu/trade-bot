"""Pure synchronous rules: regime reconciliation, oil patch, workflow classifier.

No async, no DB, no LLM. Imported by the async orchestrators in
``derive.py`` and by the ``post_process_phase1`` flow in ``io.py``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ProducerLeakError(RuntimeError):
    """Raised when a producer-side reconciliation was bypassed and a
    downstream verification caught the resulting drift. Aborts rather than
    silently re-reconciling — single-source contract is broken."""


def extract_risk_regime(macro_metrics: dict | None) -> str:
    """Extract global risk regime from macro metrics, defaulting to CAUTIOUS."""
    if macro_metrics and not macro_metrics.get("error"):
        return macro_metrics.get("global_risk_regime") or "CAUTIOUS"
    print("  [Regime Gate] Macro data unavailable — defaulting to CAUTIOUS (unknown = caution)")
    return "CAUTIOUS"


_RISK_REGIME_TO_MARKET_FLOOR = {
    "CRISIS": "RISK_OFF",
    "ELEVATED": "RISK_OFF",
    "CAUTIOUS": "NEUTRAL",
}

# Ordinal ranking of market_regime values — higher = more optimistic.
_MARKET_REGIME_ORDER = {
    "RISK_ON": 2,
    "NEUTRAL": 1,
    "RISK_OFF": 0,
}


def reconcile_regimes(market_regime: str, global_risk_regime: str) -> str:
    """Cap market_regime optimism based on global risk severity.

    The market_level agent has no geopolitical context (runs in Phase 1
    before geo context is built). This deterministic post-hoc reconciliation
    ensures market_regime reflects macro stress.

    CAUTIOUS → caps at NEUTRAL (so RISK_ON → NEUTRAL, leaves RISK_OFF alone).
    ELEVATED/CRISIS → caps at RISK_OFF.

    Comparison is ordinal (RISK_ON > NEUTRAL > RISK_OFF): a stricter
    regime than the floor is preserved — the floor only lowers, never raises.
    """
    floor = _RISK_REGIME_TO_MARKET_FLOOR.get(global_risk_regime)
    if not floor:
        return market_regime

    market_rank = _MARKET_REGIME_ORDER.get(market_regime)
    floor_rank = _MARKET_REGIME_ORDER.get(floor)
    if market_rank is None or floor_rank is None:
        return market_regime

    if market_rank > floor_rank:
        logger.error(
            "reconcile_regimes: agent emitted %s but global_risk_regime "
            "is %s (floor=%s). Capping to %s. Investigate why the agent "
            "ignored the dual-label injection.",
            market_regime,
            global_risk_regime,
            floor,
            floor,
        )
        print(
            f"  [Regime Reconciliation FAIL-LOUD] {market_regime} -> {floor} "
            f"(global_risk={global_risk_regime})"
        )
        return floor
    return market_regime


def patch_oil_from_commodities(
    macro_metrics: dict | None,
    commodity_prices: dict | None,
) -> None:
    """Backfill missing oil_price from commodity pipeline, recalculate regime."""
    from agents.macro import _is_valid_number

    if not macro_metrics or macro_metrics.get("error"):
        return

    existing_oil = macro_metrics.get("oil_price")
    if _is_valid_number(existing_oil) and existing_oil is not None and existing_oil > 0:
        return

    oil_crude = (commodity_prices or {}).get("oil_crude", {})
    fallback_price = oil_crude.get("price")
    if not _is_valid_number(fallback_price) or fallback_price <= 0:
        logger.warning(
            "patch_oil_from_commodities: all oil sources unavailable — oil_signal remains NORMAL"
        )
        return

    from agents.macro import calculate_global_regime, classify_oil

    fallback_change = oil_crude.get("change_1d_pct") or 0.0
    oil_signal = classify_oil(fallback_price, fallback_change)
    macro_metrics["oil_price"] = fallback_price
    macro_metrics["oil_change_pct"] = fallback_change
    macro_metrics["oil_signal"] = oil_signal
    logger.warning(
        "patch_oil_from_commodities: backfilled oil=%.1f -> %s",
        fallback_price,
        oil_signal,
    )
    print(f"  [Oil Fallback] commodity pipeline: ${fallback_price:.1f}/bbl -> {oil_signal}")

    geo_shock = macro_metrics.get("geopolitical_shock")
    new_regime = calculate_global_regime(
        macro_metrics.get("dxy_signal") or "NEUTRAL",
        macro_metrics.get("vix_signal") or "LOW",
        macro_metrics.get("usd_vnd_signal") or "STABLE",
        False,
        oil_signal,
        active_geopolitical_phase=(geo_shock.get("phase_name") if geo_shock else None),
    )
    if new_regime != macro_metrics.get("global_risk_regime"):
        logger.warning(
            "Oil fallback regime recalc: %s -> %s",
            macro_metrics["global_risk_regime"],
            new_regime,
        )
        macro_metrics["global_risk_regime"] = new_regime


def determine_adaptive_workflow(
    early_mode, market_regime, global_risk_regime, scan_date, deployable_cash, sectors
):
    """Determine adaptive workflow via meta-controller.

    Returns (workflow_config, sectors_for_phase2).
    """
    from agents.meta_controller import (
        determine_workflow,
        format_routing_summary,
        get_workflow_config,
    )
    from shared.market_calendar import is_trading_day

    routing = determine_workflow(
        trading_mode=early_mode,
        market_regime=market_regime,
        global_macro_regime=global_risk_regime,
        is_trading_day=is_trading_day(scan_date),
        deployable_cash=deployable_cash,
    )
    workflow_config = get_workflow_config(routing.workflow)
    print(f"\nMeta-Controller:\n{format_routing_summary(routing)}")

    sectors_for_phase2 = sectors if workflow_config.get("run_sectors", True) else {}
    if not sectors_for_phase2:
        print("  [Meta-Controller] Skipping sector analysis")

    return workflow_config, sectors_for_phase2
