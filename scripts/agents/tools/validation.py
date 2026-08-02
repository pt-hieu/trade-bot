"""
Data validation layer for pipeline inputs.

Runs BEFORE Phase 2 agents to catch bad data early:
- Per-ticker: RSI range, price validity, levels consistency
- Capital: arithmetic checks
- Holdings: P/L consistency
- Post-Phase-2: sector signal quality gating
"""

from dataclasses import dataclass, field

from shared.trading_config import get_trading_config


@dataclass
class ValidationReport:
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    excluded_tickers: list[str] = field(default_factory=list)
    corrections: dict = field(default_factory=dict)  # ticker -> {field: corrected_value}

    @property
    def has_issues(self) -> bool:
        return bool(self.warnings or self.blockers)

    def log(self):
        if self.blockers:
            print(f"  [Validation] BLOCKERS ({len(self.blockers)}):")
            for b in self.blockers:
                print(f"    !! {b}")
        if self.warnings:
            print(f"  [Validation] Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"    -- {w}")
        if self.excluded_tickers:
            print(f"  [Validation] Excluded tickers: {', '.join(self.excluded_tickers)}")


def validate_pipeline_data(
    technicals: dict,
    cash_balance: float,
    holdings: list[dict],
    macro: dict | None = None,
) -> ValidationReport:
    """Validate pipeline data before Phase 2 agents.

    Args:
        technicals: Dict of ticker -> technical data
        cash_balance: Total cash in VND
        holdings: list[HoldingData] — one row per (ticker, plan_type) slice
        macro: Optional macro metrics dict

    Returns:
        ValidationReport with warnings, blockers, excluded tickers
    """
    report = ValidationReport()
    excluded = []

    # --- Per-ticker validation ---
    for ticker, data in technicals.items():
        if not isinstance(data, dict):
            report.warnings.append(f"{ticker}: non-dict technical data, skipping")
            excluded.append(ticker)
            continue

        if data.get("error"):
            report.warnings.append(f"{ticker}: technical data error — {data['error']}")
            excluded.append(ticker)
            continue

        # Price validity
        close = data.get("close") or data.get("price")
        if close is not None and close <= 0:
            report.blockers.append(f"{ticker}: invalid price {close} <= 0")
            excluded.append(ticker)
            continue

        # RSI range
        rsi = data.get("rsi")
        if rsi is not None:
            if rsi < 0 or rsi > 100:
                report.warnings.append(f"{ticker}: RSI={rsi} out of [0,100] range")
            elif rsi < 5 or rsi > 95:
                report.warnings.append(f"{ticker}: extreme RSI={rsi:.1f}")

        # Levels consistency
        levels = data.get("levels", {})
        swing_low = levels.get("swing_low") or levels.get("range_20d_low")
        swing_high = levels.get("swing_high") or levels.get("range_20d_high")

        if close and swing_low and swing_low >= close:
            report.warnings.append(
                f"{ticker}: swing_low ({swing_low}) >= close ({close}) — levels may be stale"
            )

        if close and swing_high and swing_high <= close:
            report.warnings.append(
                f"{ticker}: swing_high ({swing_high}) <= close ({close}) — resistance already broken"
            )

    report.excluded_tickers = list(set(excluded))

    # --- Capital validation ---
    cfg = get_trading_config()
    min_reserve = cfg.min_cash_reserve
    if cash_balance < min_reserve:
        report.warnings.append(
            f"Cash {cash_balance:,.0f} below reserve {min_reserve:,.0f} — no entries allowed"
        )
    elif cash_balance < min_reserve + cfg.low_cash_threshold:
        report.warnings.append(f"Cash near reserve ({cash_balance:,.0f}) — minimal entries only")

    # --- Holdings validation ---
    # Holdings is a list of (ticker, plan_type) slice rows per migration 314.
    # Iterate each slice separately so dual-listed tickers (e.g. FPT SWING +
    # FPT LONGTERM) are each validated against their own cost basis.
    for h in holdings:
        ticker = h.get("ticker") or "?"
        plan_type = h.get("plan_type") or "?"
        label = f"{ticker} {plan_type}" if plan_type != "?" else ticker
        avg_cost = h.get("avg_cost") or 0
        if avg_cost <= 0:
            report.warnings.append(f"Holdings: {label} avg_cost={avg_cost} — P/L unreliable")
            continue

        # The authoritative key emitted by shared.neon.portfolio for open
        # holdings is `pct_from_entry`. The previous fallback chain (`pl_pct`
        # → `pnl_pct`) never matched, masking the P/L mismatch check and
        # contributing to MON-2026-04-19-003 (-12.3% vs -10.1% brief drift).
        pct_from_entry = h.get("pct_from_entry")
        current = h.get("current_price_vnd")
        if pct_from_entry is not None and current is not None and avg_cost > 0:
            expected_pl = (current - avg_cost) / avg_cost * 100
            if abs(expected_pl - pct_from_entry) > 2.0:  # 2% tolerance for fees/rounding
                report.warnings.append(
                    f"Holdings: {label} P/L mismatch — stored {pct_from_entry:.1f}% vs "
                    f"calculated {expected_pl:.1f}%"
                )

        # Extreme P/L check (possible data error)
        if pct_from_entry is not None and (pct_from_entry < -50 or pct_from_entry > 150):
            report.warnings.append(
                f"Holdings: {label} extreme P/L {pct_from_entry:.1f}% — verify data accuracy"
            )

    # --- Macro validation ---
    if macro and not macro.get("error"):
        vix = macro.get("vix_value")
        if vix is not None and (vix < 0 or vix > 100):
            report.warnings.append(f"Macro: VIX={vix} out of expected range")
        dxy = macro.get("dxy_value")
        if dxy is not None and (dxy < 80 or dxy > 130):
            report.warnings.append(f"Macro: DXY={dxy} out of historical range")

    return report


def validate_sector_signals(
    signals: list[dict],
    technicals: dict,
    rotation: dict | None = None,
) -> list[dict]:
    """Post-Phase-2: Gate sector BUY signals against data quality.

    Returns list of flagged warnings (not removals — agent decides).
    Each warning is: {ticker, issues, signal_type}
    """
    flagged = []
    cold_sectors: set[str] = set()
    if rotation:
        cold_sectors = set(rotation.get("cold_sectors", []))

    for sig in signals:
        if sig.get("signal") != "BUY":
            continue

        ticker = sig.get("ticker", "")
        sector = sig.get("sector", "")
        data = technicals.get(ticker, {})
        rsi = data.get("rsi")
        levels = data.get("levels", {})
        swing_low = levels.get("swing_low") or levels.get("range_20d_low")

        issues = []

        # RSI > 70 + BUY signal = potential chasing
        if rsi is not None and rsi > 70:
            issues.append(f"overbought RSI={rsi:.0f}")

        # Cold sector + BUY signal = headwind
        if sector in cold_sectors:
            issues.append(f"cold sector ({sector})")

        # No support level available
        if not swing_low and not levels.get("nearest_support"):
            issues.append("no support level for stop placement")

        if issues:
            flagged.append(
                {
                    "ticker": ticker,
                    "sector": sector,
                    "issues": issues,
                    "signal_type": "BUY",
                }
            )

    return flagged
