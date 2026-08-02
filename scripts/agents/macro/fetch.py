"""External data fetchers (vnstock + yfinance) used by fetch_macro_metrics."""

from __future__ import annotations

import asyncio

from shared.errors import report_caught


def _yf_pair(indicator: dict, value_key: str, change_key: str) -> dict:
    """Extract value + change_pct from a yfinance indicator dict, None if no data."""
    if "value" not in indicator:
        return {value_key: None, change_key: None}
    return {value_key: indicator["value"], change_key: indicator.get("change_pct")}


async def _fetch_macro_data() -> dict:
    """Fetch DXY, VIX, USD/VND from Lightsail API.

    USD/VND: prefer SBV reference rate (stable, official), fallback to yfinance
    market rate. When both available, compute spread as additional stress signal.
    """
    from shared.vnstock_client import (
        fetch_commodity_prices,
        fetch_macro_global,
        fetch_market_breadth,
    )

    macro, breadth, commodities = await asyncio.gather(
        fetch_macro_global(),
        fetch_market_breadth(),
        fetch_commodity_prices(),
    )

    dxy = macro.get("dxy", {})
    vix = macro.get("vix", {})

    usd_vnd_rate = 0.0
    usd_vnd_source = None
    usd_vnd_spread = None

    try:
        from shared.macro_utils import extract_sbv_central_rate
        from shared.vnstock_client import fetch_exchange_rate

        exr = await fetch_exchange_rate()
        data_rows = exr.get("data", [])
        central_rate = extract_sbv_central_rate(data_rows)
        if central_rate:
            usd_vnd_rate = central_rate
            usd_vnd_source = "sbv"
            print(f"  [Macro] USD/VND: using SBV central rate {usd_vnd_rate:.0f}")
        else:
            latest = exr.get("latest", {})
            for val in latest.values():
                if isinstance(val, (int, float)) and 20000 < val < 30000:
                    usd_vnd_rate = float(val)
                    usd_vnd_source = "sbv"
                    print(f"  [Macro] USD/VND: using SBV rate (fallback scan) {usd_vnd_rate:.0f}")
                    break
    except Exception as e:
        report_caught("macro.usd_vnd_sbv", e)

    usd_vnd_yf = macro.get("usd_vnd", {})
    yf_rate = usd_vnd_yf.get("value", 0.0) if isinstance(usd_vnd_yf, dict) else 0.0

    if usd_vnd_rate and yf_rate:
        usd_vnd_spread = round(yf_rate - usd_vnd_rate, 2)
        print(f"  [Macro] USD/VND spread (market - SBV): {usd_vnd_spread:.0f}")
    elif not usd_vnd_rate and yf_rate:
        usd_vnd_rate = yf_rate
        usd_vnd_source = "yfinance"
        print(
            f"  [Macro] USD/VND: fallback to yfinance market rate {usd_vnd_rate:.0f} (SBV unavailable)"
        )
    elif not usd_vnd_rate:
        usd_vnd_source = "failed"
        print("  [Macro] USD/VND: both sources failed")

    oil_crude = commodities.get("oil_crude", {}) if isinstance(commodities, dict) else {}
    oil_price = oil_crude.get("price")
    oil_change_pct = oil_crude.get("change_1d_pct")
    oil_source = "vnstock"
    if not oil_price or oil_price <= 0:
        yf_oil = macro.get("oil", {})
        oil_price = yf_oil.get("value")
        oil_change_pct = yf_oil.get("change_pct")
        oil_source = "yfinance"
        if oil_price:
            print(f"  [Macro] Oil: fallback to yfinance CL=F ${oil_price:.2f}")
    else:
        print(
            f"  [Macro] Oil: vnstock oil_crude ${oil_price:.2f} ({oil_change_pct:+.2f}%)"
            if oil_change_pct
            else f"  [Macro] Oil: vnstock oil_crude ${oil_price:.2f}"
        )

    copper = macro.get("copper", {})
    us_10y = macro.get("us_10y", {})
    shanghai = macro.get("shanghai", {})

    sp500 = macro.get("sp500", {})
    nasdaq = macro.get("nasdaq", {})
    dow = macro.get("dow", {})

    return {
        "dxy_value": dxy.get("value", 0.0),
        "dxy_change_pct": dxy.get("change_pct", 0.0),
        "vix_value": vix.get("value", 0.0),
        "vix_change_pct": vix.get("change_pct", 0.0),
        "usd_vnd_rate": usd_vnd_rate,
        "usd_vnd_source": usd_vnd_source,
        "usd_vnd_spread": usd_vnd_spread,
        **_yf_pair(copper, "copper_price", "copper_change_pct"),
        "oil_price": oil_price,
        "oil_change_pct": oil_change_pct,
        "oil_source": oil_source,
        **_yf_pair(us_10y, "us_10y_yield", "us_10y_change_pct"),
        **_yf_pair(shanghai, "shanghai_close", "shanghai_change_pct"),
        **_yf_pair(sp500, "sp500_close", "sp500_change_pct"),
        **_yf_pair(nasdaq, "nasdaq_close", "nasdaq_change_pct"),
        **_yf_pair(dow, "dow_close", "dow_change_pct"),
        "breadth_advance": breadth.get("advance"),
        "breadth_decline": breadth.get("decline"),
        "breadth_ratio": breadth.get("breadth_ratio"),
    }
