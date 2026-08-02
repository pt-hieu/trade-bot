#!/usr/bin/env python3
"""Per-feature correlation audit for the deterministic scorer.

Computes Spearman rho between each feature's point contribution
(``breakdown.breakdown.<feature>``) and forward returns at
+1d/+3d/+5d trading-day horizons over a 30-day window of
``pre_gate_candidates`` (phase=morning).

Outputs:
  - tmp/feature_correlation_audit.md (full tables + commentary)
  - stdout: headline table + plain-English summary

Read-only. Extends ``backtest_scoring_week.py`` patterns.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from statistics import mean
from typing import Any

WINDOW_START = date(2026, 4, 17)
WINDOW_END = date(2026, 5, 16)
HORIZONS = [1, 3, 5]
OUT_PATH = "tmp/feature_correlation_audit.md"

FEATURES = [
    "risk_reward",
    "sim_ev",
    "sim_p_target",
    "sim_p_stop",
    "bullish_sector_belief_count",
    "belief_conviction",
    "catalyst_strength",
    "trend_alignment",
    "strategy_confidence",
    "rs_20d",
    "volume_vs_avg",
    "foreign_net_strength",
    "order_imbalance",  # legacy, may be zero in v2.2.0
]


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
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
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks

    rx = average_ranks(xs)
    ry = average_ranks(ys)
    mx, my = mean(rx), mean(ry)
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((v - mx) ** 2 for v in rx) ** 0.5
    dy = sum((v - my) ** 2 for v in ry) ** 0.5
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


async def fetch_candidates() -> list[dict[str, Any]]:
    from shared.database import Database, close_db, fetch_all

    async with Database():
        try:
            rows = await fetch_all(
                """
                SELECT scan_date, ticker, score::float8 AS score,
                       gated_by, regime, breakdown
                FROM pre_gate_candidates
                WHERE scan_date BETWEEN $1 AND $2
                  AND phase = 'morning'
                ORDER BY scan_date, ticker
                """,
                WINDOW_START,
                WINDOW_END,
            )
        finally:
            await close_db()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        bk = d.get("breakdown") or {}
        if isinstance(bk, str):
            bk = json.loads(bk)
        d["breakdown"] = bk
        out.append(d)
    return out


async def fetch_close_history(
    tickers: list[str], start: date, end: date
) -> dict[str, dict[date, float]]:
    from shared.api.prices import get_ohlc_series

    series = await get_ohlc_series(tickers, start=start.isoformat(), end=end.isoformat())
    closes: dict[str, dict[date, float]] = {}
    for ticker, bars in (series or {}).items():
        per: dict[date, float] = {}
        for bar in bars or []:
            ds = bar.get("date")
            cl = bar.get("close")
            if not ds or cl is None:
                continue
            per[date.fromisoformat(str(ds)[:10])] = float(cl)
        if per:
            closes[ticker] = per
    return closes


def forward_return(
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
    fwd = closes.get(trading_days[idx + horizon])
    if base is None or fwd is None or base == 0:
        return None
    return (fwd - base) / base * 100


def verdict(rho: float, n: int) -> str:
    if n < 10 or rho != rho:  # NaN
        return "insufficient"
    a = abs(rho)
    if a < 0.10:
        return "noise"
    if rho < 0:
        return "INVERTED"
    return "carries signal"


def tercile_spread(
    contribs: list[float], rets: list[float]
) -> tuple[float, float, float, int, int] | None:
    pairs = sorted(zip(contribs, rets, strict=True), key=lambda p: p[0])
    n = len(pairs)
    if n < 6:
        return None
    k = n // 3
    bottom = pairs[:k]
    top = pairs[-k:]
    bot_avg = mean(p[1] for p in bottom)
    top_avg = mean(p[1] for p in top)
    return bot_avg, top_avg, top_avg - bot_avg, len(bottom), len(top)


async def main_async() -> int:
    sys.path.insert(0, "scripts")

    candidates = await fetch_candidates()
    if not candidates:
        print("FATAL: no pre_gate_candidates in window")
        return 1
    if len(candidates) < 50:
        print(f"WARNING: only {len(candidates)} rows in window — small sample")

    tickers = sorted({str(r["ticker"]) for r in candidates})
    # fetch through today so forward windows resolve
    closes = await fetch_close_history(tickers, WINDOW_START, date.today())
    union_days = sorted({d for c in closes.values() for d in c})

    # Build enriched rows
    enriched = []
    for c in candidates:
        ticker = str(c["ticker"])
        scan = c["scan_date"]
        ck = closes.get(ticker, {})
        rets = {h: forward_return(ck, union_days, scan, h) for h in HORIZONS}
        bk = c["breakdown"] or {}
        inner = bk.get("breakdown") or {}
        version = bk.get("scoring_version") or "unknown"
        enriched.append(
            {
                "scan_date": scan,
                "ticker": ticker,
                "score": float(c["score"]),
                "gated_by": c.get("gated_by") or "unknown",
                "version": version,
                "rets": rets,
                "contribs": {f: float(inner.get(f) or 0.0) for f in FEATURES},
            }
        )

    # Version distribution
    version_counts: dict[str, int] = defaultdict(int)
    for r in enriched:
        version_counts[r["version"]] += 1

    # Gate distribution
    gate_counts: dict[str, int] = defaultdict(int)
    for r in enriched:
        gate_counts[r["gated_by"]] += 1

    # Per-feature analysis
    def per_feature_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for feat in FEATURES:
            row_stats: dict[str, Any] = {"feature": feat}
            # coverage (nonzero contribution among ALL rows in `rows`)
            nonzero_rows = [r for r in rows if abs(r["contribs"][feat]) > 1e-9]
            row_stats["n_total"] = len(rows)
            row_stats["n_nonzero"] = len(nonzero_rows)
            row_stats["coverage_pct"] = 100.0 * len(nonzero_rows) / len(rows) if rows else 0.0
            row_stats["mean_contrib"] = (
                mean(r["contribs"][feat] for r in nonzero_rows) if nonzero_rows else 0.0
            )
            for h in HORIZONS:
                pairs = [
                    (r["contribs"][feat], r["rets"][h])
                    for r in nonzero_rows
                    if r["rets"][h] is not None
                ]
                if pairs:
                    xs = [p[0] for p in pairs]
                    ys = [p[1] for p in pairs]
                    rho = spearman(xs, ys)
                    row_stats[f"rho_{h}d"] = rho
                    row_stats[f"n_{h}d"] = len(pairs)
                else:
                    row_stats[f"rho_{h}d"] = float("nan")
                    row_stats[f"n_{h}d"] = 0
            # Tercile spread at +1d
            pairs1 = [
                (r["contribs"][feat], r["rets"][1])
                for r in nonzero_rows
                if r["rets"][1] is not None
            ]
            ts = tercile_spread([p[0] for p in pairs1], [p[1] for p in pairs1])
            if ts is not None:
                bot, top, spread, nbot, ntop = ts
                row_stats["tercile_bot_avg"] = bot
                row_stats["tercile_top_avg"] = top
                row_stats["tercile_spread"] = spread
                row_stats["tercile_n_each"] = ntop
            else:
                row_stats["tercile_bot_avg"] = float("nan")
                row_stats["tercile_top_avg"] = float("nan")
                row_stats["tercile_spread"] = float("nan")
                row_stats["tercile_n_each"] = 0
            # verdict using +1d
            row_stats["verdict_1d"] = verdict(row_stats["rho_1d"], row_stats["n_1d"])
            out.append(row_stats)
        return out

    all_stats = per_feature_table(enriched)
    passed_rows = [r for r in enriched if r["gated_by"] == "passed"]
    passed_stats = per_feature_table(passed_rows) if passed_rows else []

    # Catalyst lead vs chase: among rows where catalyst_strength > 0,
    # rho(catalyst contribution, forward return)
    cat_rows = [r for r in enriched if r["contribs"]["catalyst_strength"] > 1e-9]
    catalyst_findings: dict[str, Any] = {"n_rows": len(cat_rows)}
    for h in HORIZONS:
        pairs = [
            (r["contribs"]["catalyst_strength"], r["rets"][h])
            for r in cat_rows
            if r["rets"][h] is not None
        ]
        if pairs:
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            catalyst_findings[f"rho_{h}d"] = spearman(xs, ys)
            catalyst_findings[f"n_{h}d"] = len(pairs)
            catalyst_findings[f"mean_fwd_{h}d"] = mean(ys)
        else:
            catalyst_findings[f"rho_{h}d"] = float("nan")
            catalyst_findings[f"n_{h}d"] = 0
            catalyst_findings[f"mean_fwd_{h}d"] = float("nan")

    # Total score sanity check vs forward returns
    score_pairs = {
        h: [(r["score"], r["rets"][h]) for r in enriched if r["rets"][h] is not None]
        for h in HORIZONS
    }
    score_rhos = {
        h: spearman([p[0] for p in v], [p[1] for p in v]) if v else float("nan")
        for h, v in score_pairs.items()
    }

    # Write report
    lines: list[str] = []
    lines.append("# Feature Correlation Audit — pre_gate_candidates")
    lines.append("")
    lines.append(
        f"Window: {WINDOW_START} .. {WINDOW_END}  phase=morning  "
        f"N_rows={len(enriched)}  N_tickers={len(tickers)}"
    )
    lines.append("")
    lines.append(
        "Scoring version distribution: "
        + ", ".join(f"{v}={n}" for v, n in sorted(version_counts.items()))
    )
    lines.append(
        "Gate distribution: "
        + ", ".join(f"{g}={n}" for g, n in sorted(gate_counts.items(), key=lambda kv: -kv[1]))
    )
    lines.append("")
    lines.append(
        "Total-score sanity (rho(score, fwd)): "
        + " ".join(f"+{h}d={score_rhos[h]:+.3f}(N={len(score_pairs[h])})" for h in HORIZONS)
    )
    lines.append("")

    def fmt_table(stats: list[dict[str, Any]], title: str) -> list[str]:
        L = [f"## {title}", ""]
        L.append("| Feature | Cov% | MeanContrib | ρ+1d (N) | ρ+3d (N) | ρ+5d (N) | Verdict |")
        L.append("|---|---:|---:|---:|---:|---:|---|")
        for s in stats:

            def fmt_rho(rho: float, n: int) -> str:
                if n == 0 or rho != rho:
                    return "  n/a (0)"
                return f"{rho:+.3f} ({n})"

            L.append(
                f"| {s['feature']} | {s['coverage_pct']:.0f}% | "
                f"{s['mean_contrib']:+.2f} | "
                f"{fmt_rho(s['rho_1d'], s['n_1d'])} | "
                f"{fmt_rho(s['rho_3d'], s['n_3d'])} | "
                f"{fmt_rho(s['rho_5d'], s['n_5d'])} | "
                f"{s['verdict_1d']} |"
            )
        L.append("")
        return L

    lines += fmt_table(
        all_stats,
        "1. Headline — per-feature ρ vs forward return (ALL rows where feature contributed)",
    )

    # Tercile spread
    lines.append("## 2. Within-feature tercile spread (+1d, contributors only)")
    lines.append("")
    lines.append("| Feature | n_each | Bot avg | Top avg | Spread (Top-Bot) |")
    lines.append("|---|---:|---:|---:|---:|")
    for s in all_stats:
        if s["tercile_n_each"] == 0:
            lines.append(f"| {s['feature']} | 0 | n/a | n/a | n/a |")
        else:
            lines.append(
                f"| {s['feature']} | {s['tercile_n_each']} | "
                f"{s['tercile_bot_avg']:+.2f}% | {s['tercile_top_avg']:+.2f}% | "
                f"{s['tercile_spread']:+.2f}% |"
            )
    lines.append("")

    # Coverage
    lines.append("## 3. Coverage histogram (% rows with nonzero contribution)")
    lines.append("")
    lines.append("| Feature | Coverage | NonzeroN/Total | Mean Contrib (nonzero) |")
    lines.append("|---|---:|---:|---:|")
    for s in sorted(all_stats, key=lambda x: -x["coverage_pct"]):
        lines.append(
            f"| {s['feature']} | {s['coverage_pct']:.0f}% | "
            f"{s['n_nonzero']}/{s['n_total']} | {s['mean_contrib']:+.2f} |"
        )
    lines.append("")

    # Passed-only
    lines.append("## 4. Passed-only subset (gated_by='passed')")
    lines.append("")
    lines.append(f"N_passed_rows = {len(passed_rows)}")
    lines.append("")
    if passed_stats:
        lines += fmt_table(passed_stats, "Passed-only ρ table")
    else:
        lines.append("No passed rows — nothing to correlate.")
        lines.append("")

    # Catalyst lead-vs-chase
    lines.append("## 5. Catalyst lead-vs-chase")
    lines.append("")
    lines.append(f"Rows with catalyst_strength > 0: {catalyst_findings['n_rows']}")
    for h in HORIZONS:
        n = catalyst_findings[f"n_{h}d"]
        rho = catalyst_findings[f"rho_{h}d"]
        mn = catalyst_findings[f"mean_fwd_{h}d"]
        rho_s = "n/a" if n == 0 or rho != rho else f"{rho:+.3f}"
        mn_s = "n/a" if n == 0 else f"{mn:+.2f}%"
        lines.append(f"- +{h}d: N={n}, ρ(catalyst_pts, fwd)={rho_s}, mean_fwd={mn_s}")
    lines.append("")
    cat_rho1 = catalyst_findings["rho_1d"]
    if catalyst_findings["n_1d"] >= 10 and cat_rho1 == cat_rho1:
        if cat_rho1 > 0.10:
            lines.append(
                "Interpretation: catalyst contribution LEADS forward return — amplifying catalyst weight is a plausible cure."
            )
        elif cat_rho1 < -0.10:
            lines.append(
                "Interpretation: catalyst is CHASING (post-move news) — amplifying would worsen the inversion."
            )
        else:
            lines.append(
                "Interpretation: catalyst is noise at this sample size — neither lead nor chase confirmed."
            )
    else:
        lines.append(
            "Interpretation: insufficient catalyst-positive observations to confidently classify lead vs chase."
        )
    lines.append("")

    # Summary + recommendations
    lines.append("## 6. Plain English summary")
    lines.append("")
    # Identify worst inverters and best signal carriers (require N>=10)
    qualified = [s for s in all_stats if s["n_1d"] >= 10 and s["rho_1d"] == s["rho_1d"]]
    inverters = sorted([s for s in qualified if s["rho_1d"] < -0.1], key=lambda x: x["rho_1d"])
    carriers = sorted([s for s in qualified if s["rho_1d"] > 0.1], key=lambda x: -x["rho_1d"])

    inv_names = (
        ", ".join(
            f"{s['feature']} (ρ={s['rho_1d']:+.2f}, mean={s['mean_contrib']:+.1f}pts)"
            for s in inverters[:4]
        )
        or "none qualified"
    )
    car_names = (
        ", ".join(
            f"{s['feature']} (ρ={s['rho_1d']:+.2f}, mean={s['mean_contrib']:+.1f}pts)"
            for s in carriers[:4]
        )
        or "none qualified"
    )

    lines.append(
        f"Over the window, score↔fwd ρ at +1d = {score_rhos[1]:+.3f} "
        f"(N={len(score_pairs[1])}). "
        f"Features driving inversion: {inv_names}. "
        f"Features carrying positive signal: {car_names}. "
        "Sample size is small (≈10 scan days, sub-100 rows total), so each individual rho should be treated as directional, not statistically tight. Treat anything with N<20 as suggestive only."
    )
    lines.append("")

    # Confounder note
    lines.append("### Confounder check")
    lines.append("")
    lines.append(
        "All scoring contributions are bounded by their weight×feature_norm products, so dominant-feature inversions can co-move (e.g., bullish_sector_belief_count and belief_conviction both spike on the same names). If both invert, the marginal attribution to either is ambiguous — caution before isolated weight cuts. Also: top scorers may concentrate in large-caps that underperform mid-caps in current regime; without a beta/size control we cannot exclude this confound from the per-feature ρ signs."
    )
    lines.append("")

    lines.append("## 7. Recommended weight reshuffles")
    lines.append("")
    if not qualified:
        lines.append("Insufficient data — no recommendation.")
    else:
        recs = []
        for s in inverters[:3]:
            recs.append(
                f"- Consider trimming `{s['feature']}` weight (ρ+1d={s['rho_1d']:+.2f}, "
                f"contributes mean {s['mean_contrib']:+.1f} pts on {s['coverage_pct']:.0f}% of rows). "
                "Suggest a ~30-50% reduction pending re-test."
            )
        for s in carriers[:3]:
            recs.append(
                f"- Consider boosting `{s['feature']}` weight (ρ+1d={s['rho_1d']:+.2f}, "
                f"contributes mean {s['mean_contrib']:+.1f} pts on {s['coverage_pct']:.0f}% of rows). "
                "Suggest reallocating from inverters above."
            )
        # Catalyst-specific
        if catalyst_findings["n_1d"] >= 10:
            cr = catalyst_findings["rho_1d"]
            if cr == cr:
                if cr > 0.10:
                    recs.append(
                        f"- Specifically, raise catalyst_strength weight (currently 0.14 in v2.2.0); "
                        f"catalyst contributors show ρ+1d={cr:+.2f}, mean_fwd={catalyst_findings['mean_fwd_1d']:+.2f}%. "
                        "Suggest 0.14 → 0.18-0.20."
                    )
                elif cr < -0.10:
                    recs.append(
                        f"- Do NOT raise catalyst_strength weight: catalyst contributors invert (ρ+1d={cr:+.2f}). "
                        "Catalyst tagging appears to chase rather than lead — investigate tagger upstream before reweighting."
                    )
        lines += recs
        lines.append("")
        lines.append(
            "Caveats: N≈10 scan days. Re-run on a wider window (≥60 days, ideally regime-balanced) before committing weight changes to YAML. "
            "Also re-test in a /pipeline-review eval, not just spearman — top-tercile entry P&L is the true KPI."
        )
    lines.append("")

    # Per-scan total-score ρ for context
    lines.append("## Appendix: per-scan-date score ρ at +1d")
    lines.append("")
    by_scan: dict[date, list[tuple[float, float]]] = defaultdict(list)
    for r in enriched:
        f1 = r["rets"][1]
        if f1 is None:
            continue
        by_scan[r["scan_date"]].append((r["score"], f1))
    lines.append("| scan_date | N | ρ(score,fwd+1d) | mean_fwd |")
    lines.append("|---|---:|---:|---:|")
    for d, pairs in sorted(by_scan.items()):
        if len(pairs) < 2:
            continue
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        rho = spearman(xs, ys)
        lines.append(f"| {d.isoformat()} | {len(pairs)} | {rho:+.3f} | {mean(ys):+.2f}% |")

    text = "\n".join(lines) + "\n"
    with open(OUT_PATH, "w") as f:
        f.write(text)

    # stdout: headline table + summary
    print(f"\nWrote {OUT_PATH}\n")
    print("=" * 100)
    print(f"Window {WINDOW_START}..{WINDOW_END}  N_rows={len(enriched)}  N_tickers={len(tickers)}")
    print(
        "Total-score ρ(score,fwd): "
        + "  ".join(f"+{h}d={score_rhos[h]:+.3f}(N={len(score_pairs[h])})" for h in HORIZONS)
    )
    print("=" * 100)
    print(
        f"{'Feature':<32} {'Cov%':>5} {'MnPts':>7} {'ρ1d':>8} {'N1d':>4} {'ρ3d':>8} {'N3d':>4} {'ρ5d':>8} {'N5d':>4}  Verdict"
    )
    print("-" * 110)

    def fmt_rho_8(rho: float, n: int) -> str:
        if n == 0 or rho != rho:
            return f"{'  n/a':>8}"
        return f"{rho:+8.3f}"

    for s in all_stats:
        print(
            f"{s['feature']:<32} {s['coverage_pct']:>4.0f}% "
            f"{s['mean_contrib']:>+7.2f} "
            f"{fmt_rho_8(s['rho_1d'], s['n_1d'])} {s['n_1d']:>4} "
            f"{fmt_rho_8(s['rho_3d'], s['n_3d'])} {s['n_3d']:>4} "
            f"{fmt_rho_8(s['rho_5d'], s['n_5d'])} {s['n_5d']:>4}  "
            f"{s['verdict_1d']}"
        )
    print("")
    print("Summary:")
    print(
        f"  Score↔fwd+1d ρ = {score_rhos[1]:+.3f} (N={len(score_pairs[1])}). "
        f"Inverters: {inv_names}. Carriers: {car_names}."
    )
    print(
        "  Catalyst-specific: "
        + ", ".join(
            f"+{h}d ρ={catalyst_findings[f'rho_{h}d']:+.3f}"
            if catalyst_findings[f"n_{h}d"] >= 1
            and catalyst_findings[f"rho_{h}d"] == catalyst_findings[f"rho_{h}d"]
            else f"+{h}d ρ=n/a"
            for h in HORIZONS
        )
        + f" on N_cat={catalyst_findings['n_rows']} contributor rows."
    )
    print("")
    return 0


def main() -> int:
    sys.path.insert(0, "scripts")
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
