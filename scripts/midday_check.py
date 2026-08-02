#!/usr/bin/env python3
"""
Midday Market Check Script

Runs at 12:00 PM Vietnam time (market break) to:
1. Load morning brief recommendations
2. Fetch midday prices
3. Compare morning entries vs current prices
4. Generate afternoon action plan with trading mode awareness

Usage:
    python scripts/midday_check.py [--date YYYY-MM-DD]
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from shared.config import get_scan_date
from shared.observability import (
    configure_observability,
    emit_pipeline_health_summary,
    log_info,
    log_warn,
    reset_health_counters,
    shutdown_observability,
    span,
)
from shared.session import init_session

# Initialize observability early (no-op if LOGFIRE_TOKEN not set)
configure_observability()
init_session("midday")

from agents import run_midday_check_async
from agents.tools.portfolio import get_cash_balance_async, get_holdings_async
from agents.trading_mode import determine_mode
from midday.formatter import (
    generate_midday_markdown,
    save_midday_check,
    validate_midday_markdown,
)
from midday.helpers import (
    compute_big_movers,
    compute_entries_hit,
    compute_position_alerts,
    fetch_midday_prices,
)
from shared.database import Database
from shared.migration_guard import (
    MigrationDriftError,
    assert_no_pending_migrations,
    report_drift_and_exit,
)
from shared.neon import insert_midday_check
from shared.portfolio_invariants import (
    PortfolioInvariantError,
    assert_no_dual_listed_tickers,
    report_invariant_and_exit,
)
from shared.telegram import send_telegram, send_telegram_error

logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run midday market check")
    parser.add_argument(
        "--date",
        default=get_scan_date(),
        help="Date to analyze (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    today = args.date

    reset_health_counters()
    try:
        asyncio.run(asyncio.wait_for(_run_midday_check_async(today), timeout=3600))
    except MigrationDriftError as drift:
        report_drift_and_exit(drift)
    except PortfolioInvariantError as exc:
        report_invariant_and_exit(exc)
    except TimeoutError:
        error_msg = "Midday check timed out after 1 hour"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Midday check failed: {e}"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    finally:
        emit_pipeline_health_summary(scan_date=today, phase="midday", logger=logger)
        shutdown_observability()


async def _run_midday_check_async(today: str):
    """Run the midday check analysis (async)."""
    print(f"\n{'=' * 60}")
    print(f"Midday Market Check - {today}")
    print(f"{'=' * 60}\n")

    from shared.env import is_dry_run

    if not os.environ.get("OPENROUTER_API_KEY") and not is_dry_run():
        await asyncio.to_thread(send_telegram_error, "Midday check: OPENROUTER_API_KEY not set")
        print("Error: OPENROUTER_API_KEY not set")
        return

    with span("midday_check", date=today):
        async with Database():
            from shared.trading_config import init_trading_config

            await assert_no_pending_migrations()
            await assert_no_dual_listed_tickers()
            await init_trading_config()
            from shared.rules.catalyst_override.geolabel import _validate_geo_factor_map_once

            await _validate_geo_factor_map_once()
            scan_date = datetime.strptime(today, "%Y-%m-%d").date()

            # Step 1: Load morning recommendations + holdings + position alerts.
            # Holdings + alerts are loaded BEFORE the rec-empty branch so a
            # zero-rec day can still drive catastrophic-floor monitoring.
            print("Step 1: Loading morning recommendations + holdings + alerts...")
            from shared.neon.insert_records import get_morning_recommendations
            from shared.neon.position_alerts import get_morning_position_alerts

            recommendations, holdings_data, morning_position_alerts = await asyncio.gather(
                get_morning_recommendations(scan_date),
                get_holdings_async(),
                get_morning_position_alerts(scan_date),
            )
            holdings = holdings_data.get("holdings") or []

            if not recommendations:
                if not holdings and not morning_position_alerts:
                    # Full skip: no recs, no holdings, no alerts → nothing to monitor.
                    print(
                        f"  Midday {today}: No morning recommendations found — "
                        "skipping (nothing to monitor)"
                    )
                    # Belt-and-suspenders alerting — emit alertable logfire
                    # warning independent of the Telegram credential chain.
                    log_warn(
                        "midday_skip",
                        reason="no_morning_recs",
                        date=str(today),
                    )
                    # Neutral 'did-not-run' signal (SWI-235) — NOT a red error.
                    await asyncio.to_thread(
                        _notify_midday_skipped,
                        today,
                        reason="no morning recommendations found",
                        monitoring_ran=False,
                    )
                    # Write a skip-stub markdown so downstream midday_notify
                    # has something to load + publish. Without this, the notify
                    # step crashes with "Midday check not found" and the whole
                    # workflow fails silently (MON-2026-04-16-001).
                    _write_midday_skip_stub(
                        today, reason="no_morning_recs", entry_checks_skipped=False
                    )
                    return

                # Reduced-monitoring path — entry checks skipped, but holdings
                # still need catastrophic-floor / urgent-EXIT enforcement and
                # midday-price refresh. FPT-class incident: a 0-rec day must
                # not silence floor breaches on existing positions.
                print(
                    f"  No morning recs, but {len(holdings)} holdings + "
                    f"{len(morning_position_alerts)} alerts — running reduced monitoring"
                )
                log_warn(
                    "midday_reduced",
                    reason="no_morning_recs_but_holdings",
                    holdings_n=len(holdings),
                    alerts_n=len(morning_position_alerts),
                    date=str(today),
                )
                await _run_reduced_monitoring(
                    today=today,
                    scan_date=scan_date,
                    holdings=holdings,
                    morning_position_alerts=morning_position_alerts,
                )
                # Neutral 'did-not-run' signal (SWI-235) — entry checks were
                # skipped but holdings risk enforcement ran; not a failure.
                await asyncio.to_thread(
                    _notify_midday_skipped,
                    today,
                    reason="no morning recommendations — monitoring-only run",
                    monitoring_ran=True,
                )
                _write_midday_skip_stub(
                    today,
                    reason="no_morning_recs_monitoring_only",
                    entry_checks_skipped=True,
                )
                return
            print(f"  Loaded {len(recommendations)} recommendations from DB")

            # Step 3: Fetch midday prices
            print("\nStep 3: Fetching midday prices...")
            midday_prices = await fetch_midday_prices(today, get_holdings_async)
            if not midday_prices:
                logger.warning(
                    "No midday prices available for %s — continuing with empty prices", today
                )

            # Step 3.5+4: Load strategy directive, cash, catalysts concurrently
            # (holdings_data + morning_position_alerts already loaded above).
            print("\nStep 3.5+4: Loading context and pre-computing...")
            from shared.neon.catalyst_summaries import (
                get_capital_events_summary,
                get_filtered_catalyst_summary,
            )
            from shared.neon.directives import get_strategy_directive

            (
                strategy_directive,
                cash_data,
                catalyst_text,
                events_text,
            ) = await asyncio.gather(
                get_strategy_directive(scan_date),
                get_cash_balance_async(),
                get_filtered_catalyst_summary(),
                get_capital_events_summary(),
            )

            if strategy_directive:
                print(f"  Loaded directive ({len(strategy_directive['directive'])} chars)")
            if morning_position_alerts:
                print(f"  Loaded {len(morning_position_alerts)} structured position alerts from DB")

            # Build catalyst context from gathered results
            catalyst_context = _build_catalyst_context(catalyst_text, events_text)

            # Fetch geo shock + held technicals concurrently (both independent of each other)
            from agents.tools.geopolitical import build_geopolitical_context
            from shared.api.technicals import get_technicals
            from shared.neon import tickers_held
            from shared.neon.catalyst_summaries import get_active_geopolitical_shock

            held_tickers = tickers_held(holdings_data.get("holdings") or [])

            async def _fetch_held_technicals():
                return await get_technicals(held_tickers) if held_tickers else {}

            geo_shock, held_technicals = await asyncio.gather(
                get_active_geopolitical_shock(),
                _fetch_held_technicals(),
            )

            geopolitical_context = build_geopolitical_context(geo_shock)
            if geopolitical_context:
                print(
                    f"  Geopolitical shock active: {(geo_shock.get('phase_name') if geo_shock else None) or 'unknown'}"
                )
                catalyst_context = (
                    geopolitical_context + "\n\n" + catalyst_context
                    if catalyst_context
                    else geopolitical_context
                )

            from shared.rules.max_loss import (
                compute_ceiling_breaches,
                format_breaches_for_agent,
            )
            from shared.trading_config import get_trading_config

            cfg = get_trading_config()
            breaches = await compute_ceiling_breaches(cfg)
            max_loss_context = format_breaches_for_agent(breaches)

            precomputed = {
                "deployable_cash": cash_data.get("deployable", 0),
                "entries_hit": compute_entries_hit(recommendations, midday_prices),
                "big_movers": compute_big_movers(
                    midday_prices,
                    holdings_tickers=held_tickers,
                ),
                "position_alerts": compute_position_alerts(recommendations, midday_prices),
                "morning_position_alerts": morning_position_alerts,
                "strategy_directive": strategy_directive,
                "catalyst_context": catalyst_context,
                "max_loss_context": max_loss_context,
                "max_loss_breaches": [
                    {
                        "ticker": breach.ticker,
                        "plan_type": breach.plan_type,
                        "loss_pct": breach.loss_pct,
                        "ceiling_pct": breach.ceiling_pct,
                    }
                    for breach in breaches
                ],
                "held_technicals": held_technicals,
            }
            print(f"  Entries hit: {len(precomputed['entries_hit'])}")
            print(f"  Big movers: {len(precomputed['big_movers'])}")
            print(f"  Alerts: {len(precomputed['position_alerts'])}")

            # Step 5: Run midday analysis (LLM for qualitative only)
            print("\nStep 5: Running midday analysis (Agentic)...")
            computed_trading_mode = determine_mode(cash_data.get("deployable", 0))

            from pipeline.context_blocks import format_portfolio_block
            from pipeline.context_blocks_calibration import (
                format_executed_trades_block,
                format_learnings_block,
                format_midday_prices_block,
                format_trades_block,
            )

            portfolio_context = format_portfolio_block(
                holdings_data.get("holdings") or [],
                cash_data.get("total_cash", 0),
                cash_data.get("deployable", 0),
            )

            # Pre-fetch data for injection (replaces midday agent tool calls)
            from agents.tools.portfolio import get_recent_trades_async, get_trades_for_date_async
            from agents.tools.portfolio_learnings import get_learnings_async

            _trades_result, _executed_result, _learnings_result = await asyncio.gather(
                get_recent_trades_async(limit=5),
                get_trades_for_date_async(scan_date),
                get_learnings_async(query="midday_insights"),
            )
            recent_trades_context = format_trades_block(
                _trades_result.get("prose") or str(_trades_result)
            )
            executed_trades_context = format_executed_trades_block(
                _executed_result.get("prose") or str(_executed_result)
            )
            midday_prices_context = format_midday_prices_block(midday_prices or {})

            # Format midday learnings (direct DB fetch — midday pipeline
            # runs separately from morning, no enrichment_loader available)
            learnings_context = ""
            if _learnings_result and not _learnings_result.get("error"):
                learnings_context = format_learnings_block(
                    {"midday_insights": _learnings_result}, ["midday_insights"]
                )

            result = await run_midday_check_async(
                recommendations,
                scan_date,
                midday_prices,
                precomputed,
                trading_mode=computed_trading_mode,
                portfolio_context=portfolio_context,
                recent_trades_context=recent_trades_context,
                executed_trades_context=executed_trades_context,
                midday_prices_context=midday_prices_context,
                learnings_context=learnings_context,
                holdings=holdings_data.get("holdings") or [],
            )
            result["trading_mode"] = computed_trading_mode  # safety override

            # Step 6: Save outputs
            print("\nStep 6: Saving outputs...")
            markdown_content = generate_midday_markdown(result, today)
            # Section-count gate (SWI-235): warn on a degenerate render so a
            # malformed full-analysis run is distinguishable from a skip-stub.
            # Advisory only — we still publish (exit-0 policy).
            section_warnings = validate_midday_markdown(markdown_content)
            for warning in section_warnings:
                logger.error("Midday output validation: %s", warning)
            save_midday_check(markdown_content, today)

            # Step 7: Insert to database
            print("\nStep 7: Inserting to database...")
            if await insert_midday_check(scan_date, result):
                print("  DB: midday check inserted")
            else:
                logger.error(f"Midday DB insert failed for {scan_date}")
                send_telegram_error(
                    f"Midday DB insert failed for {scan_date} — retro will have missing midday data"
                )

            # Step 8: Register midday alerts
            print("\nStep 8: Registering midday alerts...")
            await _register_midday_alerts(result, scan_date)

            # Step 9: Catalyst news check (flag spikes for strategy revision)
            print("\nStep 9: Catalyst news check...")
            await _check_catalyst_news(scan_date)

    print(f"\n{'=' * 60}")
    print("Midday check complete!")
    print(f"{'=' * 60}\n")

    print("Summary:")
    print(f"  - Trading Mode: {result['trading_mode']}")
    print(f"  - Entries Hit: {len(result.get('entries_hit', []))}")
    print(f"  - Big Movers: {len(result.get('big_movers', []))}")
    print(f"  - Position Alerts: {len(result.get('position_alerts', []))}")


def _notify_midday_skipped(
    today: str,
    *,
    reason: str,
    monitoring_ran: bool,
) -> None:
    """Emit a NEUTRAL 'did-not-run' signal — distinct from a failure (SWI-235).

    A 0-rec midday is an expected, non-failing state (the morning brief
    legitimately produced no entries). Surfacing it via ``send_telegram_error``
    painted the run red and conflated "skipped on purpose" with "crashed".
    Here we emit a neutral Telegram note + a logfire span so the operator can
    tell the two apart. Never raises: a Telegram credential gap degrades to a
    log line, mirroring midday_notify.py's exit-0 policy (MON-2026-04-16-001).
    """
    monitoring_note = (
        "reduced monitoring ran (holdings floor + EXIT enforcement)"
        if monitoring_ran
        else "nothing to monitor (no holdings or alerts)"
    )
    with span(
        "midday_skipped",
        date=str(today),
        reason=reason,
        monitoring_ran=monitoring_ran,
    ):
        log_info(
            "midday_skipped",
            reason=reason,
            monitoring_ran=monitoring_ran,
            date=str(today),
        )
        try:
            send_telegram(
                f"<b>MIDDAY SKIPPED — {today}</b>\n\n{reason}\n{monitoring_note}",
                parse_mode="HTML",
            )
        except Exception as exc:  # noqa: BLE001 — neutral signal must never fail the run
            print(f"  Neutral skip notification could not send (non-fatal): {exc}")


def _write_midday_skip_stub(
    today: str,
    *,
    reason: str,
    entry_checks_skipped: bool,
) -> None:
    """Write a skip-stub `midday-check.md` when the check cannot run.

    Keeps the downstream notify step + commit step working by giving
    them a file to publish, and gives the reader an audit trail of why
    midday did not run. Replaces the MON-2026-04-16-001 cascade failure
    where 0-rec → no markdown → notify crash → silent workflow failure.

    `entry_checks_skipped` records whether the reduced-monitoring path
    ran (holdings checked, entry decisions deferred) vs full skip
    (nothing checked).
    """
    research_dir = Path(__file__).parent.parent / "research" / today
    research_dir.mkdir(parents=True, exist_ok=True)
    stub_path = research_dir / "midday-check.md"
    from midday.formatter import _midday_sentinel

    monitoring_note = (
        "Holdings monitoring ran (catastrophic-floor + urgent-EXIT directives). "
        "Entry decisions skipped because no morning recommendations existed.\n\n"
        if entry_checks_skipped
        else "No monitoring ran — no holdings or alerts present.\n\n"
    )
    body = (
        f"# Midday Check Skipped - {today}\n\n"
        f"No full midday analysis was produced for {today}.\n\n"
        f"Reason: `{reason}`\n\n"
        f"{monitoring_note}"
        "Possible causes:\n"
        "- Morning brief produced 0 recommendations (check `daily_records.buy_rec_count`)\n"
        "- Morning scan failed (check `daily-scan.yml` run status)\n"
        "- Database write-path failure in morning pipeline\n\n"
        f"Generated: {datetime.utcnow().isoformat()}Z\n"
        f"Entry checks skipped: {entry_checks_skipped}\n"
        "Trace: `midday_check._write_midday_skip_stub`\n"
    ) + _midday_sentinel(today)
    tmp_path = stub_path.with_suffix(stub_path.suffix + ".tmp")
    tmp_path.write_text(body, encoding="utf-8")
    os.replace(tmp_path, stub_path)
    print(f"  Wrote midday skip stub → {stub_path}")


async def _run_reduced_monitoring(
    *,
    today: str,
    scan_date,
    holdings: list[dict],
    morning_position_alerts: list[dict],
) -> None:
    """Refresh midday prices, enforce catastrophic-floor breaches, and forward
    urgent morning EXIT/TRIM alerts on a no-rec day.

    Called only on the reduced-monitoring branch. Entry decisions are skipped;
    holdings-side risk enforcement still runs so a -15% LONGTERM holding does
    not go unwatched on days with zero BUYs.
    """
    from shared.rules.max_loss import compute_ceiling_breaches
    from shared.trading_config import get_trading_config

    midday_prices = await fetch_midday_prices(today, get_holdings_async)
    if not midday_prices:
        logger.warning("Reduced-monitoring: no midday prices available for %s", today)

    cfg = get_trading_config()
    breaches = await compute_ceiling_breaches(cfg)
    breach_alerts = [breach.to_alert_dict() for breach in breaches]

    combined_alerts = breach_alerts + list(morning_position_alerts)
    if not combined_alerts:
        return

    from agents.alert_registrar import send_immediate_position_directives

    await send_immediate_position_directives(
        {"alerts": combined_alerts}, holdings=holdings, scan_date=scan_date
    )
    print(
        f"  Sent {len(breach_alerts)} catastrophic-floor + "
        f"{len(morning_position_alerts)} morning directives"
    )


def _build_catalyst_context(catalyst_text: str | None, events_text: str | None) -> str | None:
    """Assemble catalyst context from individual summaries."""
    parts = []
    if catalyst_text:
        parts.append("ACTIVE CATALYSTS\n" + catalyst_text)
    if events_text and events_text != "No upcoming capital events tracked.":
        parts.append("CAPITAL EVENTS\n" + events_text)
    if parts:
        ctx = "\n\n".join(parts)
        print(f"  Loaded catalyst context ({len(ctx)} chars)")
        return ctx
    return None


async def _register_midday_alerts(result: dict, scan_date) -> None:
    """Send urgent directives and cancel overridden tickers.

    Morning alerts survive all day (lifecycle fix respects expires_at).
    Non-urgent midday items no longer get separate price alerts — LLM registrar
    had 0% trigger rate.
    """
    try:
        from agents.alert_registrar import send_immediate_position_directives

        position_alerts_dict = {"alerts": result.get("position_alerts", [])}

        # Send urgent TRIM/EXIT directives immediately via Telegram
        await send_immediate_position_directives(position_alerts_dict, scan_date=scan_date)

        # Cancel active alerts for CANCEL-overridden tickers
        overrides = result.get("recommendation_overrides") or []
        cancel_tickers = [
            o["ticker"]
            for o in overrides
            if isinstance(o, dict) and o.get("midday_status") == "CANCEL"
        ]
        if cancel_tickers:
            from shared.neon.alerts import cancel_alerts_for_tickers

            cancelled_count = await cancel_alerts_for_tickers(cancel_tickers)
            print(
                f"  Cancelled {cancelled_count} alerts for CANCEL tickers: "
                f"{', '.join(cancel_tickers)}"
            )
    except Exception as e:
        print(f"  Alert registration error: {e}")


async def _check_catalyst_news(scan_date) -> None:
    """Run catalyst news check and persist signals.

    Flags spikes for the standalone catalyst_check.py to pick up —
    midday pipeline does NOT trigger strategy revision directly
    (different purpose: portfolio review vs news reaction).
    """
    try:
        from pipeline.catalyst_news_check import check_catalyst_news, save_catalyst_news_signals

        signals, match_method, checked_keys = await check_catalyst_news(scan_date)
        if signals or checked_keys:
            saved = await save_catalyst_news_signals(
                signals, scan_date, match_method, checked_keys=checked_keys
            )
            spike_count = sum(1 for s in signals if s["is_spike"])
            print(
                f"  Catalyst news: {len(signals)} signals ({spike_count} spikes), "
                f"{saved} saved, {len(checked_keys)} refreshed [{match_method}]"
            )
            if spike_count > 0:
                print("  ⚡ Spike detected — catalyst_check.py will handle revision")
        else:
            print("  No catalyst-article matches found")
    except Exception as exc:
        logger.warning("Catalyst news check failed (non-critical): %s", exc)


if __name__ == "__main__":
    main()
