"""fetch_macro_metrics orchestrator — coordinates classifiers, fetch, and interpretation."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from .classifiers import (
    MISSING_SIGNAL,
    MISSING_SIGNAL_DEFAULTS,
    _is_valid_number,
    calculate_global_regime,
    classify_dxy,
    classify_oil,
    classify_usd_vnd,
    classify_vix,
)
from .fetch import _fetch_macro_data
from .interpretation import _build_failclosed_output, _generate_interpretation

if TYPE_CHECKING:
    from pipeline.types import GeopoliticalShockDict, MacroMetricsOutput

logger = logging.getLogger(__name__)


async def fetch_macro_metrics(
    scan_date: date | None = None,
    geo_shock: GeopoliticalShockDict | None = None,
) -> MacroMetricsOutput:
    """Fetch and analyze global macro metrics.

    1. Fetch structured data from Lightsail API (DXY, VIX, USD/VND)
    2. Classify signals deterministically
    3. Calculate risk regime
    4. Use LLM for interpretation text only

    ``geo_shock`` is injected from Phase 0 pre-fetch. On flaky-API mornings,
    passing the pre-fetched value prevents the fail-closed branches from
    dropping geopolitical context and allows the regime floor to stay
    elevated during ``immediate_shock`` / ``sustained_pressure`` phases.
    """
    if scan_date is None:
        scan_date = date.today()

    date_str = scan_date.strftime("%Y-%m-%d")

    try:
        data = await _fetch_macro_data()

        dxy_valid = _is_valid_number(data["dxy_value"]) and data["dxy_value"] != 0
        vix_valid = _is_valid_number(data["vix_value"]) and data["vix_value"] != 0
        if not dxy_valid and not vix_valid:
            logger.error(
                "fetch_macro_metrics: DXY=0 AND VIX=0 — macro data completely stale/missing. "
                "Defaulting to CAUTIOUS (fail-closed)."
            )
            for key in ("dxy_value", "dxy_change_pct", "vix_value", "vix_change_pct"):
                data[key] = 0.0
            return _build_failclosed_output(
                data_quality="STALE",
                date_str=date_str,
                geo_shock=geo_shock,
                interpretation="Macro data unavailable (DXY=0, VIX=0). Defaulting to {regime}.",
                data=data,
                dxy_signal=MISSING_SIGNAL_DEFAULTS["dxy"],
                vix_signal=MISSING_SIGNAL_DEFAULTS["vix"],
                usd_vnd_signal=MISSING_SIGNAL_DEFAULTS["usd_vnd"],
            )

        print(
            f"  [Macro] DXY={data['dxy_value']}, VIX={data['vix_value']}, USD/VND={data['usd_vnd_rate']}"
        )

        from shared.neon.market import get_macro_history, has_upcoming_macro_events

        data_quality = "OK"
        macro_history = await get_macro_history(30)
        if macro_history:
            prev = macro_history[0]
            if (
                prev.get("dxy_value") == data["dxy_value"]
                and prev.get("vix_value") == data["vix_value"]
            ):
                data_quality = "STALE"
                print(
                    f"  [Macro] ⚠️  WARNING: DXY={data['dxy_value']} and VIX={data['vix_value']} "
                    f"identical to {prev['date']} — data may be stale (yfinance cache issue?)"
                )
            curr_source = data.get("usd_vnd_source")
            prev_source = prev.get("usd_vnd_source")
            if prev_source and curr_source and prev_source != curr_source:
                logger.warning(
                    "USD/VND source switched: %s → %s (rate: %.0f → %.0f)",
                    prev_source,
                    curr_source,
                    prev.get("usd_vnd_rate") or 0,
                    data["usd_vnd_rate"],
                )

        history_rates = [
            h["usd_vnd_rate"]
            for h in macro_history
            if h["usd_vnd_rate"] is not None and h.get("usd_vnd_source") != "sbv"
        ]
        if len(history_rates) >= 5:
            sorted_rates = sorted(history_rates)
            rolling_median = sorted_rates[len(sorted_rates) // 2]
        else:
            rolling_median = None

        dxy_signal = classify_dxy(data["dxy_value"], data["dxy_change_pct"])
        vix_signal = classify_vix(data["vix_value"])
        usd_vnd_signal = classify_usd_vnd(
            data["usd_vnd_rate"],
            data.get("usd_vnd_source") or "sbv",
            rolling_median=rolling_median,
        )
        oil_price = data.get("oil_price")
        oil_change = data.get("oil_change_pct") or 0.0
        oil_source = data.get("oil_source") or "unknown"
        if not _is_valid_number(oil_price) or oil_price is None or oil_price <= 0:
            logger.warning(
                "fetch_macro_metrics: oil_price=%s (source=%s) — "
                "oil_signal defaults to NORMAL. Regime may undercount risk.",
                oil_price,
                oil_source,
            )
            oil_signal = "NORMAL"
            oil_price = 0.0
        else:
            oil_signal = classify_oil(float(oil_price), oil_change)

        critical_signals = {"dxy": dxy_signal, "vix": vix_signal, "usd_vnd": usd_vnd_signal}
        missing_signals = [name for name, sig in critical_signals.items() if sig == MISSING_SIGNAL]
        if missing_signals:
            logger.error(
                "fetch_macro_metrics: MISSING signals for %s — NaN/invalid data detected. "
                "Fail-closed to CAUTIOUS (rule 16: missing data = most conservative).",
                ", ".join(missing_signals),
            )
            for key in ("dxy_value", "dxy_change_pct", "vix_value", "vix_change_pct"):
                if not _is_valid_number(data.get(key)):
                    data[key] = 0.0
            data.setdefault("oil_price", oil_price)
            data.setdefault("oil_change_pct", oil_change)
            return _build_failclosed_output(
                data_quality="DEGRADED",
                date_str=date_str,
                geo_shock=geo_shock,
                interpretation=(
                    f"Macro data degraded: {', '.join(missing_signals)} returned NaN/invalid. "
                    "Defaulting to {regime} (missing data = caution)."
                ),
                data=data,
                dxy_signal=dxy_signal
                if dxy_signal != MISSING_SIGNAL
                else MISSING_SIGNAL_DEFAULTS["dxy"],
                vix_signal=vix_signal
                if vix_signal != MISSING_SIGNAL
                else MISSING_SIGNAL_DEFAULTS["vix"],
                usd_vnd_signal=usd_vnd_signal
                if usd_vnd_signal != MISSING_SIGNAL
                else MISSING_SIGNAL_DEFAULTS["usd_vnd"],
                oil_signal=oil_signal,
            )

        print(
            f"  [Macro] Signals: DXY={dxy_signal}, VIX={vix_signal}, USD/VND={usd_vnd_signal}, Oil={oil_signal}"
        )

        if geo_shock:
            print(
                f"  [Macro] Geopolitical shock active: {geo_shock['catalyst_event']} "
                f"-> phase: {geo_shock['phase_name']}"
            )

        has_events = await has_upcoming_macro_events(scan_date)
        if has_events:
            print("  [Macro] Upcoming macro events detected → CAUTIOUS floor applied")
        regime = calculate_global_regime(
            dxy_signal,
            vix_signal,
            usd_vnd_signal,
            has_events,
            oil_signal,
            active_geopolitical_phase=geo_shock["phase_name"] if geo_shock else None,
            phase_stale=bool(geo_shock.get("phase_stale")) if geo_shock else False,
        )
        print(f"  [Macro] Regime: {regime}")

        interpretation = await _generate_interpretation(
            data,
            dxy_signal,
            vix_signal,
            usd_vnd_signal,
            regime,
            oil_signal,
            data.get("usd_vnd_source") or "sbv",
            data.get("usd_vnd_spread"),
        )

        output: MacroMetricsOutput = {
            "date": date_str,
            "dxy_value": data["dxy_value"],
            "dxy_change_pct": data["dxy_change_pct"],
            "dxy_signal": dxy_signal,
            "vix_value": data["vix_value"],
            "vix_change_pct": data["vix_change_pct"],
            "vix_signal": vix_signal,
            "usd_vnd_rate": data["usd_vnd_rate"],
            "usd_vnd_signal": usd_vnd_signal,
            "usd_vnd_source": data.get("usd_vnd_source") or "sbv",
            "usd_vnd_spread": data.get("usd_vnd_spread"),
            "global_risk_regime": regime,
            "interpretation": interpretation,
            "upcoming_events": [],
            "copper_price": data.get("copper_price"),
            "copper_change_pct": data.get("copper_change_pct"),
            "oil_price": data.get("oil_price"),
            "oil_change_pct": data.get("oil_change_pct"),
            "oil_signal": oil_signal,
            "us_10y_yield": data.get("us_10y_yield"),
            "us_10y_change_pct": data.get("us_10y_change_pct"),
            "shanghai_close": data.get("shanghai_close"),
            "shanghai_change_pct": data.get("shanghai_change_pct"),
            "geopolitical_shock": geo_shock,
            "sp500_close": data.get("sp500_close"),
            "sp500_change_pct": data.get("sp500_change_pct"),
            "nasdaq_close": data.get("nasdaq_close"),
            "nasdaq_change_pct": data.get("nasdaq_change_pct"),
            "dow_close": data.get("dow_close"),
            "dow_change_pct": data.get("dow_change_pct"),
            "breadth_advance": data.get("breadth_advance"),
            "breadth_decline": data.get("breadth_decline"),
            "breadth_ratio": data.get("breadth_ratio"),
            "data_quality": data_quality,
        }

        return output

    except Exception as e:
        logger.error("fetch_macro_metrics failed: %s", e, exc_info=True)
        return _build_failclosed_output(
            data_quality="ERROR",
            date_str=date_str,
            geo_shock=geo_shock,
            interpretation=(
                f"Unable to fetch macro data: {e}. Defaulting to {{regime}} (unknown = caution)."
            ),
            data={"usd_vnd_source": "unknown"},
            dxy_signal=MISSING_SIGNAL_DEFAULTS["dxy"],
            vix_signal=MISSING_SIGNAL_DEFAULTS["vix"],
            usd_vnd_signal=MISSING_SIGNAL_DEFAULTS["usd_vnd"],
            error=f"Macro fetch failed: {e}",
        )
