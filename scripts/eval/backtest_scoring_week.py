#!/usr/bin/env python3
"""Backtest scoring efficacy over a recent window.

Reads ``pre_gate_candidates`` rows for a date range (default: trailing 7
calendar days), fetches close prices via the vnstock-api ``/prices`` HTTP
endpoint, and reports whether the deterministic 0-100 score actually
ranks tickers by forward return at +1d / +3d / +5d horizons.

This is the missing piece next to ``score_tickers.py`` (rescore) and
``weight_correlation_audit.py`` (Phase A signal-strength on
``daily_recommendations``). It answers: "does the score the pipeline
PRODUCED on day T predict the return realised by day T+N?"

Metrics:
- Spearman ρ(score, forward_return) per horizon (aggregate + per-scan)
- Top-vs-bottom tercile spread (pooled)
- Hit rate (% positive forward return)

Read-only: queries ``pre_gate_candidates``, does not write.

Usage::

    uv run python scripts/eval/backtest_scoring_week.py \\
        [--start 2026-05-05] [--end 2026-05-08] \\
        [--phase morning] [--horizons 1,3,5]

Defaults: window = (today - 7d) .. (today - 1d), phase = morning,
horizons = 1,3,5.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from statistics import mean
from typing import TypedDict


class EnrichedRow(TypedDict):
    scan_date: date
    ticker: str
    score: float
    returns: dict[int, float | None]


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("backtest_scoring_week")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest scoring efficacy")
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--phase", default="morning", choices=("morning", "midday", "retro"))
    parser.add_argument(
        "--horizons",
        default="1,3,5",
        help="Comma-separated forward trading-day horizons",
    )
    return parser.parse_args()


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")

    def average_ranks(values: Sequence[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = average
            i = j + 1
        return ranks

    rx = average_ranks(xs)
    ry = average_ranks(ys)
    mean_x, mean_y = mean(rx), mean(ry)
    num = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    dx = sum((v - mean_x) ** 2 for v in rx) ** 0.5
    dy = sum((v - mean_y) ** 2 for v in ry) ** 0.5
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


async def _fetch_candidates(start: date, end: date, phase: str) -> list[dict[str, object]]:
    from shared.database import Database, close_db, fetch_all

    async with Database():
        try:
            rows = await fetch_all(
                """
                SELECT scan_date, ticker, score::float8 AS score,
                       gated_by, regime,
                       would_pass_score_gate
                FROM pre_gate_candidates
                WHERE scan_date BETWEEN $1 AND $2
                  AND phase = $3
                ORDER BY scan_date, score DESC
                """,
                start,
                end,
                phase,
            )
        finally:
            await close_db()
    return [dict(row) for row in rows]


async def _fetch_close_history(
    tickers: list[str], start: date, end: date
) -> dict[str, dict[date, float]]:
    """Fetch close prices via the project's HTTP enrichment client."""
    from shared.api.prices import get_ohlc_series

    series = await get_ohlc_series(
        tickers,
        start=start.isoformat(),
        end=end.isoformat(),
    )
    closes: dict[str, dict[date, float]] = {}
    for ticker, bars in (series or {}).items():
        per_ticker: dict[date, float] = {}
        for bar in bars or []:
            date_str = bar.get("date")
            close = bar.get("close")
            if not date_str or close is None:
                continue
            per_ticker[date.fromisoformat(str(date_str)[:10])] = float(close)
        if per_ticker:
            closes[ticker] = per_ticker
    return closes


def _forward_return(
    closes: dict[date, float],
    trading_days: list[date],
    scan_day: date,
    horizon: int,
) -> float | None:
    if scan_day not in trading_days:
        return None
    idx = trading_days.index(scan_day)
    if idx + horizon >= len(trading_days):
        return None
    base = closes.get(scan_day)
    forward = closes.get(trading_days[idx + horizon])
    if base is None or forward is None or base == 0:
        return None
    return (forward - base) / base * 100


def _report(
    candidates: list[dict[str, object]],
    closes_by_ticker: dict[str, dict[date, float]],
    horizons: list[int],
) -> None:
    union_days = sorted({d for closes in closes_by_ticker.values() for d in closes})
    if not union_days:
        logger.error("No price data returned — nothing to backtest")
        return

    horizon_label = " ".join(f"+{horizon}d%".rjust(7) for horizon in horizons)
    print(f"{'Scan':<11} {'Tkr':<5} {'Score':>6} {horizon_label}")
    print("-" * (24 + 8 * len(horizons)))

    enriched: list[EnrichedRow] = []
    for candidate in candidates:
        ticker = str(candidate["ticker"])
        scan_day = candidate["scan_date"]
        assert isinstance(scan_day, date)
        closes = closes_by_ticker.get(ticker, {})
        returns_by_horizon = {
            horizon: _forward_return(closes, union_days, scan_day, horizon) for horizon in horizons
        }
        enriched.append(
            EnrichedRow(
                scan_date=scan_day,
                ticker=ticker,
                score=float(candidate["score"]),  # type: ignore[arg-type]
                returns=returns_by_horizon,
            )
        )
        cells = " ".join(
            (
                "    -  "
                if returns_by_horizon[horizon] is None
                else f"{returns_by_horizon[horizon]:+6.2f}"
            ).rjust(7)
            for horizon in horizons
        )
        score_val = float(candidate["score"])  # type: ignore[arg-type]
        print(f"{scan_day.isoformat():<11} {ticker:<5} {score_val:>6.2f} {cells}")

    print("\n=== Aggregate ===")
    for horizon in horizons:
        pairs: list[tuple[float, float]] = [
            (row["score"], forward)
            for row in enriched
            if (forward := row["returns"][horizon]) is not None
        ]
        if not pairs:
            print(f"+{horizon}d: no observations (today blocks lookahead)")
            continue
        xs = [pair[0] for pair in pairs]
        ys = [pair[1] for pair in pairs]
        rho = _spearman(xs, ys)
        hit_rate = sum(1 for y in ys if y > 0) / len(ys) * 100
        average = mean(ys)
        print(
            f"+{horizon}d: N={len(pairs):3d}  Spearman(score,fwd)={rho:+.3f}  "
            f"mean_fwd={average:+.2f}%  hit_rate={hit_rate:.0f}%"
        )

    # Tercile spread at the shortest horizon
    shortest = horizons[0]
    pairs = sorted(
        [
            (row["score"], forward)
            for row in enriched
            if (forward := row["returns"][shortest]) is not None
        ],
        key=lambda pair: pair[0],
    )
    if len(pairs) >= 6:
        tercile = len(pairs) // 3
        bottom = pairs[:tercile]
        top = pairs[-tercile:]
        bottom_avg = mean(p[1] for p in bottom)
        top_avg = mean(p[1] for p in top)
        print(
            f"\n+{shortest}d  bottom tercile (n={len(bottom)}): "
            f"avg_score={mean(p[0] for p in bottom):.1f}  avg_fwd={bottom_avg:+.2f}%  "
            f"hit={sum(1 for p in bottom if p[1] > 0) / len(bottom) * 100:.0f}%"
        )
        print(
            f"+{shortest}d  top    tercile (n={len(top)}): "
            f"avg_score={mean(p[0] for p in top):.1f}  avg_fwd={top_avg:+.2f}%  "
            f"hit={sum(1 for p in top if p[1] > 0) / len(top) * 100:.0f}%"
        )
        print(f"+{shortest}d  top-bottom spread = {top_avg - bottom_avg:+.2f}%")

    print(f"\n=== Per-scan within-day Spearman (+{shortest}d) ===")
    by_scan: dict[date, list[tuple[float, float]]] = defaultdict(list)
    for row in enriched:
        forward = row["returns"][shortest]
        if forward is None:
            continue
        scan_day = row["scan_date"]
        by_scan[scan_day].append((row["score"], forward))
    for scan_day, pairs in sorted(by_scan.items()):
        if len(pairs) < 3:
            continue
        xs = [pair[0] for pair in pairs]
        ys = [pair[1] for pair in pairs]
        hit = sum(1 for y in ys if y > 0) / len(ys) * 100
        print(
            f"  {scan_day.isoformat()}: N={len(pairs):2d}  "
            f"ρ={_spearman(xs, ys):+.3f}  mean_fwd={mean(ys):+.2f}%  hit={hit:.0f}%"
        )


async def _main_async(args: argparse.Namespace) -> int:
    sys.path.insert(0, "scripts")
    from shared.env import load_env

    load_env()
    today = date.today()
    end = args.end or (today - timedelta(days=1))
    start = args.start or (end - timedelta(days=6))
    horizons = [int(h.strip()) for h in args.horizons.split(",") if h.strip()]
    if not horizons:
        logger.error("--horizons must contain at least one positive integer")
        return 2

    candidates = await _fetch_candidates(start, end, args.phase)
    if not candidates:
        logger.error(
            "No pre_gate_candidates rows for [%s..%s] phase=%s",
            start,
            end,
            args.phase,
        )
        return 1

    tickers = sorted({str(row["ticker"]) for row in candidates})
    price_end = today  # let server clip to last available bar
    closes = await _fetch_close_history(tickers, start, price_end)
    if not closes:
        logger.error("price fetch returned empty payload")
        return 1

    print(
        f"Backtest scoring  window=[{start}..{end}]  phase={args.phase}  "
        f"horizons={horizons}  N_candidates={len(candidates)}  tickers={len(tickers)}\n"
    )
    _report(candidates, closes, horizons)
    return 0


def main() -> int:
    sys.path.insert(0, "scripts")
    args = _parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
