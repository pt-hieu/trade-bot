"""LLM-driven interpretation text + the fail-closed output builder.

These two helpers were carved out of ``build.py`` so the orchestrator
stays under the 350-line cap. The fail-closed builder lives here because
:func:`_generate_interpretation` and :func:`_build_failclosed_output`
both shape the textual surface of the macro payload (one for the OK
path, one for STALE/DEGRADED/ERROR), keeping presentation concerns in
one module.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from shared.rules.geopolitical import apply_shock_floor

from .classifiers import _is_valid_number

if TYPE_CHECKING:
    from pipeline.types import GeopoliticalShockDict, MacroMetricsOutput

logger = logging.getLogger(__name__)

_FailClosedQuality = Literal["STALE", "DEGRADED", "ERROR"]


def _build_failclosed_output(
    *,
    data_quality: _FailClosedQuality,
    date_str: str,
    geo_shock: GeopoliticalShockDict | None,
    interpretation: str,
    data: dict,
    dxy_signal: str,
    vix_signal: str,
    usd_vnd_signal: str,
    oil_signal: str = "NORMAL",
    error: str | None = None,
) -> MacroMetricsOutput:
    """Build a fail-closed :class:`MacroMetricsOutput` with consistent fields.

    Shared across STALE / DEGRADED / ERROR branches in ``fetch_macro_metrics``
    so the three paths can't drift. Regime is computed via
    :func:`apply_shock_floor` so shock context survives DXY/VIX outages.
    """
    phase_name = geo_shock["phase_name"] if geo_shock else None
    regime = apply_shock_floor(
        "CAUTIOUS", phase_name, phase_stale=bool((geo_shock or {}).get("phase_stale"))
    )
    out: MacroMetricsOutput = {
        "date": date_str,
        "scan_date": date_str,
        "dxy_value": float(data.get("dxy_value") or 0.0),
        "dxy_change_pct": float(data.get("dxy_change_pct") or 0.0),
        "dxy_signal": dxy_signal,
        "vix_value": float(data.get("vix_value") or 0.0),
        "vix_change_pct": float(data.get("vix_change_pct") or 0.0),
        "vix_signal": vix_signal,
        "usd_vnd_rate": float(data.get("usd_vnd_rate") or 0.0),
        "usd_vnd_signal": usd_vnd_signal,
        "usd_vnd_source": data.get("usd_vnd_source") or "unknown",
        "oil_price": data.get("oil_price"),
        "oil_change_pct": data.get("oil_change_pct"),
        "oil_signal": oil_signal,
        "global_risk_regime": regime,
        "interpretation": interpretation.format(regime=regime),
        "geopolitical_shock": geo_shock,
        "data_quality": data_quality,
        "upcoming_events": [],
    }
    if error is not None:
        out["error"] = error
    return out


async def _generate_interpretation(
    data: dict,
    dxy_signal: str,
    vix_signal: str,
    usd_vnd_signal: str,
    regime: str,
    oil_signal: str = "NORMAL",
    usd_vnd_source: str = "sbv",
    usd_vnd_spread: float | None = None,
) -> str:
    """Use LLM to generate human-readable interpretation."""
    from shared.agent_config import load_agent_config

    from ..agent_factory import AgentDeps, create_agent
    from ..model.wrappers import OUTER_FALLBACK_STACK_WALL_S, await_with_hop_unwrap

    oil_price = data.get("oil_price")
    oil_change = data.get("oil_change_pct") or 0.0
    oil_line = (
        f"Oil: {oil_price:.1f} USD/bbl ({oil_change:+.2f}%) → {oil_signal}"
        if oil_price
        else f"Oil: N/A → {oil_signal}"
    )

    oil_impacts = {
        "LOW": "cheap energy is favorable for manufacturing/logistics costs",
        "NORMAL": "stable energy costs",
        "ELEVATED": "inflationary pressure — raises VN logistics, manufacturing, power costs",
        "ELEVATED_SPIKE": "sudden energy cost spike — inflation risk for VN importers",
        "EXTREME": "supply crisis — severe cost inflation, hit transport/manufacturing sectors",
        "EXTREME_SPIKE": "energy supply shock — expect stagflation pressure, defensive posture",
    }
    oil_impact = oil_impacts.get(oil_signal, "monitor energy costs")

    spread_note = f" (market spread: +{usd_vnd_spread:.0f})" if usd_vnd_spread is not None else ""
    source_label = "SBV ref rate" if usd_vnd_source == "sbv" else "market rate (fallback)"

    us_index_specs = [("S&P 500", "sp500"), ("NASDAQ", "nasdaq"), ("Dow", "dow")]
    us_parts = []
    for label, key in us_index_specs:
        close_value = data.get(f"{key}_close")
        if close_value:
            change = data.get(f"{key}_change_pct") or 0
            us_parts.append(f"{label}: {close_value:,.1f} ({change:+.2f}%)")
    us_lines = f"\nUS Overnight: {' | '.join(us_parts)}" if us_parts else ""

    breadth_ratio = data.get("breadth_ratio")
    breadth_line = ""
    if breadth_ratio is not None:
        breadth_advance = data.get("breadth_advance") or 0
        breadth_decline = data.get("breadth_decline") or 0
        breadth_line = f"\nVN Market Breadth: {breadth_advance} advancing / {breadth_decline} declining (ratio: {breadth_ratio:.2f})"

    dxy_val = data["dxy_value"] if _is_valid_number(data.get("dxy_value")) else 0
    dxy_chg = data["dxy_change_pct"] if _is_valid_number(data.get("dxy_change_pct")) else 0
    vix_val = data["vix_value"] if _is_valid_number(data.get("vix_value")) else 0
    vix_chg = data["vix_change_pct"] if _is_valid_number(data.get("vix_change_pct")) else 0

    prompt = f"""Given these macro indicators, write a 2-3 sentence interpretation for Vietnamese stock trading:

DXY: {dxy_val} ({dxy_chg:+.2f}%) → {dxy_signal}
VIX: {vix_val} ({vix_chg:+.2f}%) → {vix_signal}
USD/VND: {data["usd_vnd_rate"]:,.0f} [{source_label}]{spread_note} → {usd_vnd_signal}
{oil_line}{us_lines}{breadth_line}
Global Risk Regime: {regime}

Impact by regime:
- CALM: Normal trading, all strategies valid
- CAUTIOUS: Reduce position sizes, tighten stops
- ELEVATED: Prefer confirmed-trend setups, prioritize higher-R:R entries, size conservatively
- CRISIS: Preserve capital; trim stretched positions; defer new entries

Oil transmission to VN: {oil_impact}
US overnight moves strongly influence VN market open — large US drops typically lead to VN gap-downs.

Focus on what this means for Vietnamese stock trading today."""

    try:
        config = await load_agent_config("macro_interpreter")
        # HOOK-ALLOW: no-tickers-scope (macro_interpreter emits global regime, not ticker-scoped)
        agent = create_agent(config, output_type=str)
        deps = AgentDeps(scan_date=None, agent_key=config.agent_key)
        result = await await_with_hop_unwrap(
            agent.run(prompt, deps=deps),
            timeout=int(OUTER_FALLBACK_STACK_WALL_S),
        )
        return result.output
    except TimeoutError:
        return f"Global risk regime: {regime}. DXY {dxy_signal}, VIX {vix_signal}, USD/VND {usd_vnd_signal}."
    except Exception:
        return f"Global risk regime: {regime}. DXY {dxy_signal}, VIX {vix_signal}, USD/VND {usd_vnd_signal}."
