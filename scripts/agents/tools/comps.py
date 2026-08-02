#!/usr/bin/env python3
"""
Comparable company analysis — deterministic peer group statistics.

Adapts the "5-10 Rule" from financial-services-plugins:
  5 operating metrics + 5 valuation metrics per sector.
  Statistics block: max, p75, median, p25, min.
  Target company's percentile rank within peer group.

Vietnam-calibrated sanity ranges:
  PE: 8-15x (not 10-50x US), EV/EBITDA: 5-12x
"""

from __future__ import annotations

from shared.api.fundamentals import get_financial_ratios_batch

# ── Sector-specific metric sets ────────────────────────────────────────────────

_DEFAULT_METRICS = [
    "roe",
    "net_margin",
    "gross_margin",
    "operating_margin",
    "pe",
    "pb",
    "debt_to_equity",
    "current_ratio",
]

_SECTOR_METRICS: dict[str, list[str]] = {
    "banking": ["roe", "roa", "net_margin", "current_ratio", "pe", "pb", "debt_to_equity"],
    "bank": ["roe", "roa", "net_margin", "current_ratio", "pe", "pb", "debt_to_equity"],
    "real_estate": [
        "roe",
        "gross_margin",
        "net_margin",
        "current_ratio",
        "pe",
        "pb",
        "debt_to_equity",
    ],
    "securities": ["roe", "roa", "net_margin", "pe", "pb", "debt_to_equity"],
    "technology": [
        "roe",
        "gross_margin",
        "net_margin",
        "operating_margin",
        "pe",
        "pb",
        "debt_to_equity",
    ],
}

_METRIC_LABELS: dict[str, str] = {
    "roe": "ROE (%)",
    "roa": "ROA (%)",
    "net_margin": "Net Margin (%)",
    "gross_margin": "Gross Margin (%)",
    "operating_margin": "Op Margin (%)",
    "pe": "P/E",
    "pb": "P/B",
    "debt_to_equity": "D/E",
    "current_ratio": "Current Ratio",
}


# ── Public API ─────────────────────────────────────────────────────────────────


async def compute_comps(
    target_ticker: str,
    peer_tickers: list[str],
    sector: str | None = None,
) -> dict:
    """Compute comparable company statistics.

    Returns dict with:
      - target: {metric: display_value}
      - peers: {ticker: {metric: display_value}}
      - stats: {metric: {max, p75, median, p25, min}}
      - target_percentile: {metric: 0-100 rank among peers}
      - metrics: list of metric keys used
      - sector: sector name used for metric selection
    """
    all_tickers = list({target_ticker.upper()} | {t.upper() for t in peer_tickers})
    ratios_batch = await get_financial_ratios_batch(all_tickers)

    metrics = _get_metrics(sector)
    peer_data: dict[str, dict[str, float | None]] = {}
    target_data: dict[str, float | None] = {}

    for ticker in all_tickers:
        ratios = ratios_batch.get(ticker, {})
        vals = {m: _get_display_value(m, ratios) for m in metrics}
        if ticker == target_ticker.upper():
            target_data = vals
        else:
            peer_data[ticker] = vals

    stats = _compute_stats(metrics, peer_data)
    target_pct = _compute_percentile_ranks(target_data, metrics, peer_data)

    return {
        "target": target_ticker.upper(),
        "target_data": target_data,
        "peers": peer_data,
        "stats": stats,
        "target_percentile": target_pct,
        "metrics": metrics,
        "sector": sector or "default",
    }


def format_comps_prose(comps: dict) -> str:
    """Format comps result as readable prose table for LLM agents."""
    target = comps["target"]
    metrics = comps["metrics"]
    peers = comps["peers"]
    stats = comps["stats"]
    pct_ranks = comps["target_percentile"]

    lines = [f"=== Comparable Analysis: {target} vs {len(peers)} peers ==="]

    # Header
    col_w = 12
    header = f"{'Ticker':<8}" + "".join(f"{_METRIC_LABELS.get(m, m):>{col_w}}" for m in metrics)
    lines.append(header)
    lines.append("-" * len(header))

    # Target row
    target_row = f"{target:<8}"
    for m in metrics:
        v = comps["target_data"].get(m)
        target_row += f"{_fmt(v):>{col_w}}"
    lines.append(target_row + "  ← target")

    # Peer rows
    for ticker, vals in sorted(peers.items()):
        row = f"{ticker:<8}"
        for m in metrics:
            v = vals.get(m)
            row += f"{_fmt(v):>{col_w}}"
        lines.append(row)

    # Stats block
    lines.append("-" * len(header))
    for label, key in [
        ("Max", "max"),
        ("75th", "p75"),
        ("Median", "median"),
        ("25th", "p25"),
        ("Min", "min"),
    ]:
        row = f"{label:<8}"
        for m in metrics:
            v = stats.get(m, {}).get(key)
            row += f"{_fmt(v):>{col_w}}"
        lines.append(row)

    # Percentile summary
    lines.append("")
    lines.append(f"Percentile ranks for {target} vs peers:")
    pct_parts = []
    for m in metrics:
        pct = pct_ranks.get(m)
        if pct is not None:
            label = _METRIC_LABELS.get(m, m)
            pct_parts.append(f"  {label}: {pct:.0f}th percentile")
    lines.extend(pct_parts)

    return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_metrics(sector: str | None) -> list[str]:
    if not sector:
        return _DEFAULT_METRICS
    key = sector.lower().replace(" ", "_").replace("-", "_")
    return _SECTOR_METRICS.get(key, _DEFAULT_METRICS)


def _get_display_value(metric: str, ratios: dict) -> float | None:
    """Get metric value from ratios dict. Upstream returns whole-number %."""
    return ratios.get(metric)


def _compute_stats(metrics: list[str], peer_data: dict[str, dict]) -> dict:
    """Compute max/p75/median/p25/min for each metric across peers."""
    result = {}
    for m in metrics:
        values = [v for t in peer_data.values() for k, v in [(m, t.get(m))] if v is not None]
        if not values:
            result[m] = {}
            continue
        sorted_v = sorted(values)
        result[m] = {
            "max": sorted_v[-1],
            "p75": _percentile(sorted_v, 75),
            "median": _percentile(sorted_v, 50),
            "p25": _percentile(sorted_v, 25),
            "min": sorted_v[0],
        }
    return result


def _compute_percentile_ranks(
    target_data: dict,
    metrics: list[str],
    peer_data: dict[str, dict],
) -> dict:
    """Compute target's percentile rank (0-100) for each metric vs peers."""
    result = {}
    for m in metrics:
        target_val = target_data.get(m)
        if target_val is None:
            continue
        peer_vals = [v for t in peer_data.values() if (v := t.get(m)) is not None]
        if not peer_vals:
            continue
        rank = sum(1 for v in peer_vals if v <= target_val) / len(peer_vals) * 100
        result[m] = round(rank, 0)
    return result


def _percentile(sorted_values: list[float], pct: int) -> float:
    """Compute percentile from sorted list."""
    if not sorted_values:
        return 0.0
    idx = (pct / 100) * (len(sorted_values) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (idx - lo)


def _fmt(v: float | None) -> str:
    if v is None:
        return "N/A"
    if abs(v) >= 100:
        return f"{v:.1f}"
    return f"{v:.2f}"
