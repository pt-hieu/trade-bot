# Trading Context Reference

## Risk Parameters (Live — Query at Runtime)

Risk params are stored in the `trading_config` DB table. Do NOT hardcode values.
Use `get_cash` MCP tool or query DB for: cash reserve, max risk per trade, max positions, position sizing formula.

---

## Data Source Hierarchy

When data from different sources conflicts, this is the priority order:

| Priority | Source | Trust Level |
|----------|--------|------------|
| 1 (highest) | `shared.api.*` (API-first modules) | Normalized, fresh from vnstock API |
| 2 | vnstock API real-time calls | Current but unverified, use for intraday only |
| 3 | Tool results from agent tools | Processed/summarized — check for staleness |
| 4 (lowest) | LLM training knowledge | **NEVER trust for prices, volumes, or dates** |

**Rule:** If DB data and LLM "knowledge" conflict, DB wins. Always. LLM training data is months old and cannot be trusted for any specific market values.

---

## Trading Strategies

### Strategy 1: Buy the Bounce
**Signal:** RSI below 30 crosses back above 30 at support level.
**Entry:** When RSI crosses above 30 with price at historical support.
**Exit:** When price reaches resistance or RSI > 70.

### Strategy 2: Ride the Trend
**Signal:** Uptrending stock pulls back to moving average.
**Entry:** Price touches MA (20 or 50 day) with RSI 40-50.
**Exit:** Previous swing high or RSI > 70.

### Strategy 3: Catch the Breakout
**Signal:** Price breaks above resistance with 2-3x normal volume.
**Entry:** Close above resistance with volume confirmation.
**Exit:** Target = breakout level + prior trading range height.

### Strategy 4: Spot the Divergence
**Signal:** Price makes lower low but RSI makes higher low (bullish divergence).
**Entry:** When divergence confirmed with price reversal.
**Exit:** When reversal plays out or hits resistance.

---

## Technical Analysis Framework

### Core Indicators
1. **RSI (14-period):** <30 oversold, >70 overbought
2. **Bollinger Bands:** Upper = overbought, Middle (SMA20) = trend, Lower = oversold
3. **MACD:** Cross above signal = buy, cross below = sell
4. **Volume:** Confirms trend strength, validates breakouts
5. **Moving Averages:** SMA 20 (short), SMA 50 (medium), SMA 100 (long)

### ATR (Average True Range)
- 14-period ATR for stop-loss sizing
- Stop = Entry - (ATR × 2), Target = Entry + (ATR × 3)
- Better than arbitrary % stops

*Detailed field tables for Supertrend, ADX, Bollinger Bands, Stochastic → `references/indicator-fields.md`*

### Candlestick Patterns (Auto-Detected)
| Pattern | Signal |
|---------|--------|
| Hammer | Bullish reversal at support (small body, long lower wick >2x body) |
| Inverted Hammer | Bullish reversal (small body, long upper wick) |
| Doji | Indecision / potential reversal (open ≈ close, <0.1% range) |
| Bullish Engulfing | Strong bullish reversal (green body engulfs prior red) |
| Bearish Engulfing | Strong bearish reversal (red body engulfs prior green) |

### Trend Classification
| Field | Values | Logic |
|-------|--------|-------|
| `trend` | UPTREND, DOWNTREND, SIDEWAYS | Price vs MA20 vs MA50 |
| `strength` | strong, moderate, weak | Distance from MA20 (>5%, 2-5%, <2%) |
| `momentum` | bullish, neutral, bearish | Green candle count in last 5 days |

### Support/Resistance Methodology
**Entry:** Use `nearest_support` or current price if bouncing from support.
**Stop:** Place 1-2% below `swing_low` or `range_20d_low`.
**Target:** Use `swing_high` or `range_20d_high`.
**R:R:** (Target - Entry) / (Entry - Stop) must be ≥ 3.0.

---

## Vietnamese Market Context

### Trading Hours (GMT+7)
- Morning: 9:15 AM - 11:30 AM
- Afternoon: 1:00 PM - 2:30 PM

### Daily Price Limits
- HOSE: ±7% | HNX: ±10% | UPCoM: ±15%

### Settlement & Tax
- T+1 settlement (KRX system since May 2025), T+0 same-day available
- **Transaction Tax:** 0.1% on sale proceeds (not capital gains)
- **No capital gains tax** — tax-loss harvesting is irrelevant
- **Dividends:** Calculated on par value (10,000 VND), not market price
  - Example: 20% dividend on 100 shares = 10,000 × 100 × 20% = 200,000 VND

### Key Catalysts
- **FTSE Emerging Market Upgrade:** Vietnam's upgrade from Frontier to secondary emerging — major passive ETF inflow catalyst expected
- **Public Investment:** Infrastructure driving steel, construction sectors
- **FDI Flows:** Industrial real estate benefits from foreign manufacturing inflows

---

## Long-Term Portfolio Strategy

### Target Allocation
Sector targets are per-operator and live in config, not in this skill. The shape is a
small number of sector buckets with a target weight and a one-line thesis each, e.g.
Technology / Real Estate / Banking for a VN growth tilt.

### Core Holdings
Core long-term names and their entry zones are stored in the `longterm_watchlist` DB
table — query at runtime, never hardcode them here.

### Rebalancing Rules
- **Trim when:** >10% overweight OR stock >50% above entry zone OR 30%+ gain
- **Add when:** Underweight vs target, price at support, monthly contribution available
- Review monthly, act on >10% deviations

### Long-Term Watchlist Status
| Status | Definition |
|--------|------------|
| BUY ZONE | At or below entry zone (gap_pct ≤ 0) |
| NEAR ENTRY | Within 5% above |
| WATCH | Within 15% above |
| WAIT | >15% above entry zone |

---

## Risk Regime Rules

### Global Macro Thresholds
| Indicator | Threshold | Signal |
|-----------|-----------|--------|
| VIX | <18=LOW, 18-25=MODERATE, 25-30=HIGH, >30=EXTREME | Market fear |
| DXY | Change >0.5% | STRONG/WEAK dollar |
| USD/VND | >25,500 | PRESSURE/FLIGHT |

### Risk Regime → Trading Rules
| Regime | Trading Rules |
|--------|---------------|
| CALM | Normal trading, all strategies valid |
| CAUTIOUS | Reduce position sizes, tighter stops |
| ELEVATED | Defensive only (GAS, SAB, VNM), no growth longs |
| CRISIS | Cash preservation, exits only |

---

## Position Monitoring Triggers

### Swing Positions
| Action | Trigger |
|--------|---------|
| EXIT | Position up 15-20% or momentum reversing |
| TRIM | Position up 10%+ (take 50% profit) |
| ADD | Bullish reversal at support |
| HOLD | No action needed |

### Long-Term Positions
| Action | Trigger |
|--------|---------|
| HOLD | Default for 4-year core holdings |
| TRIM | >30% overweight OR +50% above entry zone |
| ADD | Price returns to entry zone |
| EXIT | Only if thesis breaks |

Urgency: `high` (act today), `medium` (this week), `low` (monitor)

---

## Gotchas

- **NEVER let LLMs compute numbers.** Python handles all arithmetic: R:R ratios, position sizing, goal urgency, longterm status, trading mode. LLMs do qualitative judgment only (interpreting context, generating prose, recommendations). Key functions: `compute_setup_from_levels()`, `compute_position_size()`, `determine_mode()`, `calculate_goal_urgency()`.
- **VND prices are integers, not thousands.** All prices in the system are VND integers (e.g., `close=30500` means 30,500 VND). vnstock API returns thousands (`30.5`) but `shared/api/` normalizes at the boundary. NEVER apply magnitude heuristics like `if value > 1000: value /= 1000`.
- **Anti-conservatism compounding.** 12+ conservative gates can compound to produce 0 entries for days despite available cash. Circuit breaker in `strategy_director.py` ensures `max_entries ≥ 1, min_rr ≤ 4.5` always. Goal urgency UNREACHABLE uses DETERMINED (min_rr=3.5, max_picks=3), not AGGRESSIVE (min_rr=6.0, max_picks=1).
- **Risk config is runtime-only.** Never hardcode risk params (cash reserve, max risk per trade, max positions). Always query `trading_config` DB table or use `get_cash` MCP tool.

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `pipeline-workflows` | Understanding how trading strategies are implemented as automated pipeline agents |
| `finance-prompting` | Improving how agents reason about the trading signals and strategies described here |
| `agent-development` | Modifying an agent that applies these strategies (entry_strategist, position_monitor, etc.) |
| `data-layer` | Understanding where technical indicators, prices, and risk params are fetched from |
