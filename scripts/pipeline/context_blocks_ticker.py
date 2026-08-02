"""Ticker-specific context block formatters for agent prompt injection.

Formats per-ticker briefings combining technicals, flow, insider, RS,
beliefs, and company profiles into compact pipe-delimited text blocks.

Token budget: ≤300 tokens per ticker.
See: .claude/skills/agent-development/instructions.md § Context Injection
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents.belief_models import decay_belief_conviction
from agents.tools.technicals import is_structural_uptrend
from shared.formatting import format_price_k, format_vnd

from .context_blocks_commodity import COMMODITY_LABELS
from .context_blocks_macro import format_macro_signal_transmission
from .context_blocks_ticker_news import (
    format_article_lines,
    format_longterm_line,
    format_narrative_line,
)

if TYPE_CHECKING:
    from pipeline.enrichment_loader import EnrichmentData
    from pipeline.types import GeopoliticalShockDict
    from shared.rules.catalyst_override import CatalystBoost, CatalystInput, GeoLabel

TICKER_DATA_HEADER = "## TICKER DATA (pre-loaded — analyze directly)"

# Catalyst event description truncation for briefing line — short enough to
# fit the compact briefing format, long enough to carry meaning.
CATALYST_EVENT_MAX_LEN = 80

# Maps company macro_sensitivities factor names to commodity_prices keys
FACTOR_TO_COMMODITY = {
    "steel_price": "steel_hrc",
    "iron_ore": "iron_ore",
    "oil_price": "oil_crude",
    "gold_price": "gold_global",
}


def _direction_label(
    flag: bool | None,
    rising: str = "rising",
    falling: str = "falling",
) -> str | None:
    """Map a tri-state direction flag (True/False/None) to a display label.

    None represents "flat-within-delta / unknown" — do not emit a tag.
    """
    if flag is True:
        return rising
    if flag is False:
        return falling
    return None


def format_ticker_briefing(
    ticker: str,
    technicals: dict | None = None,
    flow: dict | None = None,
    insider: list | None = None,
    relative_strength: float | None = None,
    beliefs: list | None = None,
    company_profile: dict | None = None,
    commodity_prices: dict | None = None,
    agent_key: str | None = None,
    macro_metrics: dict | None = None,
    geopolitical_shock: GeopoliticalShockDict | None = None,
    articles: list[dict] | None = None,
    narratives: list[dict] | None = None,
    longterm: dict | None = None,
    catalyst_boost: CatalystBoost | None = None,
    geo_label: GeoLabel | None = None,
) -> str:
    """Compact per-ticker briefing combining technicals, flow, insider, RS, beliefs.

    Args:
        ticker: Stock ticker symbol
        technicals: Dict with rsi, macd, trend, pattern, support, resistance, close, etc.
        flow: Dict with foreign_net, prop_net, retail_net, order_imbalance
        insider: List of insider transaction dicts
        relative_strength: 20d RS vs VN-Index (>1 = outperforming)
        beliefs: List of prior belief dicts for this ticker
        company_profile: Dict with sector, business_summary, macro_sensitivities
        macro_metrics: Phase 1 macro dict with usd_vnd_signal, vix_signal, etc.
        geopolitical_shock: Active geo shock dict with catalyst_key, affected_tickers
        articles: Recent articles already filtered to mention this ticker
        narratives: Active narratives already filtered to mention this ticker
        longterm: Longterm watchlist config dict for this ticker (or None if swing only)
    """
    close_price = (technicals or {}).get("close") or 0
    lines = [f"## {ticker} | {format_price_k(close_price)} VND"]

    if not technicals:
        lines.append("[INSUFFICIENT TECHNICAL DATA — no RSI/MACD/ADX/Supertrend available]")

    if technicals:
        tech_parts = []
        signals = technicals.get("momentum_signals")

        rsi = technicals.get("rsi")
        if rsi is not None:
            zone = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
            rsi_bits = [zone]
            if signals is not None:
                direction = _direction_label(signals.rsi_rising)
                if direction:
                    rsi_bits.append(direction)
            tech_parts.append(f"RSI: {rsi:.1f} ({', '.join(rsi_bits)})")

        # MACD histogram direction — sign + slope. The histogram value
        # carries both crossover polarity (sign) and momentum direction (slope).
        macd_hist = technicals.get("macd_histogram")
        if macd_hist is not None:
            sign = "positive" if macd_hist > 0 else "negative" if macd_hist < 0 else "flat"
            mac_bits = [sign]
            if signals is not None:
                direction = _direction_label(signals.macd_hist_rising)
                if direction:
                    mac_bits.append(direction)
            tech_parts.append(f"MACD hist: {macd_hist:+.2f} ({', '.join(mac_bits)})")
        else:
            # Fallback to legacy macd dict/string shape for backwards-compat
            # on any pipeline that hasn't surfaced macd_histogram yet.
            macd = technicals.get("macd") or technicals.get("macd_signal")
            if isinstance(macd, dict):
                macd_signal = macd.get("signal") or macd.get("crossover")
                if macd_signal:
                    tech_parts.append(f"MACD: {macd_signal}")
            elif isinstance(macd, str):
                tech_parts.append(f"MACD: {macd}")

        trend = technicals.get("trend")
        if isinstance(trend, dict):
            trend_str = trend.get("trend") or trend.get("direction")
            if trend_str:
                strength = trend.get("strength") or ""
                tech_parts.append(f"Trend: {trend_str}" + (f" ({strength})" if strength else ""))
        elif isinstance(trend, str):
            tech_parts.append(f"Trend: {trend}")

        support = technicals.get("support")
        resistance = technicals.get("resistance")
        if support:
            tech_parts.append(f"S: {format_price_k(support)}")
        if resistance:
            tech_parts.append(f"R: {format_price_k(resistance)}")

        # Structural uptrend indicator (Supertrend UP + ADX DM+ > DM-)
        if is_structural_uptrend(technicals):
            tech_parts.append("STRUCTURAL UPTREND ✓")
        elif (technicals.get("supertrend_direction") or "").upper() == "DOWN":
            tech_parts.append("Supertrend: DOWN")

        # Raw ADX strength + directional index values. Direction tag (rising/
        # fading) only surfaces when ADX ≥ 25 — on weak trends the direction
        # noise dominates and would mislead the LLM.
        adx_value = technicals.get("adx")
        adx_dmp = technicals.get("adx_dmp")
        adx_dmn = technicals.get("adx_dmn")
        if adx_value is not None:
            adx_bits: list[str] = []
            if adx_value >= 25:
                adx_bits.append("strong")
                if signals is not None:
                    direction = _direction_label(
                        signals.adx_rising, rising="rising", falling="fading"
                    )
                    if direction:
                        adx_bits.append(direction)
            adx_tag = f" ({', '.join(adx_bits)})" if adx_bits else ""
            tech_parts.append(f"ADX: {adx_value:.0f}{adx_tag}")
        if adx_dmp is not None and adx_dmn is not None:
            bullish = adx_dmp > adx_dmn
            tech_parts.append(
                f"DM+/DM-: {adx_dmp:.0f}/{adx_dmn:.0f} ({'bullish' if bullish else 'bearish'})"
            )

        # Volume trend direction — surfaced from momentum_signals so agents
        # reason about volume-confirmation alongside ADX/RSI/MACD.
        if signals is not None:
            direction = _direction_label(signals.volume_trending_up)
            if direction:
                tech_parts.append(f"Vol: {direction}")

        if tech_parts:
            lines.append(" | ".join(tech_parts))

    # Catalyst attachment — surface the active boost so sector prompts can
    # cite the catalyst in a trend-follow BUY decision. Same data that
    # drives the MR→MOMENTUM promotion in strategy_classifier.
    if catalyst_boost:
        event_text = catalyst_boost["catalyst_event"][:CATALYST_EVENT_MAX_LEN]
        lines.append(
            f"CATALYST: {catalyst_boost['catalyst_key']} / "
            f"lifecycle={catalyst_boost['phase_lifecycle']} — {event_text}"
        )

    trade_setup = (technicals or {}).get("trade_setup")
    if trade_setup and trade_setup.get("valid"):
        entry = trade_setup.get("entry") or 0
        stop = trade_setup.get("stop") or 0
        target_raw = trade_setup.get("target")
        risk_reward_raw = trade_setup.get("risk_reward")
        from shared.rules.rr_floors import RR_FLOOR_DEFAULT

        if risk_reward_raw is None:
            # ATR_TRAIL contract (SWI-115): risk_reward=None end-to-end. Display
            # the trailing-strategy intent instead of coercing to 0.0 (which
            # would mislead the LLM into flagging a [LOW R:R] tag).
            risk_reward_label = "R:R trailing (ATR_TRAIL)"
            target_label = format_price_k(target_raw) if target_raw else "trailing"
        else:
            risk_reward = float(risk_reward_raw)
            low_rr_tag = " [LOW R:R — below threshold]" if risk_reward < RR_FLOOR_DEFAULT else ""
            risk_reward_label = f"R:R {risk_reward:.1f}{low_rr_tag}"
            target_label = format_price_k(target_raw or 0)
        lines.append(
            f"Setup: Entry {format_price_k(entry)} | Stop {format_price_k(stop)}"
            f" | Target {target_label} | {risk_reward_label}"
        )

    if flow:
        flow_parts = []
        foreign_net = flow.get("foreign_net")
        if foreign_net is not None:
            direction = "buy" if foreign_net > 0 else "sell"
            flow_parts.append(f"Foreign: net {direction} {format_vnd(abs(foreign_net))}")
        prop_net = flow.get("prop_net")
        if prop_net is not None:
            flow_parts.append(f"Prop: {format_vnd(prop_net)}")
        if flow_parts:
            lines.append("Flow: " + " | ".join(flow_parts))

    if relative_strength is not None:
        rs_tag = (
            "outperforming"
            if relative_strength > 1.05
            else "underperforming"
            if relative_strength < 0.95
            else "in-line"
        )
        lines.append(f"RS: {relative_strength:.2f}x ({rs_tag})")

    if insider:
        buys = sum(
            1 for transaction in insider if (transaction.get("action") or "").upper() == "BUY"
        )
        sells = sum(
            1 for transaction in insider if (transaction.get("action") or "").upper() == "SELL"
        )
        if buys or sells:
            lines.append(f"Insider (90d): {buys} buys, {sells} sells")

    if beliefs:
        own_belief = None
        other_beliefs = []
        for belief in beliefs:
            if agent_key and belief.get("agent_key") == agent_key:
                own_belief = belief
            else:
                other_beliefs.append(belief)

        if own_belief:
            direction = own_belief.get("direction") or "NEUTRAL"
            bull = float(own_belief.get("bull_probability") or 0)
            base = float(own_belief.get("base_probability") or 0)
            bear = float(own_belief.get("bear_probability") or 0)
            days_held = own_belief.get("days_held") or 1
            status = own_belief.get("belief_status") or "NEW"
            decayed_conviction = decay_belief_conviction(
                float(own_belief.get("conviction") or 0), days_held
            )
            lines.append(
                f"YOUR PRIOR: {direction} bull={bull:.0%}/base={base:.0%}"
                f"/bear={bear:.0%} held {days_held}d conv={decayed_conviction:.0%} [{status}]"
            )

        # Sort by conviction descending so strongest signal survives truncation
        sorted_other = sorted(
            other_beliefs, key=lambda belief: float(belief.get("conviction") or 0), reverse=True
        )
        for belief in sorted_other[:2]:
            direction = belief.get("direction") or "NEUTRAL"
            conviction = float(belief.get("conviction") or 0)
            agent = belief.get("agent_key") or "?"
            lines.append(f"Belief ({agent}): {direction} ({conviction:.0%})")

    # Hoist sensitivities once for commodity, macro signal, and geo sections
    sensitivities = (company_profile or {}).get("macro_sensitivities") or []

    if company_profile:
        sector = company_profile.get("sector") or ""
        profile_parts = []
        if sector:
            profile_parts.append(f"Sector: {sector}")
        if sensitivities:
            sensitivity_strs = [
                f"{sensitivity.get('factor', '?')} {sensitivity.get('direction', '?')}"
                for sensitivity in sensitivities[:3]
            ]
            profile_parts.append("Macro: " + ", ".join(sensitivity_strs))
        if profile_parts:
            lines.append(" | ".join(profile_parts))

    if commodity_prices and sensitivities:
        transmission_parts = []
        for sensitivity in sensitivities:
            factor = sensitivity.get("factor") or ""
            direction = (sensitivity.get("direction") or "").upper()
            commodity_key = FACTOR_TO_COMMODITY.get(factor)
            if not commodity_key:
                continue
            commodity_data = commodity_prices.get(commodity_key) or {}
            change_5d = commodity_data.get("change_5d_pct")
            if change_5d is None or abs(change_5d) < 1.0:
                continue
            price_up = change_5d > 0
            # POSITIVE sensitivity: price up = TAILWIND, price down = HEADWIND
            # NEGATIVE sensitivity: price up = HEADWIND, price down = TAILWIND
            if direction == "POSITIVE":
                impact = "TAILWIND" if price_up else "HEADWIND"
            elif direction == "NEGATIVE":
                impact = "HEADWIND" if price_up else "TAILWIND"
            else:
                continue
            label = COMMODITY_LABELS.get(commodity_key) or commodity_key
            transmission_parts.append(f"{label}: {change_5d:+.1f}% 5d → {impact}")
        if transmission_parts:
            lines.append("Commodity: " + " | ".join(transmission_parts))

    if macro_metrics and sensitivities:
        macro_parts = format_macro_signal_transmission(sensitivities, macro_metrics)
        if macro_parts:
            lines.append("Macro signal: " + " | ".join(macro_parts))

    if geopolitical_shock and geo_label:
        phase_name = geopolitical_shock.get("phase_name") or ""
        catalyst_event = (geopolitical_shock.get("catalyst_event") or "")[:60]
        suffix = ""
        if geo_label == "GEO_MIXED":
            suffix = " — shock-exposed + stacked positive catalysts"
        lines.append(f"GEO: {geo_label} ({phase_name} — {catalyst_event}){suffix}")

    if longterm:
        thesis_line = format_longterm_line(longterm)
        if thesis_line:
            lines.append(thesis_line)

    if narratives:
        narrative_line = format_narrative_line(narratives)
        if narrative_line:
            lines.append(narrative_line)

    if articles:
        lines.extend(format_article_lines(articles, limit=2))

    return "\n".join(lines)


def _precompute_geo_labels(
    tickers: list[str],
    enrichment_data: EnrichmentData | None,
    geopolitical_shock: GeopoliticalShockDict | None,
    catalyst_boosted: dict[str, CatalystBoost] | None,
    active_catalysts: list[CatalystInput] | None,
) -> dict[str, GeoLabel | None]:
    """Classify every ticker once so per-ticker briefing render is O(1).

    Without this, the per-ticker branch in `format_ticker_briefing` would
    call `classify_geo_label` N times per briefing × 3 briefing passes per
    sector — O(N × M_catalysts) iterations that repeat identical work.
    """
    if not geopolitical_shock:
        return {}
    from shared.rules.catalyst_override import classify_geo_label

    raw_factors = geopolitical_shock.get("catalyst_factors")
    shock_factors: list[str] | None = list(raw_factors) if raw_factors else None
    boosts = catalyst_boosted or {}
    profiles = enrichment_data.company_profiles if enrichment_data else {}
    labels: dict[str, GeoLabel | None] = {}
    for ticker in tickers:
        profile = profiles.get(ticker.upper()) or profiles.get(ticker) or {}
        labels[ticker] = classify_geo_label(
            ticker=ticker,
            macro_sensitivities=profile.get("macro_sensitivities") or [],
            geopolitical_shock=geopolitical_shock,
            positive_catalyst_boosts=boosts,
            active_catalysts=active_catalysts,
            shock_factors=shock_factors,
        )
    return labels


def format_ticker_briefings(
    tickers: list[str],
    technicals: dict | None = None,
    enrichment_data: EnrichmentData | None = None,
    commodity_prices: dict | None = None,
    agent_key: str | None = None,
    macro_metrics: dict | None = None,
    geopolitical_shock: GeopoliticalShockDict | None = None,
    catalyst_boosted: dict[str, CatalystBoost] | None = None,
    active_catalysts: list[CatalystInput] | None = None,
) -> str:
    """Build compact briefings for multiple tickers from batch data.

    Args:
        tickers: List of ticker symbols to include
        technicals: {ticker: {rsi, macd, ...}} batch technicals from Phase 0
        enrichment_data: EnrichmentData instance with flow, insider, RS, etc.
        commodity_prices: {commodity_key: {price, change_5d_pct, unit}} from Phase 1
        agent_key: If set, renders this agent's own prior belief with extra detail
        macro_metrics: Phase 1 macro dict for non-commodity signal transmission
        geopolitical_shock: Active geo shock dict for per-ticker exposure labels

    Returns:
        Combined briefings, one block per ticker
    """
    if not tickers:
        return ""

    articles_by_ticker = enrichment_data.articles_by_ticker if enrichment_data else {}
    narratives_by_ticker = enrichment_data.narratives_by_ticker if enrichment_data else {}
    longterm_map = enrichment_data.longterm_config if enrichment_data else {}
    geo_labels = _precompute_geo_labels(
        tickers=tickers,
        enrichment_data=enrichment_data,
        geopolitical_shock=geopolitical_shock,
        catalyst_boosted=catalyst_boosted,
        active_catalysts=active_catalysts,
    )

    blocks = [TICKER_DATA_HEADER]
    for ticker in tickers:
        ticker_technicals = (technicals or {}).get(ticker)
        ticker_flow = None
        ticker_insider = None
        ticker_rs = None
        ticker_beliefs = None
        ticker_profile = None

        if enrichment_data:
            ticker_flow = enrichment_data.ticker_flow.get(ticker)
            ticker_insider = enrichment_data.ticker_insider.get(ticker)
            ticker_rs = enrichment_data.ticker_rs.get(ticker)
            ticker_beliefs = enrichment_data.ticker_beliefs.get(ticker)
            ticker_profile = enrichment_data.company_profiles.get(ticker)

        upper = ticker.upper()
        boosted_map = catalyst_boosted or {}
        ticker_boost = boosted_map.get(upper) or boosted_map.get(ticker)
        blocks.append(
            format_ticker_briefing(
                ticker=ticker,
                technicals=ticker_technicals,
                flow=ticker_flow,
                insider=ticker_insider,
                relative_strength=ticker_rs,
                beliefs=ticker_beliefs,
                company_profile=ticker_profile,
                commodity_prices=commodity_prices,
                agent_key=agent_key,
                macro_metrics=macro_metrics,
                geopolitical_shock=geopolitical_shock,
                articles=articles_by_ticker.get(upper),
                narratives=narratives_by_ticker.get(upper),
                longterm=longterm_map.get(upper),
                catalyst_boost=ticker_boost,
                geo_label=geo_labels.get(ticker),
            )
        )

    return "\n\n".join(blocks)
