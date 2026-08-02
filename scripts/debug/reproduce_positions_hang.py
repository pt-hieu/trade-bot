"""Reproduce positions_value/positions_thesis SILENT_PROVIDER_HANG locally.

Runs the two hung agents from GH run 24647108805 against local DB + OpenRouter.
Measures per-trial wall time. Repeats to classify as deterministic vs transient.

Usage:
    uv run python scripts/debug/reproduce_positions_hang.py
    # or
    uv run python scripts/debug/reproduce_positions_hang.py --trials 3
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.positions_ensemble import _run_analyst  # type: ignore
from agents.tools.portfolio import get_holdings_async  # type: ignore
from pipeline.context_blocks import (  # type: ignore
    format_portfolio_block,
    format_regime_block,
    format_ticker_briefings,
)
from pipeline.enrichment_loader import batch_fetch_enrichment  # type: ignore
from shared.api.technicals import get_technicals  # type: ignore
from shared.trading_config import init_trading_config  # type: ignore


async def build_context():
    """Replicate what monitor_positions_ensemble builds before calling _run_analyst."""
    scan_date = date.today()

    await init_trading_config()
    holdings_data = await get_holdings_async()
    if holdings_data and "error" in holdings_data and "holdings" not in holdings_data:
        raise SystemExit(f"get_holdings_async returned error: {holdings_data.get('error')}")
    holdings_list = holdings_data.get("holdings", []) if holdings_data else []
    if not isinstance(holdings_list, list):
        holdings_list = []
    held_tickers = [
        slice_row.get("ticker")
        for slice_row in holdings_list
        if isinstance(slice_row, dict) and slice_row.get("ticker") != "CASH"
    ]
    held_tickers = [t for t in held_tickers if t]
    print(f"[setup] Holdings tickers: {held_tickers}")

    if not held_tickers:
        raise SystemExit("No holdings in local DB. Populate portfolio_holdings first.")

    technicals = await get_technicals(held_tickers)
    print(f"[setup] Technicals fetched for {len(technicals)} tickers")

    try:
        enrichment_data = await batch_fetch_enrichment(held_tickers, scan_date)
        print("[setup] Enrichment data loaded")
    except Exception as exc:
        print(f"[setup] Enrichment load failed ({exc!r}), using None")
        enrichment_data = None

    macro_metrics_dict = {"geopolitical_shock": None}
    market_level_dict = {"regime": "NEUTRAL", "breadth_score": 0.5}
    market_valuation = {}
    commodity_prices = {}

    briefings_value = format_ticker_briefings(
        tickers=held_tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices=commodity_prices,
        macro_metrics=macro_metrics_dict,
        geopolitical_shock=None,
        agent_key="positions_value",
    )
    briefings_thesis = format_ticker_briefings(
        tickers=held_tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices=commodity_prices,
        macro_metrics=macro_metrics_dict,
        geopolitical_shock=None,
        agent_key="positions_thesis",
    )

    portfolio_context = format_portfolio_block(holdings_list, 20_000_000, 20_000_000)
    regime_context = format_regime_block(
        market_level_dict, macro_metrics_dict, market_valuation=market_valuation
    )

    print(f"[setup] briefings_value bytes={len(briefings_value)}")
    print(f"[setup] briefings_thesis bytes={len(briefings_thesis)}")
    print(f"[setup] portfolio_context bytes={len(portfolio_context)}")
    print(f"[setup] regime_context bytes={len(regime_context)}")

    return {
        "scan_date": scan_date,
        "briefings_value": briefings_value,
        "briefings_thesis": briefings_thesis,
        "portfolio_context": portfolio_context,
        "regime_context": regime_context,
    }


async def run_trial(analyst_type: str, ctx: dict) -> tuple[float, str, int]:
    """One analyst run. Returns (wall_seconds, outcome, views_count)."""
    briefings_key = f"briefings_{analyst_type}"
    start = time.monotonic()
    try:
        report = await _run_analyst(
            analyst_type,
            scan_date=ctx["scan_date"],
            ticker_briefings=ctx[briefings_key],
            portfolio_context=ctx["portfolio_context"],
            regime_context=ctx["regime_context"],
        )
        wall = time.monotonic() - start
        summary = (report.summary or "")[:80]
        views = len(report.views or [])
        outcome = "SUCCESS" if views else f"EMPTY ({summary})"
        return wall, outcome, views
    except Exception as exc:
        wall = time.monotonic() - start
        traceback.print_exc()
        return wall, f"EXC {type(exc).__name__}: {exc!r}", 0


async def main(trials: int, serial: bool) -> None:
    ctx = await build_context()

    print(f"\n=== Running {trials} trial(s) | mode={'serial' if serial else 'parallel'} ===\n")
    results: list[tuple[str, int, float, str, int]] = []

    for i in range(trials):
        print(f"--- Trial {i + 1}/{trials} ---")
        if serial:
            for analyst in ("value", "thesis"):
                time.monotonic()
                wall, outcome, views = await run_trial(analyst, ctx)
                print(f"  [{analyst:7s}] wall={wall:6.1f}s views={views} outcome={outcome}")
                results.append((analyst, i + 1, wall, outcome, views))
        else:
            tasks = [run_trial(a, ctx) for a in ("value", "thesis")]
            gathered = await asyncio.gather(*tasks, return_exceptions=False)
            for analyst, (wall, outcome, views) in zip(("value", "thesis"), gathered, strict=False):
                print(f"  [{analyst:7s}] wall={wall:6.1f}s views={views} outcome={outcome}")
                results.append((analyst, i + 1, wall, outcome, views))
        print()

    print("=== Summary ===")
    for analyst in ("value", "thesis"):
        rows = [r for r in results if r[0] == analyst]
        walls = [r[2] for r in rows]
        empties = sum(1 for r in rows if r[4] == 0)
        successes = len(rows) - empties
        print(
            f"  [{analyst:7s}] trials={len(rows)} success={successes} empty={empties} "
            f"wall_min={min(walls):.1f}s wall_max={max(walls):.1f}s "
            f"wall_avg={sum(walls) / len(walls):.1f}s"
        )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=2)
    ap.add_argument(
        "--parallel", action="store_true", help="Run value+thesis in parallel (matches prod)"
    )
    args = ap.parse_args()
    asyncio.run(main(args.trials, serial=not args.parallel))
