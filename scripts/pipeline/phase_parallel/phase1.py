"""Phase 1 — independent global agents in parallel."""

from __future__ import annotations

import asyncio

from agents import fetch_flow_with_agent, fetch_macro_metrics
from shared.api.commodities import get_commodity_prices
from shared.errors import report_caught
from shared.neon import get_foreign_flow, get_macro_metrics
from shared.neon.catalyst_summaries import get_active_geopolitical_shock
from shared.neon.market import get_vn_index_trend_3d
from shared.vnstock_client import fetch_market_valuation, fetch_vn_economic_snapshot

from ..phase1_local_regime import apply_local_regime_adjustment, resolve_vn_index_trend
from ..types import Phase1Result, PhaseHealth
from .utils import _run_with_semaphore


async def run_phase1_parallel(
    scan_date,
    get_market_level_fn=None,
    *,
    skip_market_agents: bool = False,
) -> Phase1Result:
    """Phase 1: Run independent agents in parallel.

    Args:
        skip_market_agents: When True, skips market_level, foreign_flow, and
            market_valuation (holiday mode — only global macro data fetched).
    """
    label = "Holiday Global Fetch" if skip_market_agents else "Independent Agents (Parallel)"
    print(f"\n{'=' * 60}", flush=True)
    print(f"PHASE 1: {label}", flush=True)
    print("=" * 60, flush=True)

    if not skip_market_agents:
        existing_macro, existing_flow = await asyncio.gather(
            get_macro_metrics(scan_date),
            get_foreign_flow(scan_date),
        )
    else:
        existing_macro = await get_macro_metrics(scan_date)
        existing_flow = None

    tasks = []
    macro_result = None
    flow_result = None

    if not skip_market_agents:
        if get_market_level_fn is None:
            raise ValueError("get_market_level_fn required when skip_market_agents=False")
        tasks.append(_run_with_semaphore(get_market_level_fn(scan_date), "market_level"))

        assert existing_flow is not None
        if "error" not in existing_flow:
            print("  [foreign_flow] Loading from database...", flush=True)
            existing_flow["data_date"] = str(scan_date)
            existing_flow["is_stale"] = True
            flow_result = ("foreign_flow", existing_flow)
        else:
            print("  [foreign_flow] Fetching via agent...", flush=True)
            tasks.append(_run_with_semaphore(fetch_flow_with_agent(scan_date), "foreign_flow"))

    if "error" not in existing_macro:
        print("  [macro] Loading from database...", flush=True)
        macro_result = ("macro_metrics", existing_macro)
    else:
        print("  [macro] Fetching via agent...", flush=True)
        try:
            geo_shock = await get_active_geopolitical_shock()
        except Exception as shock_err:
            report_caught("phase1.geo_shock_prefetch", shock_err)
            geo_shock = None
        if geo_shock:
            print(
                f"  [Phase0] geo_shock pre-fetched: {geo_shock['phase_name']} "
                f"({geo_shock.get('catalyst_event', '')})",
                flush=True,
            )
        tasks.append(
            _run_with_semaphore(
                fetch_macro_metrics(scan_date, geo_shock=geo_shock),
                "macro_metrics",
            )
        )

    tasks.append(_run_with_semaphore(get_commodity_prices(), "commodity_prices"))
    if not skip_market_agents:
        tasks.append(_run_with_semaphore(fetch_market_valuation(), "market_valuation"))
    tasks.append(_run_with_semaphore(fetch_vn_economic_snapshot(), "vn_economy"))

    vn_index_task = asyncio.create_task(get_vn_index_trend_3d(scan_date))
    if tasks:
        print(f"  Running {len(tasks)} agent(s) in parallel...", flush=True)
        results = await asyncio.gather(*[t for t in tasks])
        results_dict = dict(results)
    else:
        results_dict = {}

    if macro_result:
        results_dict["macro_metrics"] = macro_result[1]
    if flow_result:
        results_dict["foreign_flow"] = flow_result[1]

    vn_index_3d_pct = await resolve_vn_index_trend(vn_index_task, scan_date)
    apply_local_regime_adjustment(results_dict, vn_index_3d_pct)

    processed = {}
    for key, fallback in [
        ("market_level", None),
        ("macro_metrics", None),
        ("foreign_flow", None),
        ("commodity_prices", {}),
        ("market_valuation", {}),
        ("vn_economy", {}),
    ]:
        value = results_dict.get(key)
        if isinstance(value, Exception):
            processed[key] = fallback
            print(f"  [{key}] FAILED", flush=True)
        else:
            processed[key] = value if fallback is None else (value or {})
            print(f"  [{key}] OK", flush=True)

    llm_agent_keys = ["market_level", "macro_metrics", "foreign_flow"]
    failed_names = [k for k in llm_agent_keys if processed.get(k) is None and k in results_dict]
    attempted = [k for k in llm_agent_keys if k in results_dict]
    phase_health = PhaseHealth(
        total_agents=len(attempted),
        failed_agents=len(failed_names),
        failed_names=failed_names,
    )

    return Phase1Result(
        market_level=processed.get("market_level"),
        macro_metrics=processed.get("macro_metrics"),
        foreign_flow=processed.get("foreign_flow"),
        commodity_prices=processed.get("commodity_prices") or {},
        market_valuation=processed.get("market_valuation") or {},
        vn_economy=processed.get("vn_economy") or {},
        health=phase_health,
    )
