#!/usr/bin/env python3
"""Market close retrospective orchestrator.

Usage: python scripts/retrospective.py [--date YYYY-MM-DD]
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from shared.config import get_scan_date
from shared.database import Database, close_db
from shared.migration_guard import (
    MigrationDriftError,
    assert_no_pending_migrations,
    report_drift_and_exit,
)
from shared.observability import (
    configure_observability,
    emit_pipeline_health_summary,
    reset_health_counters,
    shutdown_observability,
    span,
)
from shared.portfolio_invariants import (
    PortfolioInvariantError,
    assert_no_dual_listed_tickers,
    report_invariant_and_exit,
)
from shared.session import init_session
from shared.telegram import send_telegram_error

# Initialize observability early (no-op if LOGFIRE_TOKEN not set)
configure_observability()
init_session("retro")

logger = logging.getLogger(__name__)

from agents import (  # noqa: E402
    evaluate_day_with_agent,
    evaluate_macro_for_day,
    evaluate_rotation_for_day,
    extract_patterns,
    generate_retro_with_agent,
)
from retro.data import (  # noqa: E402
    build_portfolio_prices,
    build_sector_map,
    fetch_eod_prices,
    load_midday_check,
    print_summary,
    save_retrospective_or_quarantine,
)
from retro_helpers import (  # noqa: E402
    generate_embeddings,
    load_learnings_from_db,
)
from retro_helpers.learnings import (  # noqa: E402
    update_learnings,
)
from shared.neon import (  # noqa: E402
    get_morning_recommendations,
    get_trades_for_date,
    insert_daily_record,
    insert_learnings,
    update_portfolio_prices,
    update_previous_day_change,
)
from shared.neon.insert_strategy_insights import insert_strategy_insights  # noqa: E402

# Configuration
RESEARCH_DIR = Path(__file__).parent.parent / "research"
from retro_helpers.learnings import ROLLING_WINDOW_DAYS


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run market close retrospective")
    parser.add_argument(
        "--date",
        default=get_scan_date(),
        help="Date to analyze (YYYY-MM-DD)",
    )
    args = parser.parse_args()
    asyncio.run(_main_async(args.date))


async def _main_async(today: str):
    """Async main to initialize database pool."""
    reset_health_counters()
    try:
        async with Database():
            from shared.trading_config import init_trading_config

            await assert_no_pending_migrations()
            await assert_no_dual_listed_tickers()
            await init_trading_config()
            from shared.rules.catalyst_override.geolabel import _validate_geo_factor_map_once

            await _validate_geo_factor_map_once()
            with span("retrospective_generation", date=today):
                await asyncio.wait_for(_run_retrospective(today), timeout=3600)
    except MigrationDriftError as drift:
        report_drift_and_exit(drift)
    except PortfolioInvariantError as exc:
        report_invariant_and_exit(exc)
    except TimeoutError:
        error_msg = "Retrospective timed out after 1 hour"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Retrospective failed: {e}"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    finally:
        emit_pipeline_health_summary(scan_date=today, phase="retro", logger=logger)
        await close_db()
        shutdown_observability()


async def _run_retrospective(today: str):
    """Run the retrospective analysis."""
    print(f"\n{'=' * 60}")
    print(f"Market Close Retrospective - {today}")
    print(f"{'=' * 60}\n")

    # SWI-64: surface stale active catalysts. Monitor only — never crashes
    # retro. Upstream fix is the all-checked-keys UPDATE in
    # catalyst_news_check.save_catalyst_news_signals.
    try:
        from shared.neon.catalysts import assert_catalyst_freshness

        stale_rows = await assert_catalyst_freshness(max_age_days=2)
        if stale_rows:
            logger.warning(
                "catalyst_freshness: %d active catalysts with last_updated > 2d (keys=%s)",
                len(stale_rows),
                [row["catalyst_key"] for row in stale_rows[:10]],
            )
    except Exception as freshness_exc:
        logger.warning("catalyst_freshness check failed: %s", freshness_exc)

    from shared.env import is_dry_run

    if not os.environ.get("OPENROUTER_API_KEY") and not is_dry_run():
        print("Error: OPENROUTER_API_KEY not set")
        sys.exit(1)

    scan_date = datetime.strptime(today, "%Y-%m-%d").date()

    # Step 1: Load recommendations
    print("Step 1: Loading recommendations from database...")
    recommendations = await get_morning_recommendations(scan_date)
    if not recommendations:
        print("  Warning: No recommendations found (morning brief may not have run)")

    # Step 1.5: Load strategy directive
    print("\nStep 1.5: Loading strategy directive...")
    strategy_directive = None
    try:
        from shared.neon.directives import get_strategy_directive

        strategy_directive = await get_strategy_directive(scan_date)
        if strategy_directive:
            print(f"  Loaded directive ({len(strategy_directive['directive'])} chars)")
        else:
            print("  No directive found for today")
    except Exception as e:
        print(f"  Directive load error: {e}")

    # Step 2: Load midday check
    print("\nStep 2: Loading midday check...")
    midday_data = await load_midday_check(today)
    if midday_data:
        print(f"  Midday entries hit: {len(midday_data.get('entries_hit', []))}")
    else:
        print("  No midday check found (will evaluate morning only)")

    # Step 3: Fetch EOD prices (returns holdings+watchlist to avoid double queries)
    print("\nStep 3: Fetching EOD prices...")
    eod_prices, holdings, watchlist = await fetch_eod_prices(today)
    if not eod_prices:
        print("  Warning: No EOD prices available")
    elif holdings:
        portfolio_prices = build_portfolio_prices(holdings, eod_prices)
        if portfolio_prices:
            updated = await update_portfolio_prices(portfolio_prices)
            print(f"  Updated {updated} portfolio holdings prices")

    # Step 3.5: Match trades to alerts (alert effectiveness loop)
    print("\nStep 3.5: Matching trades to alerts...")
    try:
        from agents.tools.alert_tracking import match_trades_to_alerts

        matched = await match_trades_to_alerts(scan_date)
        if matched:
            print(f"  Matched {matched} alerts to trades")
        else:
            print("  No alert-to-trade matches (no triggered alerts or trades today)")
    except Exception as e:
        print(f"  Alert matching error (non-fatal): {e}")

    # Step 3.6 + 3.7: Evaluate sector rotation and macro regime concurrently
    print("\nStep 3.6-3.7: Evaluating sector rotation and macro regime...")
    rotation_eval, macro_eval = await asyncio.gather(
        evaluate_rotation_for_day(scan_date, eod_prices),
        evaluate_macro_for_day(scan_date, eod_prices, date_dir=RESEARCH_DIR / today),
    )
    if rotation_eval:
        print(f"  Hot sectors: {rotation_eval.get('hot_sectors', [])}")
        print(f"  Rotation effective: {rotation_eval.get('rotation_effective', False)}")
    if macro_eval:
        print(f"  Regime: {macro_eval['global_risk_regime']}")
        print(f"  Appropriate: {macro_eval.get('regime_appropriate', 'N/A')}")

    # Step 3.8: Update previous day's next_day_change
    print("\nStep 3.8: Updating previous day's next_day_change...")
    vn_change_pct = macro_eval.get("vn_index_change_pct") if macro_eval else None
    if vn_change_pct is not None:
        await update_previous_day_change(scan_date, vn_change_pct)
    else:
        print("  Skipped: No VN-Index change estimate available")

    # Step 3.9: Score mature agent beliefs
    print("\nStep 3.9: Scoring mature agent beliefs...")
    try:
        from agents.retro.belief_scoring import resolve_mature_beliefs

        scoring_result = await resolve_mature_beliefs(scan_date)
        print(
            f"  Resolved {scoring_result.resolved}/{scoring_result.unresolved_found} mature beliefs"
        )
        if scoring_result.skipped_missing_outcome_price:
            print(f"  Skipped (no outcome price): {scoring_result.skipped_missing_outcome_price}")
        if scoring_result.skipped_missing_entry_price:
            print(f"  Skipped (no entry price): {scoring_result.skipped_missing_entry_price}")
        if scoring_result.skipped_not_yet_mature:
            print(f"  Skipped (not yet mature): {scoring_result.skipped_not_yet_mature}")
    except Exception as e:
        logger.warning("Failed to resolve beliefs: %s", e)

    # Step 3.95: Fetch executed trades for the day
    print("\nStep 3.95: Fetching executed trades...")

    trades_for_date = await get_trades_for_date(scan_date)
    closed_trades = trades_for_date.get("closed") or []
    if closed_trades:
        closed_tickers = list({trade["ticker"] for trade in closed_trades})
        print(f"  Found {len(closed_trades)} closed trades: {closed_tickers}")
    else:
        print("  No closed trades today")

    # Step 4: Evaluate day (Agentic)
    print("\nStep 4: Evaluating day (Agentic)...")
    evaluations = await evaluate_day_with_agent(
        recommendations,
        eod_prices,
        scan_date,
        midday_data=midday_data,
        holdings=holdings,
        closed_trades=closed_trades,
    )

    # Step 4.5: Enrich evaluations with ATR-based calibration metrics
    print("\nStep 4.5: Enriching evaluations with ATR calibration...")
    from agents.retro.calibration import enrich_evals_with_atr

    with span("retro_atr_enrichment"):
        await enrich_evals_with_atr(evaluations.get("evaluations", []), scan_date)
    enriched = sum(
        1 for e in evaluations.get("evaluations", []) if e.get("stop_vs_atr_ratio") is not None
    )
    print(f"  Enriched {enriched} entry evaluations with ATR data")

    # Step 4.7: Resolve PENDING evaluations from prior days
    print("\nStep 4.7: Resolving PENDING evaluations over holding period...")
    try:
        from agents.retro.resolve_pending import resolve_pending_evaluations
        from shared.api.prices import get_ohlc_series
        from shared.neon.pending_evals import (
            batch_update_evaluation_status,
            get_pending_evaluations,
        )

        pending = await get_pending_evaluations(scan_date, lookback_days=7)
        if pending:
            pending_tickers = list({p["ticker"] for p in pending})
            price_data = await get_ohlc_series(
                pending_tickers,
                start=(scan_date - timedelta(days=10)).strftime("%Y-%m-%d"),
                end=scan_date.strftime("%Y-%m-%d"),
            )

            # Filter prices per eval: only days AFTER the recommendation date
            filtered_prices: dict[str, list[dict]] = {}
            for evaluation in pending:
                rec_date_str = str(evaluation.get("record_date", ""))[:10]
                ticker = evaluation["ticker"]
                after = [p for p in price_data.get(ticker, []) if p["date"] > rec_date_str]
                if after:
                    filtered_prices[ticker] = after

            resolutions = resolve_pending_evaluations(pending, filtered_prices)
            if resolutions:
                await batch_update_evaluation_status(resolutions)
            print(f"  Resolved {len(resolutions)} of {len(pending)} PENDING evaluations")
        else:
            print("  No PENDING evaluations found")
    except Exception as resolve_error:
        logger.warning("PENDING resolution failed (non-fatal): %s", resolve_error)

    # Step 5: Extract patterns
    print("\nStep 5: Extracting patterns from history...")
    learnings = await load_learnings_from_db()
    temp_record = {
        "date": today,
        "recommendations": recommendations,
        "evaluations": evaluations.get("evaluations", []),
        "day_summary": evaluations.get("day_summary", {}),
    }
    sector_map = build_sector_map(watchlist) if watchlist else {}

    # Filter today's record to avoid duplicate when retro re-runs (today already in DB)
    historical_records = [r for r in learnings.get("daily_records", []) if r["date"] != today]
    records_for_patterns = historical_records + [temp_record]
    patterns = await extract_patterns(
        records_for_patterns,
        ROLLING_WINDOW_DAYS,
        sector_map=sector_map,
        scan_date=today,
    )

    # Step 5.1: Update and persist learnings with today's data
    print("\nStep 5.1: Updating learnings file...")
    learnings = update_learnings(
        learnings,
        today,
        recommendations,
        evaluations,
        patterns,
        midday_data=midday_data,
        rotation_eval=rotation_eval,
        macro_eval=macro_eval,
    )
    print(f"  Learnings updated: {len(learnings['daily_records'])} day(s) in rolling window")

    # Step 5.5: Persist actionable rules to trading_rules table
    print("\nStep 5.5: Persisting actionable rules to DB...")
    try:
        from agents.retro.patterns import persist_actionable_rules

        rules_count = await persist_actionable_rules(patterns.get("actionable_rules", []))
        if not rules_count:
            print("  No actionable rules to persist (sample size or threshold not met)")
    except Exception as e:
        print(f"  Rule persistence error (non-fatal): {e}")

    # Step 5.6: Detect 0-BUY streak deterministically + persist for next AM
    print("\nStep 5.6: Detecting 0-BUY streak...")
    from agents.retro.streak import assert_streak_fetch_nonempty, detect_zero_buy_streak
    from shared.database import get_db
    from shared.neon.streak_alert import upsert_streak_alert

    streak_alert = None
    # Deterministic BUY count for scan_date — extracted from the same
    # streak_rows fetch and threaded into the retro generator as a
    # cite-verbatim fact (Bug 1, run2 2026-05-14). Stays None if the
    # streak fetch below throws (try/except is non-fatal).
    buy_rec_count: int | None = None

    # detect_zero_buy_streak TRIGGERS on the last 5 trading days but MEASURES
    # streak length over `_LENGTH_LOOKBACK_DAYS`=30 (SWI-93 decoupled the
    # trigger window from the length measurement). Bound the scan to >=30 rows
    # DESC and reverse, so the length window is never truncated — a LIMIT below
    # 30 silently caps the reported streak length (SWI-346).
    db = await get_db()
    streak_rows: list = []
    fetch_failed = False
    try:
        streak_rows = await db.fetch_all(
            """
            SELECT record_date, buy_rec_count, buy_signal_count, market_regime
            FROM daily_records
            WHERE record_date <= $1
            ORDER BY record_date DESC
            LIMIT 30
            """,
            scan_date,
        )
    except Exception as e:
        # A fetch EXCEPTION (e.g. transient DB error) stays non-fatal — legacy
        # behavior: a streak hiccup must not kill the whole retro.
        logger.warning("Streak fetch failed (non-fatal): %s", e)
        fetch_failed = True

    # SWI-374: a SUCCESSFUL fetch returning 0 rows for a date that should have a
    # record is a daily_records gap — fail loud. But a genuinely empty table
    # (bootstrap / reseed / backfill) is not a gap, so check whether any rows
    # exist before raising (avoids aborting the whole retro on an empty-table
    # day — the over-conservative failure the asymmetry rule disfavors).
    table_has_rows = True
    if not fetch_failed and len(streak_rows) == 0:
        try:
            table_has_rows = bool(await db.fetch_val("SELECT 1 FROM daily_records LIMIT 1"))
        except Exception as count_exc:
            logger.warning("daily_records existence probe failed (non-fatal): %s", count_exc)
            table_has_rows = False
    assert_streak_fetch_nonempty(
        streak_rows,
        scan_date=scan_date,
        fetch_failed=fetch_failed,
        table_has_rows=table_has_rows,
    )

    try:
        buy_rec_count = next(
            (r["buy_rec_count"] for r in streak_rows if r["record_date"] == scan_date),
            None,
        )
        streak_alert = detect_zero_buy_streak([dict(r) for r in reversed(streak_rows)])
        if streak_alert:
            print(
                f"  Streak detected: length={streak_alert.length} "
                f"profile={streak_alert.gate_profile} since={streak_alert.start_date}"
            )
            await upsert_streak_alert(scan_date, streak_alert.to_jsonb())
        else:
            await upsert_streak_alert(scan_date, None)
            print("  No streak detected")
    except Exception as e:
        logger.warning("Streak detection failed (non-fatal): %s", e)

    # Step 6: Generate retrospective (Agentic)
    print("\nStep 6: Generating retrospective (Agentic)...")
    retro_content = await generate_retro_with_agent(
        recommendations,
        evaluations,
        patterns,
        midday_data=midday_data,
        strategy_directive=strategy_directive,
        streak_alert=streak_alert.to_jsonb() if streak_alert else None,
        scan_date=scan_date,
        buy_rec_count=buy_rec_count,
    )

    print("\nStep 7: Saving outputs...")
    save_retrospective_or_quarantine(retro_content, evaluations, today, RESEARCH_DIR)

    # Step 9: Insert to database
    print("\nStep 9: Inserting to database...")
    # Don't override morning's reconciled market_regime — pass None so COALESCE preserves it
    market_regime_str = None

    daily_record_data = {
        "market_regime": market_regime_str,
        "trading_mode": evaluations.get("trading_mode"),
        "midday_data": midday_data,
        "recommendations": recommendations,
        "evaluations": evaluations.get("evaluations", []),
        "day_summary": evaluations.get("day_summary", {}),
        "midday_summary": evaluations.get("midday_summary", {}),
        "mode_compliance": evaluations.get("mode_compliance", True),
        "mode_violations": evaluations.get("mode_violations", []),
        "rotation_evaluation": rotation_eval,
        "macro_evaluation": macro_eval,
    }
    # Gather independent DB inserts
    record_ok, learnings_ok, strategy_ok = await asyncio.gather(
        insert_daily_record(scan_date, daily_record_data),
        insert_learnings(learnings),
        insert_strategy_insights(learnings.get("strategy_patterns", {}), scan_date),
    )
    if record_ok:
        print("  DB: daily record inserted")
    if learnings_ok:
        print("  DB: learnings updated")
    if strategy_ok:
        print("  DB: strategy insights updated")

    # Step 10: Generate embeddings
    print("\nStep 10: Generating embeddings...")
    await generate_embeddings(scan_date, rotation_eval, macro_eval, midday_data)

    print(f"\n{'=' * 60}")
    print("Retrospective complete!")
    print(f"{'=' * 60}\n")

    print_summary(evaluations, recommendations, midday_data, rotation_eval, macro_eval)

    if evaluations.get("quarantined_draft"):
        sys.exit(2)  # SWI-255 fail-loud after DB writes


if __name__ == "__main__":
    main()
