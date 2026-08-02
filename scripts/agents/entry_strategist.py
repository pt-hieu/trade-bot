#!/usr/bin/env python3
"""
Entry Strategist Agent — owns strategic sections of morning brief.

Generates: TODAY'S THEME, STANCE, MINDSET, MARKET MOOD, NEWS THAT MATTERS,
SECTOR FOCUS, KEY RISK sections.

Separated from position_strategist to focus entirely on entry opportunities
and market context, without position management concerns diluting context.
"""

import re
from datetime import date

from pydantic_ai import Agent

from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.rules.exit_strategy import is_trailing_exit
from shared.rules.recommendation_gate import RecommendationGateDecision

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_DISABLE_FALLBACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout


async def create_entry_strategist_agent() -> tuple[Agent[AgentDeps, str], AgentConfig]:
    """Create entry strategist agent from DB config."""
    config = await load_agent_config("entry_strategist")
    agent = create_agent(config)
    return agent, config


async def generate_entry_strategy(
    phase1_results: dict,
    phase2_results: dict,
    trading_mode: dict | None,
    deterministic_sections: str,
    pre_computed_picks: list[dict] | None = None,
    scan_date: date | None = None,
    catalyst_context: str = "",
    catalyst_boost_context: str = "",
    articles_context: str = "",
    macro_interpretation: str = "",
    commodity_context: str = "",
    vn_economy_context: str = "",
    regime_context: str = "",
    recent_trades_context: str = "",
    learnings_context: str = "",
    memory_context: str = "",
    holdings_verb_summary: str = "",
    gate_decision: RecommendationGateDecision | None = None,
) -> str:
    """Generate strategic entry sections for the morning brief.

    Args:
        phase1_results: Phase 1 results (market_level, macro, foreign_flow)
        phase2_results: Phase 2 results (sector_rotation, sector_results)
        trading_mode: Trading mode dict
        deterministic_sections: Pre-computed sections (embed verbatim)
        pre_computed_picks: Validated top pick candidates
        scan_date: Date for analysis
        gate_decision: Composed recommendation gate — supplies
            `effective_rr_floor` and `shock_rr_floor` so the R:R numbers the
            strategist cites match the operational floor, not a stale YAML
            literal (MON-2026-04-21, Fix 3).

    Returns:
        Formatted entry strategy sections string
    """
    if scan_date is None:
        scan_date = date.today()

    from pipeline.enrichment_position_data import extract_held_tickers

    pick_tickers = extract_held_tickers(pre_computed_picks)
    agent, config = await create_entry_strategist_agent()

    parts = []

    # Deterministic sections — CONTEXT ONLY for the LLM. These are already
    # pre-computed; the LLM reads them to inform its narrative but must NOT
    # emit them into its output. They are concatenated onto the final
    # entry_strategy below by the Python renderer (MON-2026-04-16-005).
    parts.append(
        "## PRE-COMPUTED SECTIONS (CONTEXT ONLY — do NOT echo into output; "
        "the renderer will concatenate them after your sections)\n" + deterministic_sections
    )

    # Today's authoritative holding verbs — MINDSET must reflect these,
    # not stale historical framing (MON-2026-04-16-002, Finding 3).
    if holdings_verb_summary:
        parts.append(
            "## TODAY'S HOLDING ACTIONS (authoritative — MINDSET must reflect these verbs)\n"
            + holdings_verb_summary
            + "\nDo NOT describe any holding as HOLD in MINDSET unless its verb above is HOLD. "
            "Do NOT reference historical position dates from earlier briefs."
        )

    # Market regime — dual-label injection (Phase 2 §2.8). Output `regime`
    # in the strategist's response MUST equal the GLOBAL RISK REGIME label.
    from pipeline.context_blocks_macro import format_dual_regime_labels

    ml = phase1_results.get("market_level") or {}
    macro = phase1_results.get("macro_metrics") or {}
    parts.append(
        "## MARKET REGIME\n"
        + format_dual_regime_labels(
            global_risk_regime=macro.get("global_risk_regime"),
            technical_regime=ml.get("regime"),
            technical_confidence=ml.get("regime_confidence", 0),
            style="block",
        )
    )

    # Foreign flow — label as T-1 when data is from previous session
    flow = phase1_results.get("foreign_flow")
    if flow and "error" not in flow:
        net = flow.get("net_value_billion", 0)
        data_date = flow.get("data_date")
        is_stale = flow.get("is_stale", False)
        staleness_label = ""
        if is_stale and data_date:
            staleness_label = f" (T-1: {data_date} data, INFORMATIONAL — not today's session)"
        elif is_stale:
            staleness_label = " (T-1, INFORMATIONAL — not today's session)"
        parts.append(
            f"## FOREIGN FLOW{staleness_label}\n"
            f"Net: {net:+.1f}B VND | Signal: {flow.get('signal', 'N/A')} | "
            f"Pattern: {flow.get('pattern', 'N/A')}"
        )

    # Macro
    macro = phase1_results.get("macro_metrics")
    if macro and "error" not in macro:
        parts.append(
            f"## GLOBAL MACRO\n"
            f"Risk: {macro.get('global_risk_regime', 'N/A')} | "
            f"DXY: {macro.get('dxy_value', 'N/A')} | "
            f"VIX: {macro.get('vix_value', 'N/A')} | "
            f"USD/VND: {macro.get('usd_vnd_rate', 'N/A')}"
        )

    if macro_interpretation:
        parts.append(f"## MACRO INTERPRETATION\n{macro_interpretation}")

    if commodity_context:
        parts.append(commodity_context)

    if vn_economy_context:
        parts.append(vn_economy_context)

    if regime_context:
        parts.append(f"## REGIME CONTEXT\n{regime_context}")

    # Sector rotation
    rotation = phase2_results.get("sector_rotation")
    if rotation:
        hot = rotation.get("hot_sectors", [])
        cold = rotation.get("cold_sectors", [])
        parts.append(
            f"## SECTOR ROTATION\nHot: {', '.join(hot) or 'None'} | "
            f"Cold: {', '.join(cold) or 'None'}"
        )

    # Trading mode
    if trading_mode:
        parts.append(
            f"## TRADING MODE\n"
            f"{trading_mode.get('mode', 'NORMAL')}: {trading_mode.get('reason', '')}"
        )

    # Inject entry constraint context to guide KEY RISK framing
    max_entries_match = re.search(r"Max entries: (\d+)", deterministic_sections)
    if max_entries_match:
        max_entries_val = int(max_entries_match.group(1))
        if max_entries_val == 0:
            parts.append(
                "## CONSTRAINT: NO NEW ENTRIES TODAY\n"
                "Max entries = 0 today (no deployable cash). KEY RISK must focus on POSITION MANAGEMENT risks\n"
                "(stop discipline, trim timing, holding concentration risks).\n"
                "Frame today's correct action as position stewardship — keep language on stop discipline,\n"
                "holding quality, and concentration; skip commentary on missed entries or execution paralysis."
            )
        elif max_entries_val == 1:
            parts.append(
                "## CONSTRAINT: SELECTIVE ENTRY MODE\n"
                "Max entries = 1 today. You may recommend exactly ONE entry — but ONLY if it meets elevated R:R criteria.\n"
                "STANCE should be SELECTIVE: actively identify the single best setup available.\n"
                "KEY RISK must balance position management with the cost of inaction.\n"
                "A low win rate means higher selectivity, not zero activity. One well-structured trade breaks a streak."
            )

    # R:R floor discipline — injected from the composed gate so the numbers
    # the LLM cites match the operational floor. The YAML system prompt has no
    # literal R:R values any more; it routes every R:R mention through these
    # variables (Fix 3). When `gate_decision` is unavailable (intraday catalyst
    # revision path, which loads from DB instead of composing fresh), fall back
    # to the floor already embedded in `deterministic_sections` so the block is
    # never omitted.
    rr_floor_value: float | None = None
    shock_floor_value: float | None = None
    if gate_decision is not None:
        rr_floor_value = gate_decision.effective_rr_floor
        shock_floor_value = gate_decision.shock_rr_floor
    else:
        floor_match = re.search(r"Min R:R[^0-9]*(\d+(?:\.\d+)?)", deterministic_sections)
        if floor_match:
            rr_floor_value = float(floor_match.group(1))
            shock_floor_value = rr_floor_value
    if rr_floor_value is not None and shock_floor_value is not None:
        parts.append(
            "## R:R FLOOR (today's operational numbers — use these for every R:R reference)\n"
            f"- rr_floor = {rr_floor_value:.1f} -- cite this in MARKET MOOD, KEY RISK, STANCE,\n"
            f"  and any general 'require R:R >= X' prose.\n"
            f"- shock_rr_floor = {shock_floor_value:.1f} -- cite this ONLY inside the\n"
            "  GEOPOLITICAL SHOCK PROTOCOL clause for non-beneficiary entries during an\n"
            "  active immediate-shock phase. Beneficiary entries use rr_floor.\n"
            "All R:R literals in your output MUST equal one of these two numbers — no\n"
            "rounding, no substitution, no legacy values."
        )

    # Pre-computed picks summary
    if pre_computed_picks:
        pick_lines = []
        for p in pre_computed_picks:
            belief_tag = ""
            if p.get("belief_direction"):
                belief_tag = (
                    f" [{p['belief_direction']} conviction={p.get('belief_conviction', 0):.0%}]"
                )
            rr_val = p.get("risk_reward")
            if is_trailing_exit(p):
                line = f"  {p['ticker']} ({p['sector']}): R:R trailing (ATR_TRAIL){belief_tag}"
            else:
                line = f"  {p['ticker']} ({p['sector']}): R:R {(rr_val or 0):.1f}{belief_tag}"
            pick_lines.append(line)
        parts.append("## TOP PICK CANDIDATES\n" + "\n".join(pick_lines))

    if catalyst_context:
        from pipeline.context_blocks import CATALYST_HEADER

        parts.append(f"{CATALYST_HEADER}\n{catalyst_context}")

    if catalyst_boost_context:
        parts.append(catalyst_boost_context)

    if articles_context:
        parts.append(articles_context)

    # Sector belief consensus — high-conviction directional agreements
    sector_beliefs = phase2_results.get("sector_beliefs") or []
    high_conviction_beliefs = [b for b in sector_beliefs if float(b.get("conviction") or 0) >= 0.6]
    if high_conviction_beliefs:
        from shared.formatting import format_belief_lines

        belief_lines = format_belief_lines(high_conviction_beliefs[:10])
        parts.append("## BELIEF CONSENSUS (high conviction)\n" + "\n".join(belief_lines))

    # Inject pre-fetched data (formerly tool calls)
    if recent_trades_context:
        parts.append(recent_trades_context)
    if learnings_context:
        parts.append(learnings_context)
    if memory_context:
        parts.append(memory_context)

    context = "\n\n".join(parts)

    prompt = (
        f"Generate strategic sections for {scan_date.strftime('%Y-%m-%d')} morning brief.\n\n"
        f"{context}\n\n"
        "All data for MINDSET, MARKET MOOD, KEY RISK, NEWS THAT MATTERS, and calibration is pre-loaded above.\n"
        "Synthesize directly from CATALYST PREVIEW and ARTICLES blocks for NEWS THAT MATTERS.\n\n"
        "Output ONLY these seven narrative sections in order:\n"
        "TODAY'S THEME, STANCE, MINDSET, MARKET MOOD,\n"
        "NEWS THAT MATTERS, SECTOR FOCUS, KEY RISK\n"
        "Do NOT emit GOAL PROGRESS, CAPITAL STATUS, GLOBAL CONTEXT, ENTRY CRITERIA TODAY — the renderer concatenates them after your output.\n\n"
        "PLAIN ASCII only, no markdown, no emojis."
    )

    # Re-raise so phase_strategy's exception filter can route to the
    # deterministic fallback. phase_catalyst_revision wraps this in its own
    # try/except, so re-raising is safe for that caller too.
    deps = AgentDeps(
        scan_date=scan_date,
        agent_key=config.agent_key,
        tickers_in_scope=pick_tickers,
    )
    result = await run_agent_with_total_timeout(
        agent,
        prompt,
        agent_name="entry_strategist",
        deps=deps,
        total_timeout_s=float(OUTER_DISABLE_FALLBACK_WALL_S),
        usage_limits=build_usage_limits(config),
    )
    llm_output = result.output or ""

    # Append deterministic sections after the LLM narrative. Order matters
    # less than presence — the brief parser and web components look up
    # sections by header name, not by source order. Telegram formatter uses
    # _MSG1_SECTIONS / _MSG2_SECTIONS allow-lists.
    return llm_output.rstrip() + "\n\n" + deterministic_sections.rstrip() + "\n"
