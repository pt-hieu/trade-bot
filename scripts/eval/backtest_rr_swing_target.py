"""Recompute R:R with post-SWI-289 swing target derivation + backtest 29 candidates.

For each (scan_date, ticker) row in pre_gate_candidates 5/4–5/8:
1. Recompute target = nearest local-pivot-high above close-on-scan-date in last 60 bars
   (mirrors find_nearest_levels.nearest_swing_target after SWI-289 — structural high,
   no MA-inclusive fallback).
2. Recompute stop = nearest local-pivot-low below close-on-scan-date.
3. Recompute R:R = (target - close) / (close - stop) and renormalize via
   shared.rules.scoring.normalizers._normalize_risk_reward (sqrt(rr/10)).
4. Backtest: for next N trading days after scan_date, compute MFE (max high vs close)
   and MAE (min low vs close). Classify hit at +3%, +5%, +10% targets vs -3%, -5% stops.
5. Tabulate: would entries at thresholds 30/40/50 have profited?
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

# JSON dump of daily bars keyed by ticker: {"FPT": {"data": [{date, open, high, low, close}, ...]}}
# Produce one with the `get_prices` MCP tool, or any equivalent OHLC export.
PRICES_FILE = Path(os.environ.get("BACKTEST_PRICES_FILE", "data/backtest_prices.json"))

# 29 audited candidates: (scan_date, ticker, original_score, original_feature_rr)
# from earlier audit query
CANDIDATES = [
    ("2026-05-08", "VHM", 43.35, 0.0663),
    ("2026-05-08", "SAB", 37.62, 1.1923),
    ("2026-05-08", "VPB", 35.89, 0.8979),
    ("2026-05-08", "HDB", 34.85, 0.3046),
    ("2026-05-08", "POW", 34.73, 0.2627),
    ("2026-05-08", "HCM", 33.59, 0.4239),
    ("2026-05-07", "VHM", 39.38, 0.1612),
    ("2026-05-07", "POW", 36.80, 0.2089),
    ("2026-05-07", "VPB", 35.72, 0.9551),
    ("2026-05-07", "SAB", 34.99, 1.0225),
    ("2026-05-07", "HCM", 32.34, 0.0861),
    ("2026-05-07", "HDB", 32.30, 0.2320),
    ("2026-05-06", "VHM", 25.18, 0.1833),
    ("2026-05-06", "VCB", 23.86, 1.2725),
    ("2026-05-06", "SAB", 21.73, 1.3171),
    ("2026-05-06", "GVR", 19.81, 0.5770),
    ("2026-05-06", "VPB", 19.19, 0.5546),
    ("2026-05-06", "POW", 18.58, 0.1790),
    ("2026-05-06", "HCM", 17.99, 0.1511),
    ("2026-05-06", "HDB", 17.02, 0.2320),
    ("2026-05-05", "SAB", 24.45, 0.0000),
    ("2026-05-05", "VCB", 23.38, 0.9848),
    ("2026-05-05", "GVR", 21.17, 0.1474),
    ("2026-05-05", "VHM", 20.35, 0.3370),
    ("2026-05-05", "GAS", 18.80, 0.3345),
    ("2026-05-05", "VPB", 17.53, 0.0427),
    ("2026-05-05", "HDB", 17.42, 0.2694),
    ("2026-05-05", "HCM", 17.04, 0.3173),
    ("2026-05-05", "VRE", 16.20, 0.0740),
]


def load_prices() -> dict[str, list[dict]]:
    if not PRICES_FILE.exists():
        raise FileNotFoundError(
            f"Price export not found at {PRICES_FILE}. "
            "Set BACKTEST_PRICES_FILE to a JSON OHLC dump keyed by ticker."
        )
    raw = json.loads(PRICES_FILE.read_text())
    payload = json.loads(raw[0]["text"]) if isinstance(raw, list) else raw
    return {k: v["data"] for k, v in payload.items() if isinstance(v, dict) and "data" in v}


def find_pivot_high(bars: list[dict], end_idx: int, lookback: int = 60, k: int = 3) -> float | None:
    """Find nearest pivot high above close-at-end_idx within lookback bars.

    A pivot high at i is high[i] strictly greater than k bars on both sides.
    Return the nearest pivot high ABOVE close[end_idx] looking back from end_idx-1.
    """
    if end_idx < 2 * k + 1:
        return None
    close = bars[end_idx]["close"]
    start = max(k, end_idx - lookback)
    candidates = []
    for i in range(end_idx - 1, start - 1, -1):
        if i - k < 0 or i + k >= len(bars):
            continue
        h = bars[i]["high"]
        is_pivot = all(h > bars[i - j]["high"] for j in range(1, k + 1)) and all(
            h > bars[i + j]["high"] for j in range(1, k + 1)
        )
        if is_pivot and h > close * 1.005:
            candidates.append((i, h))
    if not candidates:
        return None
    # Closest above price → smallest h
    candidates.sort(key=lambda x: x[1])
    return candidates[0][1]


def find_pivot_low(bars: list[dict], end_idx: int, lookback: int = 60, k: int = 3) -> float | None:
    if end_idx < 2 * k + 1:
        return None
    close = bars[end_idx]["close"]
    start = max(k, end_idx - lookback)
    candidates = []
    for i in range(end_idx - 1, start - 1, -1):
        if i - k < 0 or i + k >= len(bars):
            continue
        low = bars[i]["low"]
        is_pivot = all(low < bars[i - j]["low"] for j in range(1, k + 1)) and all(
            low < bars[i + j]["low"] for j in range(1, k + 1)
        )
        if is_pivot and low < close * 0.995:
            candidates.append((i, low))
    if not candidates:
        return None
    # Closest below price → largest low
    candidates.sort(key=lambda x: -x[1])
    return candidates[0][1]


def normalize_rr(rr: float) -> float:
    if rr is None or rr <= 0:
        return 0.0
    return min(1.0, max(0.0, math.sqrt(rr / 10.0)))


def find_idx_for_date(bars: list[dict], date: str) -> int | None:
    for i, b in enumerate(bars):
        if b["time"][:10] == date:
            return i
    return None


def backtest_outcome(bars: list[dict], entry_idx: int, n_days: int = 5) -> dict:
    if entry_idx + 1 >= len(bars):
        return {"available_days": 0, "mfe_pct": None, "mae_pct": None}
    entry_close = bars[entry_idx]["close"]
    end = min(entry_idx + 1 + n_days, len(bars))
    forward = bars[entry_idx + 1 : end]
    if not forward:
        return {"available_days": 0, "mfe_pct": None, "mae_pct": None}
    max_high = max(b["high"] for b in forward)
    min_low = min(b["low"] for b in forward)
    return {
        "available_days": len(forward),
        "mfe_pct": (max_high - entry_close) / entry_close * 100,
        "mae_pct": (min_low - entry_close) / entry_close * 100,
        "next_close": forward[-1]["close"],
        "ret_pct": (forward[-1]["close"] - entry_close) / entry_close * 100,
    }


def main() -> int:
    prices = load_prices()
    print(f"loaded prices for: {sorted(prices.keys())}")
    print(
        f"\n{'date':>10} {'tic':>4} {'orig_s':>7} {'orig_rr':>8} "
        f"{'close':>8} {'tgt':>8} {'stop':>8} {'rr_new':>7} {'rr_pts_new':>10} "
        f"{'days':>4} {'MFE%':>7} {'MAE%':>7} {'ret%':>7}"
    )
    print("-" * 130)

    rows = []
    for scan_date, ticker, orig_score, orig_rr_norm in CANDIDATES:
        bars = prices.get(ticker, [])
        idx = find_idx_for_date(bars, scan_date)
        if idx is None:
            print(f"{scan_date:>10} {ticker:>4}  no bar for date")
            continue
        close = bars[idx]["close"]
        target = find_pivot_high(bars, idx)
        stop = find_pivot_low(bars, idx)

        rr_raw = None
        rr_norm = 0.0
        if target is not None and stop is not None and close > stop:
            risk = close - stop
            reward = target - close
            rr_raw = reward / risk if risk > 0 else 0.0
            rr_norm = normalize_rr(rr_raw)

        # Original score had risk_reward at weight 0.20 → 20pt max contribution.
        # Original feature_rr was the normalized [0,1] value already; orig contribution = 100 * 0.20 * orig_rr_norm.
        # New contribution: 100 * 0.20 * rr_norm.
        rr_pts_new = 100 * 0.20 * rr_norm

        bt = backtest_outcome(bars, idx, n_days=5)

        delta_pts = rr_pts_new - 100 * 0.20 * orig_rr_norm
        new_score_est = orig_score + delta_pts

        rows.append(
            {
                "scan_date": scan_date,
                "ticker": ticker,
                "orig_score": orig_score,
                "orig_rr_norm": orig_rr_norm,
                "close": close,
                "target": target,
                "stop": stop,
                "rr_raw": rr_raw,
                "rr_norm": rr_norm,
                "rr_pts_new": rr_pts_new,
                "delta_pts": delta_pts,
                "new_score_est": new_score_est,
                **bt,
            }
        )

        print(
            f"{scan_date:>10} {ticker:>4} {orig_score:>7.2f} {orig_rr_norm:>8.4f} "
            f"{close:>8} {target if target else '-':>8} {stop if stop else '-':>8} "
            f"{rr_raw if rr_raw else 0:>7.2f} {rr_pts_new:>10.2f} "
            f"{bt['available_days']:>4} "
            f"{bt['mfe_pct'] if bt['mfe_pct'] is not None else 0:>7.2f} "
            f"{bt['mae_pct'] if bt['mae_pct'] is not None else 0:>7.2f} "
            f"{bt['ret_pct'] if bt.get('ret_pct') is not None else 0:>7.2f}"
        )

    # Aggregate analysis
    print("\n=== R:R recompute summary ===")
    delta_pts_list = [r["delta_pts"] for r in rows]
    new_scores = [r["new_score_est"] for r in rows]
    print(
        f"n={len(rows)}  mean Δpts from rr-recompute: {sum(delta_pts_list) / len(delta_pts_list):+.2f}  "
        f"max Δ: {max(delta_pts_list):+.2f}  min Δ: {min(delta_pts_list):+.2f}"
    )
    print(
        f"orig score range: {min(r['orig_score'] for r in rows):.2f} – {max(r['orig_score'] for r in rows):.2f}"
    )
    print(f"new  score range: {min(new_scores):.2f} – {max(new_scores):.2f}")
    print(f"new mean: {sum(new_scores) / len(new_scores):.2f}")

    print("\n=== Backtest profitability ===")
    valid = [r for r in rows if r.get("available_days", 0) >= 1]
    print(f"backtest-evaluable rows: {len(valid)}/{len(rows)}")
    for tgt_pct, stop_pct in [(3, 3), (5, 3), (5, 5), (10, 5)]:
        wins = sum(1 for r in valid if r["mfe_pct"] >= tgt_pct and r["mae_pct"] > -stop_pct)
        losses = sum(1 for r in valid if r["mae_pct"] <= -stop_pct and r["mfe_pct"] < tgt_pct)
        flat = len(valid) - wins - losses
        print(
            f"  target +{tgt_pct}% / stop -{stop_pct}%:  WIN={wins}  LOSS={losses}  FLAT={flat}  "
            f"hit_rate={wins / len(valid) * 100 if valid else 0:.0f}%"
        )

    print("\n=== Threshold cutoffs (using NEW estimated scores) ===")
    for thresh in [30, 35, 40, 50, 60]:
        admitted = [r for r in rows if r["new_score_est"] >= thresh]
        admitted_bt = [r for r in admitted if r.get("available_days", 0) >= 1]
        avg_mfe = sum(r["mfe_pct"] for r in admitted_bt) / len(admitted_bt) if admitted_bt else 0
        avg_mae = sum(r["mae_pct"] for r in admitted_bt) / len(admitted_bt) if admitted_bt else 0
        avg_ret = sum(r["ret_pct"] for r in admitted_bt if r.get("ret_pct") is not None) / max(
            1, len(admitted_bt)
        )
        print(
            f"  thresh={thresh}: admits {len(admitted)}/29  "
            f"avg MFE: {avg_mfe:+.2f}%  avg MAE: {avg_mae:+.2f}%  avg ret: {avg_ret:+.2f}%"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
