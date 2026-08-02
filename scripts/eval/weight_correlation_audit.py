"""Phase A partial-data signal-strength audit (SWI-171, A.3).

Replays historical ``daily_recommendations`` × ``daily_evaluations``
joins to compute Spearman(feature_i, won) per scoring feature. **Output
is a LOWER BOUND on signal strength, NOT a fitted weight vector.**

Phase A's input distribution is selection-biased: only post-rejection
survivors land in ``daily_recommendations`` so the historical join can
only answer "which feature predicts win among picked tickers". The
unbiased question — "which feature picks well from the rejected pool" —
needs ``pre_gate_candidates`` data, which only starts populating after
this Phase A migration ships.

The proper fit happens in ``scripts/eval/backtest_scoring.py`` (Phase B
workstream), with regime-stratified holdout split + Spearman > 0.7
orthogonalisation step. This module is intentionally renamed from the
original ``backtest_scoring.py`` so future readers don't mistake its
output for a weight vector.

Usage:
    uv run python scripts/eval/weight_correlation_audit.py \\
        [--lookback-days 90] [--output report.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import statistics
import sys
from collections.abc import Sequence
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("weight_correlation_audit")

# Features queried from daily_recommendations. Only those persisted on
# the rec rows can be replayed against the won outcome — the rest
# (sim_*, belief_conviction, sector counts) wait for the
# pre_gate_candidates table to accumulate.
_AVAILABLE_FEATURES: tuple[str, ...] = (
    "risk_reward",
    "strategy_confidence",
    "sim_ev",
    "sim_p_target",
    "belief_conviction",
)


async def _async_main(lookback_days: int, output_path: str | None) -> int:
    sys.path.insert(0, "scripts")

    from shared.database import Database, close_db, fetch_all

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    async with Database():
        try:
            rows = await fetch_all(
                """
                SELECT r.risk_reward, r.strategy_confidence, r.sim_ev,
                       r.sim_p_target, r.belief_conviction, e.won
                FROM daily_recommendations r
                JOIN daily_records dr ON dr.id = r.record_id
                JOIN daily_evaluations e
                  ON e.record_id = r.record_id AND e.ticker = r.ticker
                WHERE dr.record_date BETWEEN $1 AND $2
                  AND r.action IN ('BUY', 'LIMIT_BUY')
                  AND e.won IS NOT NULL
                """,
                start_date,
                end_date,
            )
        finally:
            await close_db()

    n = len(rows)
    logger.info("loaded %d historical (rec, eval) pairs over %d days", n, lookback_days)

    if n < 10:
        logger.error(
            "Sample size %d below minimum 10 — Spearman estimates will be unstable. "
            "Wait for more data or extend --lookback-days.",
            n,
        )
        return 1

    won_outcomes: list[int] = [int(bool(row.get("won"))) for row in rows]
    win_rate = statistics.mean(won_outcomes) if won_outcomes else 0.0

    feature_correlations: dict[str, dict[str, float | int | str]] = {}
    for feature in _AVAILABLE_FEATURES:
        values: list[float] = []
        kept_outcomes: list[int] = []
        for row, outcome in zip(rows, won_outcomes, strict=True):
            raw = row.get(feature)
            if raw is None:
                continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue
            kept_outcomes.append(outcome)
        if len(values) < 5:
            feature_correlations[feature] = {
                "n": len(values),
                "spearman": 0.0,
                "note": "insufficient_samples",
            }
            continue
        rho = _spearman(values, [float(o) for o in kept_outcomes])
        feature_correlations[feature] = {
            "n": len(values),
            "spearman": round(rho, 4),
        }

    report = {
        "lookback_days": lookback_days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "n_rec_eval_pairs": n,
        "win_rate": round(win_rate, 4),
        "feature_signal_lower_bound": feature_correlations,
        "warnings": [
            "Output is a LOWER BOUND on signal strength — selection-biased.",
            "Phase A data covers post-rejection survivors only.",
            "Real weight fit awaits pre_gate_candidates accumulation (Phase B).",
        ],
    }

    formatted = json.dumps(report, indent=2)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(formatted)
        logger.info("report written to %s", output_path)
    else:
        sys.stdout.write(formatted + "\n")
    return 0


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Spearman rank correlation. Returns 0 when the inputs are degenerate."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    rank_x = _rank(xs)
    rank_y = _rank(ys)
    mean_x = statistics.mean(rank_x)
    mean_y = statistics.mean(rank_y)
    num = sum((rx - mean_x) * (ry - mean_y) for rx, ry in zip(rank_x, rank_y, strict=True))
    den_x = math.sqrt(sum((rx - mean_x) ** 2 for rx in rank_x))
    den_y = math.sqrt(sum((ry - mean_y) ** 2 for ry in rank_y))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def _rank(values: Sequence[float]) -> list[float]:
    """Average-rank assignment for ties."""
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        average_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = average_rank
        i = j + 1
    return ranks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase A signal-strength lower-bound audit (NOT a weight fit)"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=90,
        help="Days of history to query (default 90)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional file path for the JSON report",
    )
    args = parser.parse_args()
    return asyncio.run(_async_main(args.lookback_days, args.output))


if __name__ == "__main__":
    sys.exit(main())
