# Trading Context — Indicator Fields Reference

Detailed field tables for technical indicators available in `daily_technicals`.

---

## Supertrend

| Field | Description |
|-------|-------------|
| `supertrend_direction` | `UP` or `DOWN` |
| `supertrend_lower` | Support level (when direction=UP) |
| `supertrend_upper` | Resistance level (when direction=DOWN) |

- `direction=UP` → bullish, use `lower` as dynamic support
- `direction=DOWN` → bearish, use `upper` as dynamic resistance
- Direction change = exit signal

---

## ADX (Trend Strength)

| Field | Description |
|-------|-------------|
| `adx` | Trend strength (0-100) |
| `adx_dmp` | Directional Movement Plus |
| `adx_dmn` | Directional Movement Minus |

- ADX > 25: Strong trend (follow it)
- ADX < 20: Range/sideways (skip or range-trade)
- DMP > DMN: Bullish pressure

---

## Bollinger Bands

| Field | Description |
|-------|-------------|
| `bb_lower` | Lower band (support) |
| `bb_middle` | Middle band (SMA20) |
| `bb_upper` | Upper band (resistance) |
| `bb_bandwidth` | Volatility measure |
| `bb_percent` | Position within bands (0=lower, 1=upper) |

- `bb_bandwidth` low → squeeze, breakout coming

---

## Stochastic

| Signal | Condition |
|--------|-----------|
| Oversold | %K < 20 |
| Overbought | %K > 80 |
| Buy signal | %K crosses above %D below 50 |
| Sell signal | %K crosses below %D above 50 |

---

## Support/Resistance Fields

| Field | Description |
|-------|-------------|
| `swing_high` / `swing_low` | Most recent local high/low (5-bar window) |
| `range_20d_high` / `range_20d_low` | 20-day high/low |
| `nearest_support` | Closest support below current price |
| `nearest_resistance` | Closest resistance above current price |
