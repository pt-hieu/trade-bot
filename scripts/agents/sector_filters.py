"""Deterministic post-processing filters and formatters for sector signals.

All functions are pure transforms on signal lists — no agent calls, no I/O.
"""

from __future__ import annotations

import logging

from .sector_analysts import SectorAnalystReport, SectorAnalystView
from .sector_models import SectorAnalysisResult, TickerSignal

logger = logging.getLogger(__name__)


def _format_sector_text(sector_name: str, result: SectorAnalysisResult) -> str:
    """Format structured result as text for synthesis context."""
    lines = [f"## {sector_name.upper()}"]
    for signal in result.signals:
        risk_suffix = f" | KEY RISK: {signal.key_risk}" if signal.key_risk else ""
        lines.append(f"{signal.ticker}: {signal.signal} — {signal.note}{risk_suffix}")
    lines.append(f"\n{result.summary}")
    return "\n".join(lines)


def _build_regime_context(
    market_level_dict: dict | None,
    macro_metrics_dict: dict | None,
    geopolitical_context: str = "",
    market_valuation: dict | None = None,
) -> str:
    """Build compact regime context block for sub-agent prompts using format_regime_block."""
    from pipeline.context_blocks import format_regime_block

    parts = [
        format_regime_block(
            market_level_dict, macro_metrics_dict, market_valuation=market_valuation
        )
    ]
    if geopolitical_context:
        parts.append(geopolitical_context)
    return "\n\n".join(parts)


def _apply_coverage_gaps(
    signals: list[TickerSignal],
    tickers: list[str],
    sub_reports: list[SectorAnalystReport] | None = None,
) -> list[TickerSignal]:
    """Recover aggregator coverage from sub-agent views (belief-recovery path).

    When sub-agents emitted views but the aggregator dropped them, derive the
    signal from those views (marked ``[DERIVED_FROM_BELIEFS]``). Tickers with
    zero sub-agent coverage are left uncovered — the per-ticker gate in
    ``shared/rules/belief_coverage.py`` raises when 2+ expected tickers lack
    any belief, so silent-partial publishes are structurally impossible."""
    from shared.rules.belief_to_signal import derive_signal_from_views

    covered = {signal.ticker.upper() for signal in signals}

    views_by_ticker: dict[str, list[SectorAnalystView]] = {}
    for report in sub_reports or ():
        for view in report.views:
            if view.ticker:
                views_by_ticker.setdefault(view.ticker.upper(), []).append(view)

    result = list(signals)
    for ticker in tickers:
        ticker_upper = ticker.upper()
        if ticker_upper in covered:
            continue

        ticker_views = views_by_ticker.get(ticker_upper, [])
        if not ticker_views:
            logger.warning("Sector coverage gap: %s has no sub-agent coverage", ticker)
            continue

        derived_signal, derived_note = derive_signal_from_views(ticker_views)
        logger.warning(
            "Sector coverage gap recovered from sub-agent views: %s → %s (%d view(s))",
            ticker,
            derived_signal,
            len(ticker_views),
        )
        result.append(
            TickerSignal(
                ticker=ticker,
                signal=derived_signal,
                note=derived_note,
                confidence="LOW",
            )
        )
    return result


def _apply_regime_downgrade(
    signals: list[TickerSignal], global_risk_regime: str
) -> list[TickerSignal]:
    """Downgrade BUY without HIGH confidence in CRISIS regime only."""
    if global_risk_regime != "CRISIS":
        return signals
    result = []
    for signal in signals:
        if signal.signal == "BUY" and signal.confidence != "HIGH":
            logger.info(
                "Regime downgrade: %s BUY → WATCH (confidence=%s, regime=%s)",
                signal.ticker,
                signal.confidence,
                global_risk_regime,
            )
            result.append(
                signal.model_copy(
                    update={
                        "signal": "WATCH",
                        "note": f"[REGIME_DOWNGRADE] {signal.note}",
                        # BUY signal implies trigger-on-strength → BREAKOUT.
                        "plan_shape": signal.plan_shape or "BREAKOUT",
                    }
                )
            )
        else:
            result.append(signal)
    return result


def _apply_cash_gate(signals: list[TickerSignal], entries_allowed: bool) -> list[TickerSignal]:
    """Convert BUY → WATCH when entries are not allowed (cash gate)."""
    if entries_allowed:
        return signals
    result = []
    for signal in signals:
        if signal.signal == "BUY":
            result.append(
                signal.model_copy(
                    update={
                        "signal": "WATCH",
                        "note": f"[CASH_GATE] {signal.note}",
                        # BUY signal implies trigger-on-strength → BREAKOUT.
                        "plan_shape": signal.plan_shape or "BREAKOUT",
                    }
                )
            )
        else:
            result.append(signal)
    return result
