"""Phase 5: Deterministic alert registration from pipeline data."""

import asyncio
import logging
from datetime import date

logger = logging.getLogger(__name__)

from agents.alert_registrar import (
    register_dip_buy_alerts,
    register_picks_as_alerts,
    register_trailing_stop_alerts,
    resolve_alert_conflicts,
    send_immediate_position_directives,
)
from agents.tools.selloff_detector import detect_selloff_setup
from shared.errors import report_caught
from shared.neon.alerts import (
    cancel_alerts_for_date,
    cancel_stale_alerts,
    cap_daily_alerts,
    cleanup_orphan_alerts,
)
from shared.rules.entry_gates import RiskRegime, TradingMode


async def run_alert_registration(
    position_alerts: dict,
    pre_computed_picks: list[dict],
    scan_date,
    risk_regime: RiskRegime,
    trading_mode: TradingMode,
    current_prices: dict[str, float] | None,
    holdings: list[dict] | None = None,
    skip_alerts: bool = False,
) -> dict:
    """Run Phase 5: Deterministic alert registration.

    Returns dict with alert counts.
    """
    if skip_alerts:
        print("  Skipped (--skip-alerts)", flush=True)
        return {"total": 0, "skipped": True}

    # Cancel stale alerts (respects expires_at for multi-day alerts)
    cancelled = await cancel_stale_alerts(scan_date)
    if cancelled:
        print(f"  Cancelled {cancelled} stale alerts from before {scan_date}")

    # Cancel same-day alerts (clean slate for re-runs)
    same_day_cancelled = await cancel_alerts_for_date(scan_date)
    if same_day_cancelled:
        print(f"  Cancelled {same_day_cancelled} same-day alerts (re-run cleanup)")

    # Step 1: Deterministic BUY alerts from pre-computed picks
    pick_alert_count = await register_picks_as_alerts(
        pre_computed_picks=pre_computed_picks,
        source="morning_brief",
        scan_date=scan_date,
        risk_regime=risk_regime,
        trading_mode=trading_mode,
        current_prices=current_prices,
    )
    print(f"  Registered {pick_alert_count} deterministic BUY alerts", flush=True)

    # Step 2: Deterministic trailing stop alerts for holdings
    stop_alert_count = await register_trailing_stop_alerts(
        scan_date,
        current_prices,
        risk_regime=risk_regime,
        trading_mode=trading_mode,
        holdings=holdings,
    )
    if stop_alert_count:
        print(f"  Registered {stop_alert_count} trailing stop alerts", flush=True)

    # Step 3: Multi-tranche dip-buy alerts for BOUNCE-strategy picks with sell-off setup
    dip_count = 0
    if risk_regime != "CRISIS":
        bounce_picks = [pick for pick in pre_computed_picks if pick.get("strategy") == "BOUNCE"]
        # Detect sell-offs in parallel — each makes independent API calls
        selloff_results = (
            await asyncio.gather(
                *(detect_selloff_setup(pick["ticker"], scan_date) for pick in bounce_picks),
                return_exceptions=True,
            )
            if bounce_picks
            else []
        )
        selloff_setups = []
        for pick, setup in zip(bounce_picks, selloff_results, strict=True):
            if isinstance(setup, BaseException):
                logger.warning("Selloff detection failed for %s: %s", pick["ticker"], setup)
                continue
            if setup and setup.get("conviction") in ("HIGH", "MEDIUM"):
                selloff_setups.append({**setup, "pick": pick})
                print(
                    f"  Sell-off detected: {pick['ticker']} "
                    f"{setup['classification']} ({setup['conviction']})"
                )
        if selloff_setups:
            dip_count = await register_dip_buy_alerts(
                selloff_setups=selloff_setups,
                source="morning_brief",
                scan_date=scan_date,
                risk_regime=risk_regime,
                trading_mode=trading_mode,
                current_prices=current_prices,
            )
            print(f"  Registered {dip_count} multi-tranche dip-buy alerts", flush=True)

    # Step 4: Immediate Telegram for urgent TRIM/EXIT directives
    await send_immediate_position_directives(position_alerts, holdings=holdings)

    # Step 5: Conflict detection — defensive wins over offensive
    conflicts = await resolve_alert_conflicts(scan_date)
    if conflicts:
        print(f"  Resolved {conflicts} BUY/TRIM conflicts", flush=True)

    # Step 6: Cleanup orphan alerts — cancel alerts for tickers not in picks/holdings
    valid_tickers = {p["ticker"] for p in pre_computed_picks}
    if holdings:
        valid_tickers.update(slice_row["ticker"] for slice_row in holdings)
    orphans = await cleanup_orphan_alerts(scan_date, valid_tickers)
    if orphans:
        print(f"  Cleaned up {orphans} orphan alert(s)", flush=True)

    # Step 7: Volume cap — prevent alert fatigue
    max_daily_alerts = 15
    capped = await cap_daily_alerts(scan_date, max_daily_alerts)
    if capped:
        print(
            f"  Capped alerts: cancelled {capped} lowest-priority (max {max_daily_alerts}/day)",
            flush=True,
        )

    total = pick_alert_count + stop_alert_count + dip_count
    print(f"  Total alerts registered: {total} (after cap: {total - capped})", flush=True)
    return {
        "total": total,
        "picks": pick_alert_count,
        "stops": stop_alert_count,
        "dips": dip_count,
    }


async def _fetch_alert_prices(
    holdings: list[dict],
    pre_computed_picks: list[dict],
) -> dict[str, float]:
    """Fetch live prices for ALL tickers that might get alerts.

    Returns current_prices dict.
    Fail-closed (CLAUDE.md rule 16): tickers without price data get sentinel -1.0
    so anti-instant-trigger guards conservatively block those alerts.
    """
    # Start with holdings prices (always available) — one per (ticker, plan_type);
    # SWING takes precedence if both slices carry a price.
    current_prices: dict[str, float] = {}
    if holdings:
        for slice_row in holdings:
            ticker = slice_row.get("ticker")
            price = slice_row.get("current_price_vnd")
            if not ticker or not price:
                continue
            if slice_row.get("plan_type") == "SWING" or ticker not in current_prices:
                current_prices[ticker] = float(price)

    # Collect ALL tickers — holdings + picks
    all_alert_tickers: set[str] = set(current_prices.keys())
    for pick in pre_computed_picks:
        all_alert_tickers.add(pick["ticker"])

    # Fetch live prices for tickers we don't already have
    missing_tickers = [t for t in all_alert_tickers if t not in current_prices]
    if missing_tickers:
        try:
            from shared.api.prices import get_prices

            live_prices = await get_prices(missing_tickers, days=3)
            for ticker, price_data in live_prices.items():
                close = price_data.get("close")
                if close:
                    current_prices[ticker] = float(close)
            # Sentinel -1 for missing prices — guards treat as "already triggered"
            for ticker in missing_tickers:
                if ticker not in current_prices:
                    current_prices[ticker] = -1.0
                    logger.info(
                        "No price data for %s — alert guard will block (fail-closed)", ticker
                    )
            print(
                f"  Fetched live prices for {len(live_prices)}/{len(missing_tickers)} non-held tickers"
            )
        except Exception as exception:
            logger.warning("Failed to fetch live prices for alert tickers: %s", exception)
            for ticker in missing_tickers:
                current_prices[ticker] = -1.0
            logger.warning(
                "Set %d tickers to fail-closed (no alerts without prices)", len(missing_tickers)
            )

    return current_prices


async def run_phase5_alert_pipeline(
    position_alerts: dict,
    pre_computed_picks: list[dict],
    scan_date: date,
    global_risk_regime: RiskRegime,
    trading_mode: TradingMode,
    holdings: list[dict],
    skip_alerts: bool,
) -> None:
    """Phase 5 wrapper: fetch live prices for ALL alert tickers, then register alerts."""
    print("\n" + "=" * 60, flush=True)
    print("PHASE 5: Alert Registration", flush=True)
    print("=" * 60, flush=True)

    current_prices = await _fetch_alert_prices(holdings, pre_computed_picks)

    try:
        await run_alert_registration(
            position_alerts=position_alerts,
            pre_computed_picks=pre_computed_picks,
            scan_date=scan_date,
            risk_regime=global_risk_regime,
            trading_mode=trading_mode,
            current_prices=current_prices or None,
            holdings=holdings,
            skip_alerts=skip_alerts,
        )
    except Exception as e:
        # SWI-248: per-pick failures are already swallowed inside the
        # registrars (they `continue` on a bad pick), so anything escaping
        # run_alert_registration is a SYSTEMIC Phase-5 failure that would
        # otherwise collapse alerting to 0 rows while the pipeline stayed
        # green. Surface the span AND re-raise so the phase fails loudly.
        report_caught("phase_alerts", e)
        raise
