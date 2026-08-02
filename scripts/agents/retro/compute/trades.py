"""Closed-trade aggregation by ticker."""

from __future__ import annotations

from collections import defaultdict

from shared.neon import ClosedTradeEntry


def _build_closed_trade_map(closed_trades: list[ClosedTradeEntry]) -> dict[str, dict]:
    """Aggregate closed trades by ticker for evaluation.

    Handles multiple closes per ticker (different lots) by computing
    volume-weighted average exit price and summing net P/L.
    """
    ticker_trades: dict[str, list[dict]] = defaultdict(list)
    for trade in closed_trades:
        ticker = trade.get("ticker")
        if ticker:
            ticker_trades[ticker].append(trade)

    result = {}
    for ticker, trades in ticker_trades.items():
        total_shares = sum(trade.get("shares") or 0 for trade in trades)
        total_pl_net = sum(trade.get("pl_net") or 0 for trade in trades)

        if total_shares > 0:
            weighted_exit = sum(
                (trade.get("exit_price") or 0) * (trade.get("shares") or 0) for trade in trades
            )
            average_exit_price = round(weighted_exit / total_shares)

            weighted_pl_pct = sum(
                (trade.get("pl_pct") or 0.0) * (trade.get("shares") or 0) for trade in trades
            )
            average_pl_pct = round(weighted_pl_pct / total_shares, 4)
        else:
            average_exit_price = trades[0].get("exit_price") or 0
            average_pl_pct = trades[0].get("pl_pct") or 0.0

        result[ticker] = {
            "exit_price_vnd": average_exit_price,
            "pl_pct": average_pl_pct,
            "pl_net_vnd": total_pl_net,
            "total_shares": total_shares,
        }

    return result
