#!/usr/bin/env python3
"""
Catalyst Check — Intraday catalyst spike detection and strategy revision.

Runs 3x/day (10 AM, 1:30 PM, 3 PM Vietnam) to detect breaking catalyst
news that the morning scan didn't account for. If a spike is detected
during active trading hours, triggers a lightweight strategy revision
that re-runs only the entry strategist with updated catalyst context.

Usage:
    python scripts/catalyst_check.py [--date YYYY-MM-DD]

Architecture:
    1. Detect catalyst spike (updated_at > morning scan timestamp)
    2. Check catalyst news matches (articles vs catalyst keywords)
    3. If spike detected during active hours → run strategy revision
    4. If outside active hours → persist signal for next morning
    5. If no spike → exit early (no LLM call wasted)
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from shared.config import get_scan_date
from shared.observability import configure_observability, log_info, shutdown_observability, span
from shared.session import init_session

configure_observability()
init_session("catalyst_check")

from pipeline.catalyst_news_check import check_catalyst_news, save_catalyst_news_signals
from pipeline.catalyst_news_refresh import refresh_news
from pipeline.phase_catalyst_revision import run_strategy_revision
from shared.database import Database, get_db
from shared.neon.catalyst_signals import detect_catalyst_spike, mark_scan_revision_completed
from shared.neon.catalysts import refresh_catalyst_lifecycle
from shared.neon.narratives import (
    refresh_all_conviction_scores,
    refresh_narrative_maturity,
    refresh_related_catalysts,
)
from shared.telegram import send_telegram_error
from shared.trading_config import init_trading_config

logger = logging.getLogger(__name__)

# Vietnam active trading hours in UTC (UTC+7)
# 9:00 AM - 14:30 PM VN = 02:00 - 07:30 UTC
_ACTIVE_START_HOUR_UTC = 2
_ACTIVE_END_HOUR_UTC = 8  # exclusive: hour < 8 covers up to 07:59 UTC


def _is_active_hours() -> bool:
    """Check if current time is within Vietnam trading hours (UTC)."""
    now = datetime.now(UTC)
    return _ACTIVE_START_HOUR_UTC <= now.hour < _ACTIVE_END_HOUR_UTC


async def _refresh_narratives() -> None:
    """Full narrative refresh: related_catalysts + conviction scores + maturity.

    Conviction must run before maturity (maturity reads conviction_score).
    Serialized under held lock_conn (SWI-261 family).
    """
    try:
        catalysts_updated = await refresh_related_catalysts()
        conviction_updated = await refresh_all_conviction_scores()
        maturity_updated = await refresh_narrative_maturity()
        print(
            f"  Narrative refresh: {catalysts_updated} catalyst links, "
            f"{conviction_updated} conviction, {maturity_updated} maturity",
            flush=True,
        )
    except Exception as exc:
        logger.warning("Narrative refresh failed (non-critical): %s", exc)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run catalyst check and optional strategy revision"
    )
    parser.add_argument(
        "--date",
        default=get_scan_date(),
        help="Date to analyze (YYYY-MM-DD)",
    )
    args = parser.parse_args()
    scan_date_str = args.date

    try:
        asyncio.run(asyncio.wait_for(_run_catalyst_check(scan_date_str), timeout=900))
    except TimeoutError:
        error_msg = "Catalyst check timed out after 15 minutes"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        sys.exit(1)
    except Exception as exc:
        error_msg = f"Catalyst check failed: {exc}"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        sys.exit(1)
    finally:
        shutdown_observability()


async def _run_catalyst_check(scan_date_str: str) -> None:
    """Run the catalyst check pipeline."""
    scan_date = date.fromisoformat(scan_date_str)

    print(f"\n{'=' * 60}", flush=True)
    print(f"CATALYST CHECK — {scan_date}", flush=True)
    print(f"Active hours: {_is_active_hours()}", flush=True)
    print(f"{'=' * 60}", flush=True)

    # Root span for Logfire — matches news_pipeline_v2.py pattern. The
    # collector's PIPELINE_SPAN_NAMES tuple already lists "catalyst_check",
    # so emitting this span lets pipeline-review bundles include catalyst
    # traces (MON-2026-04-14 observability gap).
    with span("catalyst_check", scan_date=str(scan_date)):
        await _run_catalyst_check_inner(scan_date)


# Fixed namespace constant (ASCII "cata") — must NOT use hash() because
# Python 3 randomizes string hashes per process, which would make each
# invocation lock on a different namespace and defeat cross-process
# serialization.
_CATALYST_LOCK_NAMESPACE = 0x63617461


async def _run_catalyst_check_inner(scan_date: date) -> None:
    async with Database():
        await init_trading_config()

        # Session-scoped advisory lock (NOT xact_lock) — xact_lock would
        # require holding a transaction open across the 420s LLM revision,
        # risking idle-in-transaction timeouts on Neon.
        db = await get_db()
        lock_key = int(scan_date.toordinal())
        async with db.pool.acquire() as lock_conn:
            acquired = await lock_conn.fetchval(
                "SELECT pg_try_advisory_lock($1::int, $2::int)",
                _CATALYST_LOCK_NAMESPACE,
                lock_key,
            )
            if not acquired:
                log_info(
                    "catalyst_check_skipped_concurrent",
                    scan_date=str(scan_date),
                )
                return
            try:
                await _run_catalyst_check_body(scan_date)
            finally:
                await lock_conn.execute(
                    "SELECT pg_advisory_unlock($1::int, $2::int)",
                    _CATALYST_LOCK_NAMESPACE,
                    lock_key,
                )


async def _run_catalyst_check_body(scan_date: date) -> None:
    # ── Step 0: Lightweight news refresh ─────────────────────
    print("\n  Step 0: News refresh...", flush=True)
    refresh = await refresh_news(scan_date)
    print(
        f"  Result: {refresh['vn_count']} VN, {refresh['intl_count']} intl, {refresh['sentiment']} sentiment",
        flush=True,
    )

    # ── Step 0b: Narrative scores + catalyst lifecycle (serial — SWI-261) ──
    print("\n  Step 0b: Narrative + lifecycle refresh...", flush=True)
    await _refresh_narratives()
    await refresh_catalyst_lifecycle()

    # ── Steps 1+2: Spike detection + news matches (serial — SWI-261) ──
    # Body holds the session-scoped advisory lock_conn (acquired at the
    # caller, line ~149) for the entire run. Both children fan out into
    # nested asyncio.gather calls (pipeline/catalyst_news_check.py:145, 207),
    # each acquiring its own pool connection. Under default pool max_size=10
    # the held lock_conn (1) plus parallel fan-out (~9) exhausts the pool —
    # surfaces as "connection has been released back to the pool" after
    # spike disposition. Serialize to bound concurrent acquires to ~5.
    # Cost: spike ~33ms + news ~400ms ≈ 450ms total; acceptable for 3x/day cron.
    has_spike, trigger_description, changed_catalysts = await detect_catalyst_spike(scan_date)
    news_signals, match_method, checked_keys = await check_catalyst_news(scan_date)
    spike_signals = [signal for signal in news_signals if signal["is_spike"]]

    # Persist all signals to DB (for baseline tracking) AND refresh
    # last_updated for every checked catalyst (SWI-64).
    if news_signals or checked_keys:
        saved = await save_catalyst_news_signals(
            news_signals, scan_date, match_method, checked_keys=checked_keys
        )
        print(
            f"  Saved {saved} news signals; refreshed {len(checked_keys)} checked rows [{match_method}]",
            flush=True,
        )

    # Combine spike sources
    if spike_signals and not has_spike:
        has_spike = True
        spike_events = [signal["catalyst_event"] for signal in spike_signals[:3]]
        trigger_description = f"News spike: {', '.join(spike_events)}"

    # ── Step 3: Exit early if no spike ───────────────────────
    if not has_spike:
        print("\n  No catalyst spike detected. Exiting early.", flush=True)
        log_info(
            "catalyst_check_spike_disposition",
            disposition="no_spike",
            trigger=trigger_description,
            has_spike=False,
            scan_date=str(scan_date),
        )
        await mark_scan_revision_completed(scan_date)
        return

    print(f"\n  SPIKE DETECTED: {trigger_description}", flush=True)

    # ── Step 4: Route based on active hours ──────────────────
    if _is_active_hours():
        print("\n  Active hours — triggering strategy revision...", flush=True)
        log_info(
            "catalyst_check_spike_disposition",
            disposition="revised",
            trigger=trigger_description,
            has_spike=True,
            scan_date=str(scan_date),
        )
        try:
            result = await asyncio.wait_for(
                run_strategy_revision(
                    scan_date=scan_date,
                    trigger_description=trigger_description,
                    changed_catalysts=changed_catalysts,
                ),
                timeout=420,
            )
            print(f"\n  Revision result: {result}", flush=True)
            await mark_scan_revision_completed(scan_date)
        except TimeoutError:
            logger.warning(
                "Strategy revision timed out after 420s for trigger: %s",
                trigger_description,
            )
            print("\n  Strategy revision TIMED OUT (420s)", flush=True)
            # Skip baseline bump on timeout — the next cron must retry.
    else:
        log_info(
            "catalyst_check_spike_disposition",
            disposition="suppressed_outside_active_hours",
            trigger=trigger_description,
            has_spike=True,
            scan_date=str(scan_date),
        )
        await mark_scan_revision_completed(scan_date)


if __name__ == "__main__":
    main()
