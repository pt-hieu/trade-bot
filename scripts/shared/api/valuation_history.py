"""Historical valuation analysis — percentiles and trajectory from 8Q ratios.

Computes where a stock's PE/PB/ROE/margin sits in its own historical range.
All calculations are deterministic Python (rule 9 — no LLM math).
"""

from .fundamentals import get_financial_ratios


def _percentile(values: list[float], current: float) -> int:
    """Compute percentile rank of current in values (0-100)."""
    if not values:
        return 50
    below = sum(1 for v in values if v < current)
    return round(below / len(values) * 100)


def _zone(pct: int) -> str:
    if pct >= 90:
        return "EXTREME_HIGH"
    if pct > 75:
        return "EXPENSIVE"
    if pct >= 25:
        return "FAIR"
    if pct > 10:
        return "CHEAP"
    return "EXTREME_LOW"


def _trend(values: list[float]) -> str:
    """IMPROVING | STABLE | DECLINING (newest first, >=4 values)."""
    if len(values) < 4:
        return "STABLE"
    newest_avg = (values[0] + values[1]) / 2
    oldest_avg = (values[2] + values[3]) / 2
    delta = newest_avg - oldest_avg
    if delta > 1.5:
        return "IMPROVING"
    if delta < -1.5:
        return "DECLINING"
    return "STABLE"


def _cagr(values: list[float]) -> float | None:
    """4Q CAGR: (newest/oldest)^(1/n) - 1 using first and last valid values."""
    valid = [v for v in values if v and v > 0]
    if len(valid) < 2:
        return None
    n = len(valid) - 1
    return (valid[0] / valid[-1]) ** (1 / n) - 1


def _stat_block(values: list[float], current: float, label: str, pct_units: bool = False) -> dict:
    """Build a stats block for a metric."""
    if not values or current is None:
        return {}
    pct = _percentile(values, current)

    def fmt(v: float) -> float:
        return round(v, 1) if pct_units else round(v, 2)

    return {
        "current": fmt(current),
        "min": fmt(min(values)),
        "p25": fmt(sorted(values)[len(values) // 4]),
        "median": fmt(sorted(values)[len(values) // 2]),
        "p75": fmt(sorted(values)[len(values) * 3 // 4]),
        "max": fmt(max(values)),
        "percentile": pct,
        "zone": _zone(pct),
    }


async def compute_valuation_history(ticker: str, periods: int = 8) -> dict:
    """Compute historical valuation percentiles and trajectories.

    Returns zone classification (CHEAP/FAIR/EXPENSIVE/EXTREME_HIGH/EXTREME_LOW),
    percentile rank, EPS trajectory, and margin trend — all Python-computed.

    Args:
        ticker: Stock symbol.
        periods: Number of quarters of history (default 8).
    """
    ratios = await get_financial_ratios(ticker.upper(), periods=periods)
    if not ratios:
        return {"ticker": ticker, "error": "no data"}

    # Newest first — extract per-metric series (skip None)
    pe_vals = [r["pe"] for r in ratios if r.get("pe") is not None and r["pe"] > 0]
    pb_vals = [r["pb"] for r in ratios if r.get("pb") is not None and r["pb"] > 0]
    roe_vals = [r["roe"] for r in ratios if r.get("roe") is not None]
    nm_vals = [r["net_margin"] for r in ratios if r.get("net_margin") is not None]
    eps_vals = [r["eps"] for r in ratios if r.get("eps") is not None]

    result: dict = {
        "ticker": ticker.upper(),
        "periods": len(ratios),
        "latest_period": ratios[0].get("report_period") if ratios else None,
    }

    if pe_vals:
        result["pe"] = _stat_block(pe_vals[1:], pe_vals[0], "PE") if len(pe_vals) >= 2 else {}
        result["pe"]["current"] = round(pe_vals[0], 2)

    if pb_vals:
        result["pb"] = _stat_block(pb_vals[1:], pb_vals[0], "PB") if len(pb_vals) >= 2 else {}
        result["pb"]["current"] = round(pb_vals[0], 2)

    if roe_vals:
        result["roe"] = (
            _stat_block(roe_vals[1:], roe_vals[0], "ROE", pct_units=True)
            if len(roe_vals) >= 2
            else {}
        )
        result["roe"]["current"] = round(roe_vals[0], 1)

    if nm_vals:
        result["net_margin"] = (
            _stat_block(nm_vals[1:], nm_vals[0], "NM", pct_units=True) if len(nm_vals) >= 2 else {}
        )
        result["net_margin"]["current"] = round(nm_vals[0], 1)

    # EPS trajectory
    if eps_vals:
        cagr = _cagr(eps_vals)
        result["eps_trajectory"] = {
            "latest": round(eps_vals[0]),
            "trend": _trend([float(v) for v in eps_vals]),
            "cagr_4q": round(cagr, 3) if cagr is not None else None,
        }

    # Margin trajectory (uses net margin series)
    if nm_vals:
        avg = sum(nm_vals) / len(nm_vals)
        result["margin_trajectory"] = {
            "trend": _trend(nm_vals),
            "latest": round(nm_vals[0], 1),
            "avg": round(avg, 1),
            "vs_avg": round(nm_vals[0] - avg, 1),
        }

    return result


def format_valuation_history_prose(data: dict) -> str:
    """Format compute_valuation_history output as agent-readable prose."""
    if data.get("error"):
        return f"No valuation history for {data.get('ticker', '?')}: {data['error']}"

    ticker = data.get("ticker", "?")
    periods = data.get("periods", "?")
    period = data.get("latest_period", "?")
    lines = [f"Valuation History — {ticker} ({periods}Q, latest {period}):"]

    def _metric_line(block: dict, label: str, suffix: str = "") -> str | None:
        if not block or "zone" not in block:
            return None
        z = block["zone"]
        pct = block.get("percentile", "?")
        curr = block.get("current", "?")
        lo = block.get("min", "?")
        hi = block.get("max", "?")
        med = block.get("median", "?")
        return (
            f"  {label}: {curr}{suffix} [{z}] — {pct}th pctl of {periods}Q "
            f"({lo}{suffix} - {hi}{suffix}), median {med}{suffix}"
        )

    for key, label, suffix in [
        ("pe", "PE", "x"),
        ("pb", "PB", "x"),
        ("roe", "ROE", "%"),
        ("net_margin", "Net Margin", "%"),
    ]:
        line = _metric_line(data.get(key, {}), label, suffix)
        if line:
            lines.append(line)

    eps = data.get("eps_trajectory")
    if eps:
        trend = eps.get("trend", "?")
        cagr = eps.get("cagr_4q")
        cagr_str = f" ({cagr * 100:+.0f}% 4Q CAGR)" if cagr is not None else ""
        lines.append(f"  EPS: {trend}{cagr_str}, latest {eps.get('latest', '?'):,} VND")

    mt = data.get("margin_trajectory")
    if mt:
        trend = mt.get("trend", "?")
        latest = mt.get("latest", "?")
        avg = mt.get("avg", "?")
        vs = mt.get("vs_avg", 0)
        sign = "+" if vs >= 0 else ""
        lines.append(f"  Margin trend: {trend} — {latest}% vs {periods}Q avg {avg}% ({sign}{vs}pp)")

    return "\n".join(lines)
