"""Convert technicals dicts to natural-language prose strings."""

from __future__ import annotations

from datetime import date, datetime, timedelta


def is_structural_uptrend(data: dict) -> bool:
    """Structural uptrend = Supertrend green + ADX confirms bullish pressure.

    Not just "price above MA" — requires trend infrastructure intact.
    """
    st_dir = data.get("supertrend_direction")
    adx_dmp = data.get("adx_dmp") or 0
    adx_dmn = data.get("adx_dmn") or 0
    return st_dir == "UP" and adx_dmp > adx_dmn


def _format_technicals_prose(data: dict) -> str:
    """Convert technicals dict to comprehensive natural prose."""
    if "error" in data:
        return f"Technicals: {data['error']}"

    ticker = data.get("ticker", "?")
    close = data.get("close", 0)
    rsi = data.get("rsi")
    trend = data.get("trend", {}) or {}
    pattern = data.get("pattern", {}) or {}
    levels = data.get("levels", {}) or {}
    volume_ctx = data.get("volume_context", {}) or {}
    macd_hist = data.get("macd_histogram")

    price_k = close / 1000

    parts = [f"{ticker} Technical Analysis:"]

    if trend:
        t = trend.get("trend", "UNKNOWN")
        s = trend.get("strength", "unknown")
        m = trend.get("momentum", "neutral")
        parts.append(f"Trend: {t} ({s} strength), {m} momentum.")

    if levels:
        support = levels.get("nearest_support")
        swing_low = levels.get("swing_low")
        swing_high = levels.get("swing_high")
        range_low = levels.get("range_20d_low")
        range_high = levels.get("range_20d_high")

        support_k = support / 1000 if support else None
        range_low_k = range_low / 1000 if range_low else None
        range_high_k = range_high / 1000 if range_high else None

        price_line = f"Price: {price_k:.1f}k"
        if support_k:
            dist = (price_k - support_k) / price_k * 100 if price_k else 0
            price_line += f", {dist:.1f}% above support at {support_k:.1f}k"
        if range_low_k and range_high_k:
            price_line += f". Range: {range_low_k:.1f}k-{range_high_k:.1f}k over 20 days."
        parts.append(price_line)

        level_detail = []
        if swing_low:
            swing_low_k = swing_low / 1000
            swing_low_date = levels.get("swing_low_date", "")
            level_detail.append(
                f"Support {swing_low_k:.1f}k (swing low{' ' + swing_low_date if swing_low_date else ''})"
            )
        if swing_high:
            swing_high_k = swing_high / 1000
            swing_high_date = levels.get("swing_high_date", "")
            level_detail.append(
                f"Resistance {swing_high_k:.1f}k (swing high{' ' + swing_high_date if swing_high_date else ''})"
            )
        if level_detail:
            parts.append("Levels: " + "; ".join(level_detail) + ".")

    if rsi is not None:
        if rsi < 30:
            rsi_text = f"RSI: {rsi:.0f} (OVERSOLD)."
        elif rsi > 70:
            rsi_text = f"RSI: {rsi:.0f} (OVERBOUGHT)."
        elif 60 <= rsi <= 70:
            if is_structural_uptrend(data):
                rsi_text = f"RSI: {rsi:.0f} (elevated — normal in confirmed uptrend)."
            else:
                rsi_text = f"RSI: {rsi:.0f} (approaching overbought)."
        elif 40 <= rsi <= 50:
            rsi_text = f"RSI: {rsi:.0f} (neutral zone)."
        elif 30 <= rsi < 40:
            rsi_text = f"RSI: {rsi:.0f} (approaching oversold)."
        else:
            rsi_text = f"RSI: {rsi:.0f}."
        parts.append(rsi_text)

    if macd_hist is not None:
        if macd_hist > 0:
            parts.append(f"MACD: bullish (+{macd_hist:.2f} histogram).")
        else:
            parts.append(f"MACD: bearish ({macd_hist:.2f} histogram).")

    if pattern.get("pattern"):
        p = pattern["pattern"]
        sig = pattern.get("signal", "")
        parts.append(f"Pattern: {p} detected ({sig}).")

    if volume_ctx:
        vol_trend = volume_ctx.get("volume_trend", "unknown")
        bounce = volume_ctx.get("bounce_confirmed")
        prior_vol = volume_ctx.get("prior_down_volume")

        vol_text = f"Volume: {vol_trend} trend."
        if bounce is True:
            vol_text += " Bounce CONFIRMED (up-day volume > prior down-day)."
        elif bounce is False and prior_vol:
            vol_text += " Bounce NOT confirmed (weak volume vs prior sell-off)."
        parts.append(vol_text)

    price_action = data.get("price_action")
    if price_action and price_action.get("classification") != "NORMAL":
        from ..price_action import format_price_action_prose

        pa_prose = format_price_action_prose(price_action)
        if pa_prose:
            parts.append(pa_prose)

    return " ".join(parts)


def _check_staleness(data: dict, scan_date: date | None = None) -> str | None:
    """Check if technicals data is stale (>3 trading days old).

    Returns a warning string if stale, None otherwise.
    """
    data_date_str = data.get("data_date")
    if not data_date_str:
        return None

    try:
        data_date = datetime.strptime(data_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    from shared.market_calendar import is_trading_day

    reference = scan_date or date.today()
    delta_days = (reference - data_date).days
    if delta_days <= 0:
        return None

    trading_days = sum(
        1 for i in range(1, delta_days + 1) if is_trading_day(data_date + timedelta(days=i))
    )

    if trading_days > 3:
        return (
            f"Data is {trading_days} trading days old "
            f"(last price date: {data_date_str}). Treat with caution."
        )
    return None
