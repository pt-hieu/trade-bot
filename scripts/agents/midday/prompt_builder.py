"""Midday prompt builder + agent factory."""

from __future__ import annotations

from pydantic_ai import Agent

from shared.agent_config import AgentConfig, load_agent_config
from shared.rules.exit_strategy import exit_state_from_rec, resolve_exit_strategy
from shared.text_utils import split_first_sentence

from ..agent_factory import AgentDeps, create_agent
from .models import MiddayQualitative

_MIDDAY_SECTIONS = {"STANCE", "CAPITAL STATUS", "KEY RISK", "POSITION GUIDANCE", "ENTRY CRITERIA"}


async def create_midday_agent() -> tuple[Agent[AgentDeps, MiddayQualitative], AgentConfig]:
    """Create a midday check agent with tools."""
    config = await load_agent_config("midday")
    # HOOK-ALLOW: no-tickers-scope (midday operates on full portfolio scope)
    agent = create_agent(config, output_type=MiddayQualitative)
    return agent, config


def _truncate_directive(raw: str) -> str:
    """Keep only midday-relevant sections from strategy directive."""
    if not raw:
        return ""
    lines = raw.split("\n")
    result: list[str] = []
    include = False
    for line in lines:
        stripped = line.strip()
        if stripped and stripped.isupper() and len(stripped) > 3:
            include = any(stripped.startswith(s) for s in _MIDDAY_SECTIONS)
        if include:
            result.append(line)
    return "\n".join(result) if result else ""


def _build_prompt(
    morning_recommendations: list[dict],
    precomputed: dict | None = None,
    trading_mode: str = "NORMAL",
    portfolio_context: str = "",
    recent_trades_context: str = "",
    learnings_context: str = "",
    executed_trades_context: str = "",
    midday_prices_context: str = "",
) -> str:
    """Build the midday check prompt from morning recs + precomputed data."""
    recs_text = ""
    for r in morning_recommendations:
        entry = r.get("entry_price")
        stop = r.get("stop_price")
        exit_line = resolve_exit_strategy(r.get("strategy")).exit_description(
            exit_state_from_rec(r)
        )
        recs_text += f"- {r['ticker']}: {r['action']}"
        if entry:
            recs_text += f" Entry: {entry:,.0f}"
        if stop:
            recs_text += f" Stop: {stop:,.0f}"
        if exit_line:
            recs_text += f" {exit_line}"

        snippet = split_first_sentence(r.get("rationale") or "", max_len=50)
        recs_text += f" ({snippet})\n"

    if not recs_text:
        recs_text = "No morning recommendations available"

    pre = precomputed or {}

    entries_text = ""
    for e in pre.get("entries_hit", []):
        entries_text += (
            f"- {e['ticker']}: Price reached entry level {e['recommended_entry']:,.0f} "
            f"(low {e['actual_low']:,.0f}, now {e['current_price']:,.0f}) — NOT bought yet, user decides\n"
        )

    movers_text = ""
    for m in pre.get("big_movers", []):
        sign = "+" if m["change_pct"] >= 0 else ""
        movers_text += (
            f"- {m['ticker']}: {sign}{m['change_pct']}% "
            f"({m['open_price']:,.0f} → {m['current_price']:,.0f})\n"
        )

    alerts_text = ""
    for a in pre.get("position_alerts", []):
        alerts_text += (
            f"- {a['ticker']}: {a['distance_pct']}% from {a['level_type']} at {a['level']:,.0f}\n"
        )

    morning_alerts_text = ""
    morning_alerts = pre.get("morning_position_alerts", [])
    if morning_alerts:
        morning_alerts_text = "\n## MORNING POSITION ALERTS (from position monitor)\n"
        for a in morning_alerts:
            consensus = f" [{a['consensus']}]" if a.get("consensus") else ""
            dissent = ""
            dv = a.get("dissenting_views") or []
            if dv:
                dissent = f" (dissent: {'; '.join(str(d) for d in dv[:2])})"
            morning_alerts_text += (
                f"- {a['ticker']}: {a['action']} ({a['urgency']}){consensus}"
                f" — {(a.get('reason') or '')[:80]}{dissent}\n"
            )

    directive_text = ""
    directive_data = pre.get("strategy_directive")
    if directive_data:
        filtered = _truncate_directive(directive_data.get("directive", ""))
        if filtered:
            directive_text = f"\n## TODAY'S STRATEGY (relevant sections)\n{filtered}\n"
        constraints = directive_data.get("constraints", {})
        if constraints:
            directive_text += (
                f"Constraints: Budget {(constraints.get('budget_vnd') or 0):,} VND | "
                f"Max Entries: {constraints.get('max_new_entries') or 0} | "
                f"Min R:R: {constraints.get('min_rr', 2.5) or 'N/A'}\n"
            )

    deployable = pre.get("deployable_cash", 0)
    catalyst_context = pre.get("catalyst_context", "")
    catalyst_section = (
        f"\n## STRUCTURAL CATALYSTS & CAPITAL EVENTS\n{catalyst_context}\n"
        if catalyst_context
        else ""
    )
    max_loss_section = ""
    if pre.get("max_loss_context"):
        max_loss_section = f"\n## {pre['max_loss_context']}\n"

    portfolio_section = ""
    if portfolio_context:
        from pipeline.context_blocks import PORTFOLIO_HEADER

        portfolio_section = f"\n{PORTFOLIO_HEADER}\n{portfolio_context}\n"

    recent_trades_section = f"\n{recent_trades_context}\n" if recent_trades_context else ""
    learnings_section = f"\n{learnings_context}\n" if learnings_context else ""
    executed_trades_section = f"\n{executed_trades_context}\n" if executed_trades_context else ""
    midday_prices_section = f"\n{midday_prices_context}\n" if midday_prices_context else ""

    return f"""Review the morning session and generate afternoon plan.

## MORNING RECOMMENDATIONS
{recs_text}

## PRE-COMPUTED DATA (these are verified, use them as-is)
Deployable cash: {deployable:,.0f} VND

### Entry Prices Reached (user has NOT bought these yet)
{entries_text or "None"}

### Big Movers (±3%)
{movers_text or "None"}

### Position Alerts
{alerts_text or "None"}
{morning_alerts_text}
{portfolio_section}{recent_trades_section}{learnings_section}{executed_trades_section}{midday_prices_section}{directive_text}{catalyst_section}{max_loss_section}
## YOUR TASK
DECLARED TRADING MODE: {trading_mode} (computed deterministically from cash balance — use this exact mode)
1. Review midday prices above (pre-loaded)
2. Write: morning_reflection, afternoon_plan, capital_note
3. For every recommendation_override that revises a price, cite the exact \
VND integer from the injected position_alerts table. \
Set `revised_stop=NN,NNN`, `revised_entry=NN,NNN`, `revised_target=NN,NNN` \
to the exact VND integer (e.g., `44910`, never `44.91`).
Afternoon recommendations use the declared trading mode above. Match the mode label exactly."""
