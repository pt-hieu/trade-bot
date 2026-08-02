"""Pure computation helpers for financial analysis endpoints."""

import math

BANK_TICKERS = frozenset(
    {
        "TCB",
        "VCB",
        "BID",
        "ACB",
        "MBB",
        "VPB",
        "HDB",
        "STB",
        "CTG",
        "TPB",
        "SHB",
        "VIB",
        "OCB",
        "KLB",
        "SSB",
        "LPB",
        "MSB",
        "EIB",
        "ABB",
        "NAB",
    }
)


def clean_rows(df):
    """Convert DataFrame rows to JSON-safe dicts, newest first."""
    rows = df.to_dict(orient="records")
    for row in rows:
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
            elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = 0.0
    rows.reverse()
    return rows


def get_first_valid(row, *keys):
    for k in keys:
        v = row.get(k)
        if v is not None and v != 0:
            try:
                f = float(v)
                if not math.isnan(f) and not math.isinf(f):
                    return f
            except (ValueError, TypeError):
                pass
    return None


def percentile(values, current):
    if not values:
        return 50
    below = sum(1 for v in values if v < current)
    return round(below / len(values) * 100)


def valuation_zone(pct):
    if pct >= 90:
        return "EXTREME_HIGH"
    if pct > 75:
        return "EXPENSIVE"
    if pct >= 25:
        return "FAIR"
    if pct > 10:
        return "CHEAP"
    return "EXTREME_LOW"


def stat_block(values, current):
    if not values or current is None:
        return {}
    sv = sorted(values)
    n = len(sv)
    pct = percentile(values, current)
    return {
        "current": round(current, 2),
        "min": round(sv[0], 2),
        "p25": round(sv[n // 4], 2),
        "median": round(sv[n // 2], 2),
        "p75": round(sv[n * 3 // 4], 2),
        "max": round(sv[-1], 2),
        "percentile": pct,
        "zone": valuation_zone(pct),
    }


def trend_direction(values):
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


def cagr(values):
    valid = [v for v in values if v and v > 0]
    if len(valid) < 2:
        return None
    n = len(valid) - 1
    return (valid[0] / valid[-1]) ** (1 / n) - 1


def to_pct(v):
    """Convert decimal ratio (0.28) to whole-number % (28.0). vnstock API always returns decimal."""
    if v is None:
        return None
    return round(v * 100, 2)


def pick_income_field(data, *keys):
    for k in keys:
        val = data.get(k)
        if val is not None and val != 0:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    return None


def decompose_earnings(data, is_bank):
    if is_bank:
        revenue = pick_income_field(
            data, "Interest income", "Net interest income", "Net sales", "Revenue"
        )
        core_profit = pick_income_field(
            data, "Operating Profit", "Profit from operating activities"
        )
        non_core = pick_income_field(
            data, "Other income", "Gains from revaluation", "Gain on disposal of investments"
        )
    else:
        revenue = pick_income_field(data, "Net sales", "Net Revenue", "Revenue", "Sales")
        core_profit = pick_income_field(
            data, "Operating Profit", "Profit from operating activities", "Gross Profit"
        )
        non_core = (
            (pick_income_field(data, "Financial income") or 0)
            + (pick_income_field(data, "Other income") or 0)
            + (
                pick_income_field(
                    data, "Share of profit of associates", "Share of profit of joint ventures"
                )
                or 0
            )
            + (
                pick_income_field(data, "Gain on disposal of investments", "Gains from revaluation")
                or 0
            )
        )
        non_core = non_core if non_core != 0 else None
    net_income = pick_income_field(
        data,
        "Net profit/(loss) after tax",
        "Attributable to parent company",
        "Net income",
    )
    return {
        "revenue": revenue,
        "core_profit": core_profit,
        "non_core": non_core,
        "net_income": net_income,
    }


def core_ratio(core, net):
    if core is None or net is None or net == 0:
        return None
    return max(-1.0, min(2.0, core / net))


def earnings_quality_grade(ratio):
    if ratio >= 0.8:
        return "HIGH"
    if ratio >= 0.5:
        return "MEDIUM"
    return "LOW"


def ratio_trend(ratios):
    if len(ratios) < 3:
        return "STABLE"
    newest_avg = sum(ratios[:2]) / 2
    oldest_avg = sum(ratios[-2:]) / 2
    delta = newest_avg - oldest_avg
    if delta > 0.1:
        return "IMPROVING"
    if delta < -0.1:
        return "DECLINING"
    return "STABLE"
