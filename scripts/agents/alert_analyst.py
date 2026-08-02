"""
Mini Alert Analyst — lightweight analysis when an alert triggers.

Hybrid agent: config from DB (load_agent_config), inline tools for real-time data.
Called by alert_monitor.py on notify_and_analyze alerts.
"""

import contextlib
from datetime import date

from pydantic import BaseModel

from shared.agent_config import load_agent_config
from shared.trading_config import get_trading_config

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout
from .tools.portfolio import get_cash_balance_async, get_holdings_async
from .tools.technicals import get_ticker_data_async


def compute_position_size(entry: float | None, stop: float | None) -> int | None:
    """Deterministic position sizing from entry/stop using 2% risk rule.

    Returns:
        Number of shares, or None if entry/stop invalid.
    """
    if not entry or not stop or entry <= stop:
        return None
    risk = entry - stop
    if risk <= 0:
        return None
    max_risk_vnd = get_trading_config().max_risk_per_trade
    return int(max_risk_vnd / risk)


class AlertAnalysis(BaseModel):
    """Structured output for alert analysis."""

    ticker: str
    recommendation: str  # BUY_NOW, WAIT, SKIP, EXIT_NOW
    confidence: str  # high, medium, low
    reasoning: str  # 2-3 sentences


async def create_analyst_agent():
    """Create the mini analyst agent with tools. Hybrid: DB config + inline tools."""
    config = await load_agent_config("alert_analyst")
    # HOOK-ALLOW: no-tickers-scope (alert_analyst reads pre-computed alerts; ticker is per-call)
    agent = create_agent(config, output_type=AlertAnalysis)

    @agent.tool_plain
    async def get_technicals(ticker: str) -> str:
        """Get current technicals for a ticker.

        Args:
            ticker: Stock ticker.
        """
        data = await get_ticker_data_async(ticker)
        if not data or "error" in data:
            return f"No technicals for {ticker}"
        # Extract key fields
        parts = [f"Ticker: {ticker}"]
        for key in [
            "close_vnd",
            "rsi",
            "macd_signal",
            "trend",
            "strength",
            "supertrend_direction",
            "adx",
            "bb_percent",
            "stoch_k",
        ]:
            if key in data and data[key] is not None:
                parts.append(f"{key}: {data[key]}")
        return "\n".join(parts)

    @agent.tool_plain
    async def get_portfolio() -> str:
        """Get current holdings and cash balance."""
        holdings_wrapper = await get_holdings_async()
        cash = await get_cash_balance_async()
        balance = cash.get("cash_balance") or cash.get("total_cash") or 0
        deployable = max(0, balance - get_trading_config().min_cash_reserve)
        parts = [f"Cash: {balance:,.0f} VND (deployable: {deployable:,.0f})"]
        slices: list[dict] = holdings_wrapper.get("holdings") or []
        for h in slices:
            ticker = h.get("ticker") or "?"
            if ticker == "Cash":
                continue
            plan_type = h.get("plan_type") or "?"
            label = f"{ticker} {plan_type}" if plan_type != "?" else ticker
            parts.append(
                f"{label}: {h.get('shares') or 0} shares @ {(h.get('avg_cost_vnd') or 0):,.0f}"
            )
        return "\n".join(parts)

    @agent.tool_plain
    async def get_foreign_flow(ticker: str) -> str:
        """Get foreign/prop/retail flow for a ticker.

        Args:
            ticker: Stock ticker (e.g. FPT).
        """
        try:
            from .tools.enrichment import get_ticker_flow_async

            flow = await get_ticker_flow_async(ticker.upper(), date.today())
            if not flow or "error" in flow:
                return f"No flow data for {ticker}"
            foreign = flow.get("foreign_net")
            prop = flow.get("prop_net")
            retail = flow.get("retail_net")
            parts = [f"Flow — {ticker.upper()}:"]
            if foreign is not None:
                parts.append(f"  Foreign net: {float(foreign) / 1e9:+.1f}B VND")
            if prop is not None:
                parts.append(f"  Prop net: {float(prop) / 1e9:+.1f}B VND")
            if retail is not None:
                parts.append(f"  Retail net: {float(retail) / 1e9:+.1f}B VND")
            return "\n".join(parts)
        except Exception as e:
            return f"Flow error for {ticker}: {e}"

    @agent.tool_plain
    async def get_selloff_pattern(ticker: str) -> str:
        """Detect multi-day sell-off pattern (capitulation, exhaustion, orderly decline).

        Args:
            ticker: Stock ticker (e.g. FPT).
        """
        try:
            from .tools.selloff_detector import detect_selloff_setup

            setup = await detect_selloff_setup(ticker.upper(), date.today())
            if not setup:
                return f"{ticker}: No sell-off pattern detected"
            vp = setup.get("volume_profile") or {}
            return (
                f"Sell-off — {ticker.upper()}: {setup['classification']} ({setup['conviction']})\n"
                f"  Consecutive red days: {setup['consecutive_red_days']}\n"
                f"  Volume: {vp.get('current_vol', 0):,} ({vp.get('ratio', 0):.1f}x avg)\n"
                f"  RSI: {setup['rsi']}"
            )
        except Exception as e:
            return f"Sell-off pattern error for {ticker}: {e}"

    @agent.tool_plain
    async def get_bounce_stats(ticker: str) -> str:
        """Get historical RSI oversold bounce statistics for a ticker.

        Args:
            ticker: Stock ticker (e.g. FPT).
        """
        try:
            from .tools.statistics import get_oversold_stats_async

            result = await get_oversold_stats_async(
                ticker.upper(), rsi_threshold=30.0, days_back=90
            )
            return result.get("prose", f"No oversold stats for {ticker}")
        except Exception as e:
            return f"Bounce stats error for {ticker}: {e}"

    return agent


async def analyze_alert(alert: dict, prices: dict[str, dict], technicals: dict[str, dict]) -> str:
    """Run mini analysis for a triggered alert.

    Args:
        alert: The triggered alert record
        prices: Current price data
        technicals: Current technical data

    Returns:
        Human-readable analysis string for Telegram.
    """
    agent = await create_analyst_agent()

    ticker = alert["ticker"]
    price = prices.get(ticker, {})
    tech = technicals.get(ticker, {})

    # Build compound conditions display
    conditions = alert.get("conditions", [])
    logic = alert.get("condition_logic", "ALL")
    if conditions:
        cond_parts = [
            f"{c.get('condition_type', '')} {c.get('condition_value', '')}" for c in conditions
        ]
        cond_display = f" {logic} ".join(cond_parts)
    else:
        cond_display = "N/A"

    tech_summary = ""
    if tech:
        tech_parts = []
        for key in [
            "rsi",
            "macd_signal",
            "trend",
            "strength",
            "supertrend_direction",
            "adx",
            "bb_percent",
            "stoch_k",
        ]:
            if key in tech and tech[key] is not None:
                tech_parts.append(f"{key}: {tech[key]}")
        if tech_parts:
            tech_summary = "Technicals: " + ", ".join(tech_parts) + "\n"

    context = (
        f"ALERT TRIGGERED: {ticker}\n"
        f"Conditions [{logic}]: {cond_display}\n"
        f"Recommended: {alert.get('recommended_action', 'WATCH')}\n"
        f"Rationale: {alert.get('rationale', 'N/A')}\n"
        f"Current price: {price.get('close', 'N/A')}\n"
        f"Today range: {price.get('low', 'N/A')} - {price.get('high', 'N/A')}\n"
        f"{tech_summary}"
    )

    if alert.get("entry_price"):
        context += f"Entry target: {alert['entry_price']}\n"
    if alert.get("stop_price"):
        context += f"Stop: {alert['stop_price']}\n"
    if alert.get("target_price"):
        context += f"Target: {alert['target_price']}\n"

    # Inject tranche context for multi-tranche dip-buy setups
    import json as _json

    raw_meta = alert.get("alert_metadata")
    metadata: dict = {}
    if isinstance(raw_meta, str):
        with contextlib.suppress(Exception):
            metadata = _json.loads(raw_meta)
    elif isinstance(raw_meta, dict):
        metadata = raw_meta

    if metadata.get("tranche"):
        context += (
            f"\nDIP-BUY SETUP: {metadata.get('setup_type', 'N/A')} "
            f"({metadata.get('conviction', 'N/A')})\n"
            f"Tranche: {metadata['tranche']}/{metadata.get('total_tranches', '?')} "
            f"({metadata.get('pct_of_size', 50)}% of full position)\n"
        )
        # For tranche 2+, fetch prior tranche analysis from alert_history
        if metadata["tranche"] >= 2 and metadata.get("setup_id"):
            try:
                from shared.database import fetch_one as _fetch_one

                sibling = await _fetch_one(
                    """SELECT a.ticker, a.entry_price, a.triggered_at,
                              h.event_data
                       FROM alerts a
                       LEFT JOIN alert_history h
                         ON h.alert_id = a.id AND h.event_type = 'analyzed'
                       WHERE a.alert_metadata->>'setup_id' = $1
                         AND a.id != $2
                         AND a.status = 'triggered'
                       ORDER BY a.triggered_at DESC LIMIT 1""",
                    metadata["setup_id"],
                    alert.get("id", 0),
                )
                if sibling:
                    sibling = dict(sibling)
                    event_data = sibling.get("event_data") or {}
                    if isinstance(event_data, str):
                        try:
                            event_data = _json.loads(event_data)
                        except Exception:
                            event_data = {}
                    prior_analysis = (event_data.get("analysis") or "N/A")[:200]
                    context += (
                        f"PRIOR TRANCHE: Tranche 1 triggered at "
                        f"{sibling.get('entry_price', 'N/A'):,} VND\n"
                        f"  Prior analyst: {prior_analysis}\n"
                        f"  NOTE: Higher conviction required — capital already deployed.\n"
                    )
            except Exception:
                pass  # Non-fatal: proceed without prior tranche context

    # Pre-compute position size deterministically
    entry = alert.get("entry_price")
    stop = alert.get("stop_price")
    position_size = compute_position_size(entry, stop)

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        result = await run_agent_with_total_timeout(
            agent,
            f"{context}\n\nAnalyze this alert and decide: BUY_NOW, WAIT, SKIP, or EXIT_NOW.",
            agent_name="alert_analyst",
            deps=AgentDeps(
                scan_date=None,
                agent_key="alert_analyst",
                tickers_in_scope=[ticker],
            ),
            total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
        )
        analysis = result.output
        msg = f"{analysis.recommendation} ({analysis.confidence})\n{analysis.reasoning}"
        if analysis.recommendation == "BUY_NOW" and position_size:
            msg += f"\nSize: {position_size} shares"
        return msg
    except Exception as e:
        return f"Analysis error: {e}"
