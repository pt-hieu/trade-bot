"""Deterministic Entry/Stop/Target/R:R computation from levels (pure functions)."""

from __future__ import annotations

import logging
from typing import Literal

import logfire

from shared.calibration_overlay import get_calibrated_entry_gap
from shared.rules.rr_math import compute_net_rr_diagnosed, compute_net_rr_only
from shared.trading_config import get_trading_config

from .prose import is_structural_uptrend

logger = logging.getLogger(__name__)

SetupState = Literal["triggered", "conditional", "invalid"]

# Buffer below swing low for stop placement
_STOP_BUFFER_PCT = 0.02

# LeBeau mid-range swing — VN noise eats 1× ATR stops (~60% of winners' MAE > 1× ATR).
ATR_STOP_MULT = 2.0

# Scales the volatility-target candidate only — never shrinks structural resistance.
REGIME_TARGET_MULT = {
    "CALM": 1.3,
    "NEUTRAL": 1.0,
    "CAUTIOUS": 0.9,
    "ELEVATED": 0.8,
    "RISK_OFF": 0.7,
    "CRISIS": 0.6,
}

# Aggressive target must beat conservative by this factor to be shipped.
_AGGRESSIVE_RR_STRETCH_FACTOR = 1.15

# Gap threshold: if close is >1.5% above support, add market entry setup
_MARKET_ENTRY_GAP_PCT = 1.5


def _resolve_stop_support(levels: dict) -> float | None:
    """Resolve the entry-support level for stop derivation (SWI-3a).

    Prefers the MA-free `nearest_swing_low` (added by `find_nearest_levels`)
    over the MA-inclusive `nearest_support`, so a moving average sitting
    just below price never collapses the risk denominator. Falls back
    through `swing_low` for legacy callers / partial level dicts.

    Used by both the primary builder branch and the rescue branch so the
    fallback chain is single-sourced.
    """
    return (
        levels.get("nearest_swing_low") or levels.get("nearest_support") or levels.get("swing_low")
    )


def _emit_subsetup_rejection(*, ticker: str, error: str, stage: str) -> None:
    """Log a sub-setup (market_entry / pullback) build failure for diagnosis.

    Sub-setups don't return through ``_invalid_setup`` (they augment a valid
    primary setup), so they need their own emission point to keep
    ``setup_rejected`` Logfire dashboards complete.
    """
    logfire.info(
        "setup_rejected",
        ticker=ticker,
        reason=error,
        stage=stage,
        missing_fields=[],
    )


def _invalid_setup(
    error: str,
    *,
    ticker: str = "",
    levels: dict | None = None,
    stage: str = "unknown",
) -> dict:
    """Return an invalid-setup shape with conditional-plan fields populated.

    Builder reads `setup_state`/`plan_shape` to decide whether to ship
    trigger/stop/target on a WATCH/WAIT row. Invalid means: no level
    geometry usable — neither a triggered BUY nor a conditional plan.
    """
    logfire.info(
        "setup_rejected",
        ticker=ticker,
        reason=error,
        stage=stage,
        missing_fields=[
            field
            for field in ("nearest_support", "swing_low", "nearest_resistance", "atr")
            if not (levels or {}).get(field)
        ],
    )
    return {
        "error": error,
        "valid": False,
        "setup_state": "invalid",
        "plan_shape": "NONE",
        "trigger_price": None,
        "invalidation_note": None,
    }


def _derive_plan_shape_from_levels(
    levels: dict,
    close: float,
    structural_uptrend: bool,
) -> tuple[str, str | None]:
    """Best-effort plan_shape from levels alone (no RSI/MA context).

    Returned ``invalidation_note`` is a short heuristic — builder may
    overwrite once it has full technicals + LLM signal.
    """
    nearest_resistance = levels.get("nearest_resistance") or levels.get("swing_high")
    nearest_support = levels.get("nearest_support") or levels.get("swing_low")

    if nearest_resistance and close and close >= nearest_resistance * 0.97:
        return (
            "BREAKOUT",
            f"Void if close back below {nearest_resistance:.0f}",
        )
    if structural_uptrend:
        return ("PULLBACK", "Void if close < MA50")
    if nearest_support:
        return ("BOUNCE", f"Void if close < {nearest_support:.0f}")
    return ("NONE", None)


def _build_single_setup(
    ticker: str,
    entry: float,
    stop: float,
    target: float,
    close: float,
    cost_pct: float = 0.0,
) -> dict:
    """Build a single entry/stop/target setup dict with net-of-cost R:R.

    ``risk_per_share`` and ``shares`` use gross risk — cost is reserved via
    the trade-level risk budget, not double-counted in position sizing.
    """
    risk_gross = entry - stop
    if risk_gross <= 0:
        return {"error": f"Invalid risk: entry {entry} <= stop {stop}"}

    rr_net, rr_gross, diag = compute_net_rr_diagnosed(entry, stop, target, cost_pct)

    # SWI-358: surface degenerate-risk / extreme-rr geometry for investigation.
    # Setup remains valid=True (user binding decision: visibility, not gating);
    # downstream scoring_health turns these into a hard fail when they appear
    # on shipped rows.
    if diag["degenerate_risk"] or diag["extreme_rr"]:
        logfire.warning(
            "rr_geometry_anomaly",
            ticker=ticker,
            entry=entry,
            stop=stop,
            target=target,
            **diag,
        )

    max_risk_vnd = get_trading_config().max_risk_per_trade
    shares = int(max_risk_vnd / risk_gross) if risk_gross > 0 else 0

    return {
        "ticker": ticker,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_reward": rr_net,
        "risk_reward_gross": rr_gross,
        "risk_per_share": risk_gross,
        "shares": shares,
        "position_vnd": shares * entry,
        "valid": rr_net > 0,
        "close": close,
        "degenerate_risk": diag["degenerate_risk"],
        "extreme_rr": diag["extreme_rr"],
    }


def _stretch_rr_from_target(
    entry: float,
    stop: float,
    stretch_target: float,
    cost_pct: float,
) -> float | None:
    """Display hint only — gates compare on the chosen target's R:R, never the stretch."""
    return compute_net_rr_only(entry, stop, stretch_target, cost_pct)


def compute_setup_from_levels(
    levels: dict,
    close: float,
    ticker: str = "",
    structural_uptrend: bool = False,
    atr: float | None = None,
    risk_regime: str | None = None,
) -> dict:
    """Compute Entry/Stop/Target/R:R from pre-computed levels (pure function).

    Returns both a support entry (limit order at support) and, when price is
    meaningfully above support (>1.5%), a market entry (buy at current price).

    Target selection is deterministic: conservative (nearest resistance) by
    default; aggressive (swing_high / volatility-scaled trend target) only
    when ``structural_uptrend=True`` AND the aggressive R:R beats conservative
    by a meaningful stretch factor.
    """
    cfg = get_trading_config()
    cost_pct = cfg.transaction_cost_pct or 0.0

    support = _resolve_stop_support(levels)
    nearest_resistance = levels.get("nearest_resistance") or levels.get("swing_high")
    swing_high = levels.get("swing_high")
    swing_low = levels.get("swing_low") or levels.get("range_20d_low")

    if not support or not swing_low:
        logger.warning(
            "[setup_calc] no conditional shape for %s: missing support/swing_low levels=%s",
            ticker,
            levels,
        )
        return _invalid_setup(
            "Insufficient level data for trade setup",
            ticker=ticker,
            levels=levels,
            stage="missing_levels",
        )

    regime_mult = REGIME_TARGET_MULT.get((risk_regime or "").upper(), 1.0)

    resistance_projected = False
    if not nearest_resistance:
        if not (structural_uptrend and atr and atr > 0):
            logger.warning(
                "[setup_calc] no conditional shape for %s: no resistance + not in uptrend",
                ticker,
            )
            return _invalid_setup(
                f"No resistance levels for {ticker} (not in structural uptrend)",
                ticker=ticker,
                levels=levels,
                stage="no_resistance",
            )
        support_based = round(support + atr * 4 * regime_mult)
        close_based = round(close + atr * 2 * regime_mult)
        nearest_resistance = max(support_based, close_based)
        resistance_projected = True

    raw_stop = round(swing_low * (1 - _STOP_BUFFER_PCT))

    if atr is not None and atr > 0 and support > 0:
        atr_based_stop = round(support - atr * ATR_STOP_MULT)
        stop = min(raw_stop, atr_based_stop)
    else:
        stop = raw_stop

    if support <= stop:
        # Rescue branch: primary read already exhausted the resolver chain;
        # widen to the structural swing_low (the deepest available structural
        # support) before declaring the setup invalid.
        support = swing_low
        if support <= stop:
            logger.warning(
                "[setup_calc] no conditional shape for %s: support %s <= stop %s",
                ticker,
                support,
                stop,
            )
            return _invalid_setup(
                f"No valid entry for {ticker}: support {support} <= stop {stop}",
                ticker=ticker,
                levels=levels,
                stage="support_le_stop",
            )

    # SWI-3a: target derivation reads the MA-free `nearest_swing_target`
    # when present. `nearest_resistance` (MA-inclusive) is the breakout/
    # prose semantic and is acceptable as a target ONLY when no swing
    # target exists (e.g., projected from ATR in the resistance-projected
    # branch above).
    conservative_target = levels.get("nearest_swing_target") or nearest_resistance

    aggressive_candidates = [v for v in [swing_high, levels.get("range_20d_high")] if v]
    aggressive_target: float | None = max(aggressive_candidates) if aggressive_candidates else None
    if aggressive_target and aggressive_target <= conservative_target * 1.02:
        aggressive_target = None

    if structural_uptrend and atr and aggressive_target is not None:
        vol_target = round(support + atr * 4 * regime_mult)
        if regime_mult >= 1.0:
            aggressive_target = max(aggressive_target, vol_target)
        else:
            aggressive_target = max(conservative_target, min(aggressive_target, vol_target))
            if aggressive_target <= conservative_target * 1.02:
                aggressive_target = None

    risk_gross = support - stop
    conservative_rr_gross = (conservative_target - support) / risk_gross if risk_gross > 0 else 0.0
    aggressive_rr_gross = (
        (aggressive_target - support) / risk_gross if aggressive_target and risk_gross > 0 else 0.0
    )

    use_aggressive = (
        structural_uptrend
        and aggressive_target is not None
        and aggressive_rr_gross > conservative_rr_gross * _AGGRESSIVE_RR_STRETCH_FACTOR
    )
    target_basis: Literal["conservative", "aggressive"]
    if use_aggressive and aggressive_target is not None:
        target = aggressive_target
        target_basis = "aggressive"
    else:
        target = conservative_target
        target_basis = "conservative"

    stretch_target = (
        aggressive_target if aggressive_target is not None and aggressive_target > target else None
    )

    result = _build_single_setup(ticker, support, stop, target, close, cost_pct=cost_pct)
    if "error" in result:
        return _invalid_setup(
            result["error"],
            ticker=ticker,
            levels=levels,
            stage="build_failed",
        )

    plan_shape, invalidation_note = _derive_plan_shape_from_levels(
        levels, close, structural_uptrend
    )
    result["setup_state"] = "triggered" if result.get("valid") else "conditional"
    result["plan_shape"] = plan_shape
    result["trigger_price"] = result.get("entry")
    result["invalidation_note"] = invalidation_note

    result["target_basis"] = target_basis
    result["target_source"] = "volatility_projected" if resistance_projected else "structural"
    result["rr_stretch"] = (
        _stretch_rr_from_target(support, stop, stretch_target, cost_pct)
        if stretch_target is not None
        else None
    )

    result["levels_used"] = {
        "nearest_support": levels.get("nearest_support"),
        "swing_low": levels.get("swing_low"),
        "nearest_resistance": levels.get("nearest_resistance"),
        "swing_high": levels.get("swing_high"),
        "range_20d_low": levels.get("range_20d_low"),
        "range_20d_high": levels.get("range_20d_high"),
    }

    gap_pct = ((close - support) / support) * 100 if support > 0 else 0
    if gap_pct > _MARKET_ENTRY_GAP_PCT:
        market = _build_single_setup(ticker, close, stop, target, close, cost_pct=cost_pct)
        if "error" in market:
            _emit_subsetup_rejection(
                ticker=ticker, error=market["error"], stage="market_entry_subsetup"
            )
        else:
            market["gap_from_support_pct"] = round(gap_pct, 1)
            market.pop("close", None)
            market.pop("ticker", None)
            result["market_setup"] = market

    max_entry_gap_pct = get_calibrated_entry_gap() or cfg.max_entry_gap_pct
    if gap_pct > max_entry_gap_pct and close > 0:
        pullback_entry = round(close * (1 - max_entry_gap_pct / 100))
        if pullback_entry > stop:
            pullback = _build_single_setup(
                ticker, pullback_entry, stop, target, close, cost_pct=cost_pct
            )
            if "error" in pullback:
                _emit_subsetup_rejection(
                    ticker=ticker, error=pullback["error"], stage="pullback_subsetup"
                )
            else:
                pullback["gap_from_close_pct"] = round(max_entry_gap_pct, 1)
                pullback["gap_from_support_pct"] = round(gap_pct, 1)

                _SETUP_FIELDS = {
                    "ticker",
                    "entry",
                    "stop",
                    "target",
                    "risk_reward",
                    "risk_reward_gross",
                    "risk_per_share",
                    "shares",
                    "position_vnd",
                    "valid",
                    "close",
                }
                support_setup = {k: v for k, v in result.items() if k in _SETUP_FIELDS}
                result["support_setup"] = support_setup

                result["entry"] = pullback["entry"]
                result["stop"] = pullback["stop"]
                result["target"] = pullback["target"]
                result["risk_reward"] = pullback["risk_reward"]
                result["risk_reward_gross"] = pullback["risk_reward_gross"]
                result["shares"] = pullback["shares"]
                result["position_vnd"] = pullback["position_vnd"]
                result["valid"] = pullback["valid"]
                result["close"] = close
                result["pullback_promoted"] = True
                # SWI-358: pullback promotion changes the active geometry —
                # carry its diagnostic flags so observability tracks what
                # shipped, not what the primary support setup looked like.
                result["degenerate_risk"] = pullback["degenerate_risk"]
                result["extreme_rr"] = pullback["extreme_rr"]

                result["rr_stretch"] = (
                    _stretch_rr_from_target(
                        pullback["entry"], pullback["stop"], stretch_target, cost_pct
                    )
                    if stretch_target is not None
                    else None
                )

    return result


def _enrich_with_setup_and_prose(ticker: str, result: dict, risk_regime: str | None = None) -> None:
    """Mutate a ticker's technicals dict with prose + trade_setup fields.

    Extracted so both single-ticker and batch paths share the exact same
    derivation logic. Works in-place.
    """
    from .prose import _format_technicals_prose

    result["prose"] = _format_technicals_prose(result)

    levels = result.get("levels") or {}
    close = result.get("close", 0)
    if levels and close:
        setup = compute_setup_from_levels(
            levels,
            close,
            ticker,
            structural_uptrend=is_structural_uptrend(result),
            atr=result.get("atr"),
            risk_regime=risk_regime,
        )
        vol_ratio = result.get("volume_vs_avg")
        if vol_ratio is not None:
            setup["volume_vs_avg"] = vol_ratio
            setup["volume_confirmed"] = bool(vol_ratio >= 0.8)
        pattern_data = result.get("pattern") or {}
        if pattern_data.get("pattern"):
            setup["pattern_name"] = pattern_data["pattern"]
            setup["pattern_signal"] = pattern_data.get("signal")
        if setup.get("valid"):
            setup["exit_state"] = {
                "entry_price": int(setup["entry"]),
                "stop_price": int(setup["stop"]),
                "target_price": int(setup["target"]),
                "atr_at_entry": None,
                "trail_mult": None,
                "peak_price": None,
                "strategy": None,
                "adx": None,
                "has_positive_catalyst": False,
                "daily_limit_pct": 0.07,
            }
        result["trade_setup"] = setup
