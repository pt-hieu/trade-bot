#!/usr/bin/env python3
"""Ad-hoc ticker scorer.

This script SCORES tickers. It does NOT fit weights and is NOT a backtest.
Two modes: ``replay`` reads historical ``pre_gate_candidates`` rows and
rescores them under current (or hypothetical) weights. ``fresh`` fetches
live technicals/flow and scores once, without running the full pipeline.

Replay mode is READ-ONLY against ``pre_gate_candidates``. Hypothetical-
weights output rows are tagged ``[HYPOTHETICAL]``; the script never writes
to the audit table.

Purity invariant: orchestration lives here, in ``scripts/eval/``. The
scoring module (``scripts/shared/rules/scoring/``) stays pure-Python per
the ``check_no_async_in_scoring.py`` pre-commit guard.

Usage::

    uv run python scripts/eval/score_tickers.py \\
        --mode {replay,fresh} \\
        --tickers VHM,VIC,FPT \\
        [--scan-date YYYY-MM-DD] \\
        [--weights-file path.yaml]      # replay only
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("score_tickers")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ad-hoc ticker scorer (replay / fresh)")
    parser.add_argument("--mode", choices=("replay", "fresh"), required=True)
    parser.add_argument(
        "--tickers",
        required=True,
        help="Comma-separated ticker list, e.g. VHM,VIC,FPT",
    )
    parser.add_argument(
        "--scan-date",
        type=date.fromisoformat,
        default=date.today(),
        help="ISO-format date (default: today)",
    )
    parser.add_argument(
        "--weights-file",
        type=Path,
        default=None,
        help="Replay mode only — full alternate scoring.yaml (12 keys, Σw=1)",
    )
    parser.add_argument(
        "--recompute-rr",
        action="store_true",
        help=(
            "Replay mode only — refetch historical OHLC up to scan_date and "
            "rebuild target/stop/R:R using current setup_calc + find_nearest_levels "
            "(SWI-289 / SWI-307). The recomputed risk_reward replaces "
            "feature_risk_reward before scoring. Tag in output: [RR-RECOMPUTED]."
        ),
    )
    return parser.parse_args()


def _format_row(
    ticker: str,
    original: float | None,
    new: float,
    base: float,
    regime_pen: float,
    shock_pen: float,
    top_contributors: str,
    gated_by: str,
    is_hypothetical: bool,
) -> str:
    delta = "" if original is None else f"{new - original:+.1f}"
    orig_text = "-" if original is None else f"{original:.1f}"
    tag = " [HYPOTHETICAL]" if is_hypothetical else ""
    return (
        f"{ticker:<6}  {orig_text:<9}  {new:<8.1f}  {delta:<5}  "
        f"{base:<5.1f}  {regime_pen:<+6.1f}  {shock_pen:<+6.1f}  "
        f"{top_contributors:<43}  {gated_by}{tag}"
    )


def _top_contributors(breakdown: dict[str, float], n: int = 3) -> str:
    items = [
        (key, value)
        for key, value in breakdown.items()
        if key not in ("regime_penalty", "shock_penalty") and value > 0
    ]
    items.sort(key=lambda pair: pair[1], reverse=True)
    return " ".join(f"{key}({value:.3f})" for key, value in items[:n])


def _print_header(mode: str, scan_date: date, hypothetical_path: Path | None) -> None:
    suffix = (
        f"  [HYPOTHETICAL — weights from {hypothetical_path.name}]"
        if hypothetical_path is not None
        else ""
    )
    print(f"Mode: {mode}  Scan date: {scan_date}{suffix}\n")
    print(
        f"{'Ticker':<6}  {'ScoreOrig':<9}  {'ScoreNew':<8}  {'Δ':<5}  "
        f"{'Base':<5}  {'RegPen':<6}  {'ShkPen':<6}  "
        f"{'Top contributors':<43}  Gated by"
    )
    print("-" * 130)


async def _recompute_rr_for_candidates(
    candidate_rows: list[dict[str, object]],
) -> dict[tuple[date, str], float | None]:
    """For each (scan_date, ticker), refetch OHLC up to scan_date, rebuild
    levels, and rerun ``compute_setup_from_levels`` to derive a new
    risk_reward. Returns mapping with ``None`` when the setup is invalid.
    """
    import pandas as pd

    from agents.tools.technicals.setup_calc import compute_setup_from_levels
    from data.technicals.levels import (
        calculate_range_levels,
        detect_swing_points,
        find_nearest_levels,
    )
    from shared.api.prices import get_ohlc_series

    # One HTTP call per (scan_date) — bucket tickers by date for batch fetch.
    by_date: dict[date, list[str]] = {}
    regime_by_key: dict[tuple[date, str], str] = {}
    for row in candidate_rows:
        scan_date_raw = row.get("scan_date")
        scan_date_value = (
            scan_date_raw
            if isinstance(scan_date_raw, date)
            else date.fromisoformat(str(scan_date_raw)[:10])
        )
        ticker_value = str(row.get("ticker") or "").upper()
        if not ticker_value:
            continue
        by_date.setdefault(scan_date_value, []).append(ticker_value)
        regime_by_key[(scan_date_value, ticker_value)] = str(
            row.get("regime") or "CAUTIOUS"
        ).upper()

    out: dict[tuple[date, str], float | None] = {}
    for scan_day, tickers_for_day in by_date.items():
        # 60 calendar-day window is enough for 20-day range + swing detection.
        from datetime import timedelta

        series = await get_ohlc_series(
            tickers_for_day,
            start=(scan_day - timedelta(days=60)).isoformat(),
            end=scan_day.isoformat(),
        )
        for ticker in tickers_for_day:
            bars = series.get(ticker) or []
            if len(bars) < 21:
                logger.warning(
                    "%s @ %s: only %d bars, skipping RR recompute",
                    ticker,
                    scan_day,
                    len(bars),
                )
                out[(scan_day, ticker)] = None
                continue
            frame = pd.DataFrame(bars)
            frame["time"] = pd.to_datetime(frame["date"])
            close = float(frame.iloc[-1]["close"])
            swings = detect_swing_points(frame)
            ranges = calculate_range_levels(frame)
            levels: dict[str, float | str] = {**swings, **ranges}
            nearest = find_nearest_levels(
                price=close,
                ma20=None,
                ma50=None,
                swing_high=swings.get("swing_high"),
                swing_low=swings.get("swing_low"),
                range_high=ranges.get("range_20d_high"),
                range_low=ranges.get("range_20d_low"),
            )
            levels.update(nearest)
            setup = compute_setup_from_levels(
                levels=levels,
                close=close,
                ticker=ticker,
                structural_uptrend=False,
                atr=None,
                risk_regime=regime_by_key[(scan_day, ticker)],
            )
            if not setup.get("valid"):
                out[(scan_day, ticker)] = None
                continue
            risk_reward = setup.get("risk_reward")
            out[(scan_day, ticker)] = float(risk_reward) if risk_reward is not None else None
    return out


async def _replay(
    tickers: list[str],
    scan_date: date,
    weights_file: Path | None,
    recompute_rr: bool = False,
) -> int:
    from shared.database import Database, close_db, fetch_all
    from shared.rules.scoring import compute_score, load_scoring_config

    is_hypothetical = weights_file is not None
    config = load_scoring_config(path=weights_file) if weights_file else load_scoring_config()

    async with Database():
        try:
            rows = await fetch_all(
                """
                SELECT scan_date, ticker, score AS original_score, gated_by, regime,
                       feature_risk_reward, feature_sim_p_target, feature_sim_p_stop,
                       feature_sim_ev, feature_strategy_confidence,
                       feature_belief_conviction, feature_catalyst_strength,
                       feature_bullish_belief_count, feature_total_sector_count,
                       feature_rs_20d, feature_volume_vs_avg, feature_trend_alignment,
                       feature_foreign_net_strength,
                       shock_penalty, breakdown
                FROM pre_gate_candidates
                WHERE scan_date = $1
                  AND ticker = ANY($2)
                  AND phase = 'morning'
                ORDER BY ticker
                """,
                scan_date,
                tickers,
            )
        finally:
            await close_db()

    if not rows:
        logger.error(
            "No pre_gate_candidates rows for scan_date=%s tickers=%s phase=morning",
            scan_date,
            tickers,
        )
        return 1

    row_dicts = [dict(row) for row in rows]
    recomputed_rr: dict[tuple[date, str], float | None] = {}
    if recompute_rr:
        from shared.database import Database, close_db
        from shared.trading_config import init_trading_config

        async with Database():
            try:
                await init_trading_config()
                recomputed_rr = await _recompute_rr_for_candidates(row_dicts)
            finally:
                await close_db()

    _print_header("replay", scan_date, weights_file)

    for row_dict in row_dicts:
        features = _reconstruct_score_inputs(row_dict)
        if recompute_rr:
            key = (row_dict.get("scan_date"), str(row_dict.get("ticker")))
            new_rr = recomputed_rr.get(key)  # type: ignore[arg-type]
            features["risk_reward"] = float(new_rr) if new_rr is not None else 0.0
        shock_active = float(row_dict.get("shock_penalty") or 0) > 0
        sim_populated = _sim_populated_from_breakdown(row_dict.get("breakdown"))
        result = compute_score(
            features=features,  # type: ignore[arg-type]
            regime=str(row_dict.get("regime") or "CAUTIOUS").upper(),
            relief_context=None,
            shock_active=shock_active,
            config=config,
            sim_populated=sim_populated,
        )
        original_raw = row_dict.get("original_score")
        print(
            _format_row(
                ticker=str(row_dict.get("ticker")),
                original=float(original_raw) if original_raw is not None else None,
                new=result.score,
                base=result.base_score,
                regime_pen=-result.regime_penalty,
                shock_pen=-result.shock_penalty,
                top_contributors=_top_contributors(result.breakdown),
                gated_by=str(row_dict.get("gated_by") or "-"),
                is_hypothetical=is_hypothetical,
            )
        )
    return 0


def _reconstruct_score_inputs(row: dict[str, object]) -> dict[str, object]:
    """Pack ``feature_*`` audit columns back into a ScoreInputs-shaped dict.

    Silently drops ``feature_order_imbalance`` — not in v2.1.0 _FEATURE_KEYS.
    """
    inputs: dict[str, object] = {}
    mapping = {
        "risk_reward": "feature_risk_reward",
        "sim_p_target": "feature_sim_p_target",
        "sim_p_stop": "feature_sim_p_stop",
        "sim_ev": "feature_sim_ev",
        "strategy_confidence": "feature_strategy_confidence",
        "belief_conviction": "feature_belief_conviction",
        "catalyst_strength": "feature_catalyst_strength",
        "rs_20d": "feature_rs_20d",
        "volume_vs_avg": "feature_volume_vs_avg",
        "foreign_net_strength": "feature_foreign_net_strength",
    }
    for key, column in mapping.items():
        value = row.get(column)
        if value is not None:
            inputs[key] = float(value)  # type: ignore[arg-type]
    bullish = row.get("feature_bullish_belief_count")
    total = row.get("feature_total_sector_count")
    if bullish is not None:
        inputs["bullish_sector_belief_count"] = int(bullish)  # type: ignore[arg-type]
    if total is not None:
        inputs["total_sector_count"] = int(total)  # type: ignore[arg-type]
    trend = row.get("feature_trend_alignment")
    if trend is not None:
        inputs["trend_alignment"] = str(trend)
    return inputs


def _sim_populated_from_breakdown(breakdown_jsonb: object) -> bool:
    from shared.neon._utils import parse_jsonb_object

    parsed = parse_jsonb_object(breakdown_jsonb)
    if parsed is None:
        return True
    value = parsed.get("sim_populated")
    if isinstance(value, bool):
        return value
    return True


async def _fresh(tickers: list[str], scan_date: date) -> int:
    """Score tickers from live technicals + flow, no full pipeline.

    Best-effort: uses neutral defaults for signals not easily fetched
    outside the orchestrated pipeline (strategy_confidence, simulation,
    belief_conviction, catalyst_strength).
    """
    from agents.picks_audit import build_score_inputs
    from agents.tools.technicals import get_batch_ticker_data_async
    from shared.api.enrichment import get_daily_flow_batch
    from shared.database import Database, close_db
    from shared.rules.scoring import compute_score, load_scoring_config
    from shared.trading_config import init_trading_config

    config = load_scoring_config()

    # setup_calc needs trading_config (max_risk_per_trade, transaction_cost_pct).
    async with Database():
        try:
            await init_trading_config()
            tech_data, flow_by_ticker = await asyncio.gather(
                get_batch_ticker_data_async(tickers, scan_date),
                get_daily_flow_batch(tickers, scan_date),
            )
        finally:
            await close_db()

    for ticker, flow in (flow_by_ticker or {}).items():
        entry = (tech_data or {}).get(ticker)
        if entry is None or "error" in entry:
            continue
        entry["flow"] = flow or {}

    _print_header("fresh", scan_date, None)
    for ticker in tickers:
        entry = (tech_data or {}).get(ticker) or {}
        if "error" in entry:
            logger.warning("%s: tech_data error — %s", ticker, entry.get("error"))
            continue
        setup = entry.get("trade_setup") or {}
        inputs = build_score_inputs(
            signal={"ticker": ticker, "confidence": "medium"},
            tech_data=entry,
            setup=setup,
            bullish_sector_belief_count=0,
            total_sector_count=10,
        )
        result = compute_score(
            features=inputs,
            regime="CAUTIOUS",
            relief_context=None,
            shock_active=False,
            config=config,
            sim_populated=False,
        )
        print(
            _format_row(
                ticker=ticker,
                original=None,
                new=result.score,
                base=result.base_score,
                regime_pen=-result.regime_penalty,
                shock_pen=-result.shock_penalty,
                top_contributors=_top_contributors(result.breakdown),
                gated_by="-",
                is_hypothetical=False,
            )
        )
    return 0


async def _main_async(args: argparse.Namespace) -> int:
    sys.path.insert(0, "scripts")
    from shared.env import load_env

    load_env()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    if not tickers:
        logger.error("--tickers must contain at least one ticker")
        return 2
    if args.mode == "replay":
        return await _replay(
            tickers, args.scan_date, args.weights_file, recompute_rr=args.recompute_rr
        )
    if args.weights_file is not None:
        logger.error("--weights-file is only valid in --mode replay")
        return 2
    if args.recompute_rr:
        logger.error("--recompute-rr is only valid in --mode replay")
        return 2
    return await _fresh(tickers, args.scan_date)


def main() -> int:
    sys.path.insert(0, "scripts")
    args = _parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
