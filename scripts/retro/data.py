"""
Data fetching and transformation helpers for the retrospective pipeline.

Extracts DB-fetching, I/O, and price/sector map construction from the main
orchestrator so the module stays under 300 lines.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from data.prices import fetch_prices_async
from shared.config import PRICE_MULTIPLIER
from shared.neon import get_longterm_watchlist as get_longterm_watchlist_async
from shared.neon import get_portfolio_holdings
from shared.neon import get_swing_watchlist as get_swing_watchlist_async
from shared.watchlist import merge_holdings_into_watchlist

logger = logging.getLogger(__name__)


async def fetch_eod_prices(date: str) -> tuple[dict, list[dict], dict]:
    """Fetch fresh EOD prices, portfolio holdings, and watchlist.

    Returns:
        (eod_prices, holdings, watchlist) — caller reuses holdings/watchlist
        without re-querying the DB. Holdings is the list[HoldingData] form.
    """
    print("  Fetching fresh EOD prices...")
    watchlist = await get_swing_watchlist_async()
    if not watchlist:
        raise RuntimeError("Database unavailable - cannot fetch watchlist")

    holdings, longterm_watchlist = await asyncio.gather(
        get_portfolio_holdings(),
        get_longterm_watchlist_async(),
    )
    merged_watchlist = merge_holdings_into_watchlist(watchlist, holdings)

    # Include longterm watchlist tickers for LONG_TERM section evaluation
    if longterm_watchlist:
        existing_tickers = {ticker for tickers in merged_watchlist.values() for ticker in tickers}
        longterm_only = [ticker for ticker in longterm_watchlist if ticker not in existing_tickers]
        if longterm_only:
            merged_watchlist["longterm"] = longterm_only
            logger.info("Added %d longterm-only tickers for price fetch", len(longterm_only))

    prices = await fetch_prices_async(merged_watchlist, end_date=date)

    if prices:
        success = sum(1 for v in prices.values() if "error" not in v)
        total = len(prices)
        if total > 0 and success / total < 0.6:
            logger.warning(f"Price fetch degraded: {success}/{total} succeeded")

    return prices, holdings, watchlist


def build_portfolio_prices(holdings: list[dict], eod_prices: dict) -> dict:
    """Build a ticker -> price (VND) map for current holdings.

    Filters to only tickers present in both holdings and eod_prices,
    skipping any entries with errors.
    fetch_prices_async returns thousands VND from vnstock API; multiply to VND.
    """
    held_tickers = {slice_row["ticker"] for slice_row in holdings if slice_row.get("ticker")}
    return {
        ticker: data.get("close", 0) * PRICE_MULTIPLIER
        for ticker, data in eod_prices.items()
        if ticker in held_tickers and "error" not in data
    }


def build_sector_map(watchlist: dict) -> dict:
    """Build a ticker -> sector_name mapping from the watchlist.

    Args:
        watchlist: dict of {sector_name: [ticker, ...]}
    """
    sector_map = {}
    for sector_name, tickers in watchlist.items():
        for ticker in tickers:
            sector_map[ticker] = sector_name
    return sector_map


async def load_midday_check(scan_date) -> dict | None:
    """Load midday check data from database."""
    from shared.neon import get_midday_check

    if isinstance(scan_date, str):
        scan_date = datetime.strptime(scan_date, "%Y-%m-%d").date()

    data = await get_midday_check(scan_date)
    if "error" in data:
        logger.warning("Midday check not found for %s", scan_date)
        return None

    print(f"  Loaded midday check (mode: {data.get('trading_mode', 'N/A')})")
    return data


def _build_completion_sentinel(kind: str, target_date: str) -> str:
    """HTML-comment trailer that consumers parse to assert completeness.

    Stripped by GitHub markdown renderers; preserved by raw byte capture
    (collector). target_date catches stale-checkout staleness — see SWI-134.
    """
    run_id = os.environ.get("GITHUB_RUN_ID") or os.environ.get("LOGFIRE_TRACE_ID") or "local"
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"\n<!-- {kind}: target_date={target_date} run_id={run_id} ts={ts} -->\n"


def _atomic_write_text(path: Path, content: str) -> None:
    """Write via temp + rename so a process kill never produces a partial file."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)


def save_retrospective(content: str, date: str, research_dir: Path) -> Path:
    """Save retrospective markdown to research directory.

    Appends a `RETRO_COMPLETE` sentinel (SWI-134) and writes atomically
    so partial files never appear on disk.
    """
    output_dir = research_dir / date
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "retrospective.md"
    header = f"""# Market Close Retrospective - {date}

*Generated by GLM-5 at {datetime.now().strftime("%H:%M:%S")}*

---

"""
    sentinel = _build_completion_sentinel("RETRO_COMPLETE", date)
    _atomic_write_text(output_file, header + content + sentinel)

    print(f"  Saved: {output_file}")
    return output_file


def save_retrospective_or_quarantine(
    retro_content: str,
    evaluations: dict,
    today: str,
    research_dir: Path,
) -> None:
    """Route to quarantine stub when validator rejected the LLM draft (SWI-255).

    Falls through to ``save_retrospective`` on the happy path.
    """
    quarantined_draft = evaluations.get("quarantined_draft")
    quarantine_violations = evaluations.get("quarantine_violations") or []
    if not quarantined_draft:
        save_retrospective(retro_content, today, research_dir)
        return

    from agents.retro.render import build_deterministic_prefixes_block

    prefixes_block = build_deterministic_prefixes_block(evaluations.get("evaluations") or [])
    save_quarantined_retrospective(
        date=today,
        research_dir=research_dir,
        deterministic_prefixes=prefixes_block,
        violations=quarantine_violations,
        rejected_draft=quarantined_draft,
    )
    logger.error(
        "RETRO_QUARANTINED today=%s violation_count=%d — see retrospective.md VIOLATIONS",
        today,
        len(quarantine_violations),
    )


def save_quarantined_retrospective(
    *,
    date: str,
    research_dir: Path,
    deterministic_prefixes: str,
    violations: list[str],
    rejected_draft: str,
) -> Path:
    """Persist a quarantine-stub retrospective when the validator rejects the LLM draft.

    Body contains the deterministic prefixes (rule + execution per ticker)
    plus a `## VIOLATIONS` section and the rejected draft fenced as an
    HTML comment for diagnostic value. SWI-255 fail-loud recovery path.
    """
    output_dir = research_dir / date
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "retrospective.md"
    header = f"""# Market Close Retrospective - {date} (QUARANTINED)

*LLM draft rejected by validator at {datetime.now().strftime("%H:%M:%S")}*

---

"""
    violations_block = "## VIOLATIONS\n" + "\n".join(f"- {v}" for v in violations) + "\n"
    body = (
        header
        + deterministic_prefixes
        + "\n\n"
        + violations_block
        + "\n<!-- QUARANTINED LLM DRAFT\n"
        + rejected_draft
        + "\n-->\n"
    )
    body += _build_completion_sentinel("RETRO_QUARANTINED", date)
    _atomic_write_text(output_file, body)
    print(f"  QUARANTINED: {output_file}")
    return output_file


def print_summary(evaluations, recommendations, midday_data, rotation_eval, macro_eval):
    """Print retrospective summary to stdout."""
    from agents.retro.compute import ENTRY_HIT_RATE_NA
    from shared.neon.insert_learnings import normalize_rate

    summary = evaluations.get("day_summary", {})
    midday_summary = evaluations.get("midday_summary", {})

    entry_hit_rate_raw = summary.get("entry_hit_rate")
    entry_hit_rate = normalize_rate(entry_hit_rate_raw) if entry_hit_rate_raw is not None else None
    win_rate = normalize_rate(summary.get("win_rate", 0)) or 0
    entry_hit_display = f"{entry_hit_rate:.0%}" if entry_hit_rate is not None else ENTRY_HIT_RATE_NA
    print("Summary:")
    print(f"  - Recommendations: {len(recommendations)}")
    print(f"  - Entry Hit Rate: {entry_hit_display}")
    print(f"  - Win Rate: {win_rate:.0%}")
    print(f"  - Best Call: {summary.get('best_call', 'N/A')}")
    print(f"  - Key Insight: {summary.get('key_insight', 'N/A')}")
    if midday_data:
        print(f"  - Trading Mode: {midday_data.get('trading_mode', 'N/A')}")
        print(f"  - Mode Compliance: {'Yes' if evaluations.get('mode_compliance', True) else 'No'}")
        if midday_summary:
            print(f"  - Midday Effectiveness: {evaluations.get('adjustment_effectiveness', 'N/A')}")
    if rotation_eval:
        print(f"  - Rotation Accuracy: {rotation_eval.get('overall_accuracy', 0):.0%}")
    if macro_eval:
        print(f"  - Global Risk Regime: {macro_eval.get('global_risk_regime', 'N/A')}")
        print(f"  - Macro Appropriate: {macro_eval.get('regime_appropriate', 'N/A')}")
