"""Intraday catalyst strategy revision.

When a catalyst spike is detected during active hours, this module:
1. Loads the morning scan's persisted Phase 1+2 data from DB
2. Rebuilds deterministic sections
3. Re-runs ONLY the entry strategist with enhanced catalyst context
4. Cancels morning BUY alerts (source-filtered) and re-registers from revised picks
5. Appends revised directive to DB (doesn't replace morning directive)
6. Sends Telegram revision summary

Architecture: reuses morning scan's persisted data — no full pipeline re-run.
Budget: ~70-100s total (well within 600s).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from agents.alert_registrar.deterministic import register_picks_as_alerts
from agents.entry_strategist import generate_entry_strategy
from agents.strategy_constraints import compute_pipeline_constraints
from agents.strategy_sections import build_deterministic_sections
from shared.neon.alert_lifecycle import cancel_alerts_by_source
from shared.neon.catalyst_summaries import get_filtered_catalyst_summary
from shared.neon.directives import get_strategy_directive, save_strategy_directive
from shared.neon.flow import get_foreign_flow
from shared.neon.insert_records import get_morning_recommendations
from shared.neon.market import get_macro_metrics, get_market_regime, get_sector_rotation
from shared.neon.portfolio import get_portfolio_holdings
from shared.neon.watchlist import load_all_watchlist_tickers
from shared.rules.catalyst_override import format_catalyst_boost_context
from shared.telegram import send_telegram

from .helpers import compose_gate_from_state
from .phase_catalyst_revision_observability import emit_revision_lexical_fidelity
from .phase_catalyst_revision_picks import generate_revision_picks
from .types import PhaseIntermediates

logger = logging.getLogger(__name__)

# Sources that catalyst revision is allowed to cancel
_CANCELLABLE_SOURCES = ["morning_brief", "catalyst_revision"]


def _build_revision_catalyst_context(
    catalyst_summary: str,
    trigger_description: str,
    changed_catalysts: list[dict],
) -> str:
    """Build enhanced catalyst context with BREAKING UPDATE header."""
    lines = [
        "## ⚡ BREAKING CATALYST UPDATE",
        f"Trigger: {trigger_description}",
        "",
        "CHANGED CATALYSTS SINCE MORNING SCAN:",
    ]
    for catalyst in changed_catalysts[:10]:
        affected = catalyst.get("affected_tickers", [])
        affected_str = ", ".join(affected[:10])
        if len(affected) > 10:
            affected_str += f" +{len(affected) - 10} more"
        lines.append(
            f"- [{catalyst['impact']}] {catalyst['event']} (confidence: {catalyst['confidence']})"
        )
        if affected_str:
            lines.append(f"  Affects: {affected_str}")

    if catalyst_summary:
        lines.append("")
        lines.append("ALL ACTIVE CATALYSTS:")
        lines.append(catalyst_summary)

    return "\n".join(lines)


async def run_strategy_revision(
    scan_date: date,
    trigger_description: str,
    changed_catalysts: list[dict],
    articles_context: str = "",
) -> dict:
    """Revise today's strategy based on breaking catalyst news.

    Reuses morning scan's persisted Phase 1+2 data. Re-runs only entry strategist.
    Fail-closed: returns {"revised": False} if morning data unavailable.

    Returns:
        {"revised": bool, "reason": str, "cancelled": int, "registered": int}
    """
    print(f"\n{'=' * 60}", flush=True)
    print(f"CATALYST STRATEGY REVISION — {scan_date}", flush=True)
    print(f"Trigger: {trigger_description}", flush=True)
    print(f"{'=' * 60}", flush=True)

    # Serial under held lock_conn (SWI-261). Per-getter wall reserves headroom
    # for the downstream entry-strategist LLM call.
    _GETTER_WALL_S = 8.0
    market_regime_data = await asyncio.wait_for(
        get_market_regime(scan_date), timeout=_GETTER_WALL_S
    )
    macro_data = await asyncio.wait_for(get_macro_metrics(scan_date), timeout=_GETTER_WALL_S)
    sector_rotation_data = await asyncio.wait_for(
        get_sector_rotation(scan_date), timeout=_GETTER_WALL_S
    )
    directive_data = await asyncio.wait_for(
        get_strategy_directive(scan_date), timeout=_GETTER_WALL_S
    )
    morning_recs_raw = await asyncio.wait_for(
        get_morning_recommendations(scan_date), timeout=_GETTER_WALL_S
    )
    foreign_flow_data = await asyncio.wait_for(get_foreign_flow(scan_date), timeout=_GETTER_WALL_S)
    catalyst_summary_text = await asyncio.wait_for(
        get_filtered_catalyst_summary(), timeout=_GETTER_WALL_S
    )

    market_regime: dict = market_regime_data if isinstance(market_regime_data, dict) else {}
    macro: dict = macro_data if isinstance(macro_data, dict) else {}
    rotation: dict = sector_rotation_data if isinstance(sector_rotation_data, dict) else {}
    directive: dict | None = directive_data if isinstance(directive_data, dict) else None
    morning_recs: list[dict] = morning_recs_raw if isinstance(morning_recs_raw, list) else []
    flow: dict = foreign_flow_data if isinstance(foreign_flow_data, dict) else {}
    catalyst_summary: str = catalyst_summary_text if isinstance(catalyst_summary_text, str) else ""

    # Fail-closed if morning scan data is unavailable — nothing to revise.
    if "error" in market_regime:
        reason = "No market regime data for today — morning scan may not have run"
        logger.warning("Strategy revision aborted: %s", reason)
        return {"revised": False, "reason": reason, "cancelled": 0, "registered": 0}

    if not directive:
        reason = "No strategy directive found — morning scan incomplete"
        logger.warning("Strategy revision aborted: %s", reason)
        return {"revised": False, "reason": reason, "cancelled": 0, "registered": 0}

    phase1_results: dict = {
        "market_level": market_regime,
        "macro_metrics": macro if "error" not in macro else None,
        "foreign_flow": flow if "error" not in flow else None,
    }

    phase2_results: dict = {
        "sector_rotation": rotation if "error" not in rotation else None,
        "sector_results": [],
        "sector_signals": [],
        "position_alerts": {"alerts": []},
    }

    # Kick off catalyst boost fetch early so it overlaps with the
    # constraints + deterministic-sections pipeline below. Revision runs
    # without Phase 0 state so the same helper as the main pipeline is
    # used; we only await right before the pick generator needs it.
    from shared.neon.catalyst_summaries import compute_catalyst_boost_bundle
    from shared.rules.catalyst_override import (
        CatalystBoost,
        CatalystInput,
    )

    catalyst_boost_task = asyncio.ensure_future(compute_catalyst_boost_bundle())

    pipeline_constraints, goals, cash_dict = await compute_pipeline_constraints(
        scan_date=scan_date,
        entries_allowed=True,  # Revision assumes entries allowed (morning gate passed)
        entries_blocked_reason=None,
    )

    deterministic_sections = await build_deterministic_sections(
        goals=goals or [],
        cash=cash_dict or {},
        constraints=pipeline_constraints,
        phase1=phase1_results,
    )

    # L1 (SWI-NN, 2026-04-27): retire the inline composer divergence.
    # Revision now calls the same `compose_gate_from_state` helper morning
    # uses so Rule 5a can fire when a per-ticker positive catalyst lands on
    # a held/watched ticker mid-day. Universe is loaded BEFORE the composer
    # call so `candidate_universe` is in scope. `sector_beliefs=None` is
    # explicit: revision's DB fetch deliberately omits today's beliefs, so
    # bullish_count=0 falls out of the helper's computation rather than a
    # hardcoded literal — Rule 5a still requires ≥2 bullish beliefs to
    # fire, so this stays fail-closed at the relief gate while letting the
    # per-ticker positive catalyst propagate into `inputs_digest` for
    # downstream consumers.
    revision_risk_regime: str = str(macro.get("global_risk_regime") or "CAUTIOUS")
    revision_market_regime: str = str(market_regime.get("market_regime") or "NEUTRAL")
    typed_catalysts: list[CatalystInput] = []
    catalyst_boost: dict[str, CatalystBoost]
    try:
        typed_catalysts, computed_boost = await catalyst_boost_task
        catalyst_boost = computed_boost or {}
    except Exception as exc:
        logger.warning("Catalyst boost computation failed during revision: %s", exc, exc_info=True)
        catalyst_boost = {}

    holdings_rows = await get_portfolio_holdings()
    watchlist_set = await load_all_watchlist_tickers()
    holdings_tickers: set[str] = {
        (row.get("ticker") or "").upper() for row in (holdings_rows or []) if row.get("ticker")
    }
    watchlist_tickers: set[str] = set(watchlist_set or [])
    candidate_universe = sorted(holdings_tickers | watchlist_tickers)

    revision_intermediates = PhaseIntermediates(
        market_regime=revision_market_regime,
        global_risk_regime=revision_risk_regime,
        entries_allowed=True,
        entries_blocked_reason=None,
        early_mode="NORMAL",
    )

    rec_gate = await compose_gate_from_state(
        intermediates=revision_intermediates,
        macro_metrics=macro if "error" not in macro else None,
        pipeline_constraints=dict(pipeline_constraints),
        trading_mode="NORMAL",
        scan_date=scan_date,
        strategy_director_failed=False,
        active_catalysts=typed_catalysts,
        sector_beliefs=None,
        candidate_universe=candidate_universe,
    )

    catalyst_boost_context = format_catalyst_boost_context(catalyst_boost)

    pre_computed_picks: list[dict] = await generate_revision_picks(
        scan_date=scan_date,
        morning_recs=morning_recs,
        changed_catalysts=changed_catalysts,
        rec_gate=rec_gate,
        catalyst_boost=catalyst_boost,
        risk_regime=revision_risk_regime,
        active_catalysts=typed_catalysts,
        # Pass the active geopolitical shock so the per-candidate gate can
        # apply stacked-shock relief on shock-affected tickers without
        # leaking the floor cap across the fleet.
        geopolitical_shock=(macro.get("geopolitical_shock") if "error" not in macro else None),
        # Inject already-loaded universe sets so generate_revision_picks
        # skips the duplicate get_portfolio_holdings + watchlist round-trip.
        holdings_tickers=holdings_tickers,
        watchlist_tickers=watchlist_tickers,
    )
    morning_pick_count = sum(
        1 for pick in pre_computed_picks if pick.get("source") != "catalyst_revision"
    )
    catalyst_pick_count = sum(
        1 for pick in pre_computed_picks if pick.get("source") == "catalyst_revision"
    )
    print(
        f"  Revision picks: {morning_pick_count} morning + {catalyst_pick_count} catalyst "
        f"= {len(pre_computed_picks)} total",
        flush=True,
    )

    revised_catalyst_context = _build_revision_catalyst_context(
        catalyst_summary, trigger_description, changed_catalysts
    )

    print("\n  Re-running entry strategist with updated catalyst context...", flush=True)
    try:
        revised_strategy = await generate_entry_strategy(
            phase1_results=phase1_results,
            phase2_results=phase2_results,
            trading_mode=None,
            deterministic_sections=deterministic_sections,
            pre_computed_picks=pre_computed_picks,
            scan_date=scan_date,
            catalyst_context=revised_catalyst_context,
            catalyst_boost_context=catalyst_boost_context,
            articles_context=articles_context,
        )
        print(f"  Revised strategy: {len(revised_strategy)} chars", flush=True)
    except Exception as exc:
        logger.error("Entry strategist failed during revision: %s", exc)
        return {"revised": False, "reason": f"LLM failed: {exc}", "cancelled": 0, "registered": 0}

    cancelled = await cancel_alerts_by_source(scan_date, _CANCELLABLE_SOURCES)
    print(f"  Cancelled {cancelled} existing alerts (sources: {_CANCELLABLE_SOURCES})", flush=True)

    registered = await register_picks_as_alerts(
        pre_computed_picks=pre_computed_picks,
        source="catalyst_revision",
        scan_date=scan_date,
        risk_regime=revision_risk_regime,  # type: ignore[arg-type]
    )
    print(f"  Re-registered {registered} alerts (source=catalyst_revision)", flush=True)

    # Append revised directive to morning's directive rather than replace.
    morning_directive = directive.get("directive") or ""
    morning_constraints = directive.get("constraints") or {}
    revised_directive = (
        f"{morning_directive}\n\n"
        f"--- CATALYST REVISION ({trigger_description}) ---\n"
        f"{revised_strategy}"
    )
    await save_strategy_directive(scan_date, revised_directive, morning_constraints)

    emit_revision_lexical_fidelity(
        scan_date=scan_date,
        changed_catalysts=changed_catalysts,
        revised_strategy=revised_strategy,
    )

    _send_revision_telegram(trigger_description, cancelled, registered, changed_catalysts)

    return {
        "revised": True,
        "reason": trigger_description,
        "cancelled": cancelled,
        "registered": registered,
    }


def _send_revision_telegram(
    trigger: str,
    cancelled: int,
    registered: int,
    changed_catalysts: list[dict],
) -> None:
    """Send Telegram summary of catalyst revision."""
    catalyst_lines = []
    for catalyst in changed_catalysts[:5]:
        catalyst_lines.append(f"  • [{catalyst['impact']}] {catalyst['event']}")

    catalysts_block = "\n".join(catalyst_lines) + "\n\n" if catalyst_lines else ""
    message = (
        f"⚡ CATALYST STRATEGY REVISION\n\n"
        f"Trigger: {trigger}\n\n"
        f"{catalysts_block}"
        f"Alerts: {cancelled} cancelled → {registered} re-registered\n"
        f"Source: catalyst_revision"
    )
    try:
        send_telegram(message)
    except Exception as exc:
        logger.warning("Failed to send revision Telegram: %s", exc)
