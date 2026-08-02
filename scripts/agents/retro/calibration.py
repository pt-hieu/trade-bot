#!/usr/bin/env python3
"""
Quantitative calibration metrics for retrospective feedback loop.

Two responsibilities:
1. enrich_evals_with_atr() — adds ATR-based stop adequacy to entry evals (async, API access)
2. calc_calibration_stats() — aggregates calibration metrics across rolling window (pure Python)

All calculations are deterministic — no LLM.
"""

import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

from shared.observability import log_warn
from shared.rules.calibration import MIN_CALIBRATION_SAMPLE, RATIO_FIELDS

from .compute import PLAN_TYPE_SWING
from .won import ENTRY_ACTIONS as _ENTRY_ACTIONS


async def enrich_evals_with_atr(
    evaluations: list[dict],
    scan_date: date,
) -> None:
    """Enrich entry evaluations with ATR-based stop adequacy ratio.

    Fetches current ATR per ticker from vnstock API.
    ATR and entry_price are both in k-VND (thousands VND) — units cancel in ratio.
    Mutates evaluation dicts in place.

    Error handling: per-symbol fallback if batch fails. Never raises —
    top-level guard catches unexpected errors. Logs warnings and enriches what it can.
    """
    try:
        await _enrich_evals_with_atr_inner(evaluations, scan_date)
    except Exception as unexpected_error:
        logger.warning("ATR enrichment unexpected failure: %s", unexpected_error)


async def _enrich_evals_with_atr_inner(
    evaluations: list[dict],
    scan_date: date,
) -> None:
    """Inner implementation — may raise, caller catches."""
    from shared.vnstock_client import fetch_technicals, fetch_technicals_batch

    # Collect unique tickers with entry actions that have entry_price
    entry_tickers: set[str] = {
        ticker
        for e in evaluations
        if e.get("recommendation") in _ENTRY_ACTIONS and e.get("entry_price")
        for ticker in [e.get("ticker")]
        if ticker
    }
    if not entry_tickers:
        logger.info("ATR enrichment: no entry tickers to enrich")
        return

    atr_map: dict[str, float] = {}

    # Try batch first, fall back to per-symbol on failure
    try:
        ta_results = await fetch_technicals_batch(symbols=list(entry_tickers))
        for ticker in entry_tickers:
            ta = ta_results.get(ticker.upper(), {})
            if isinstance(ta, dict) and "error" in ta:
                logger.warning("ATR batch: %s returned error: %s", ticker, ta.get("error"))
                continue
            atr_val = ta.get("atr") if isinstance(ta, dict) else None
            if atr_val:
                atr_map[ticker] = float(atr_val)
    except Exception as batch_error:
        logger.warning("ATR batch fetch failed (%s), falling back to per-symbol", batch_error)
        for ticker in entry_tickers:
            try:
                ta = await fetch_technicals(ticker)
                atr_val = ta.get("atr") if isinstance(ta, dict) and "error" not in ta else None
                if atr_val:
                    atr_map[ticker] = float(atr_val)
            except Exception as symbol_error:
                logger.warning("ATR fetch failed for %s: %s", ticker, symbol_error)

    if not atr_map:
        logger.warning("ATR enrichment: no ATR data retrieved for %d tickers", len(entry_tickers))

    # Enrich each entry eval
    enriched_count = 0
    for e in evaluations:
        if e.get("recommendation") not in _ENTRY_ACTIONS:
            continue
        ticker = e.get("ticker")
        if not ticker:
            continue
        atr_vnd = atr_map.get(ticker)
        entry_price = e.get("entry_price")
        stop_buffer_pct = e.get("stop_buffer_pct")

        if atr_vnd and entry_price and entry_price > 0:
            atr_pct = round(atr_vnd / entry_price * 100, 2)
            e["atr_pct"] = atr_pct
            if stop_buffer_pct and atr_pct > 0:
                e["stop_vs_atr_ratio"] = round(stop_buffer_pct / atr_pct, 2)
            enriched_count += 1

    logger.info("ATR enrichment: enriched %d/%d tickers", enriched_count, len(entry_tickers))


def _phantom_guard(stats: dict, sample_size: int, min_n: int = MIN_CALIBRATION_SAMPLE) -> dict:
    """NULL out ratio fields when sample_size below the threshold.

    Loops `RATIO_FIELDS` so any field added there is automatically guarded.
    """
    if sample_size >= min_n:
        return stats
    for field in RATIO_FIELDS:
        if field in stats:
            stats[field] = None
    return stats


def _parse_exit_date(value: date | str | None) -> date | None:
    """Coerce eval.exit_date (date | str | None) to a date."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def calc_calibration_stats(
    daily_records: list[dict],
    rolling_days: int,
    scan_date: date | None = None,
) -> dict:
    """Aggregate calibration metrics across rolling window for entry actions only.

    Returns dict with avg_entry_gap_pct, pct_entries_unreachable, avg_stop_vs_atr,
    pct_stops_too_tight, avg_predicted_rr, avg_actual_rr, target_hit_rate,
    sample_size, swing_sample_size, last_trade_exit_date.

    Returns empty dict if insufficient data.
    """
    entry_gaps: list[float] = []
    stop_atr_ratios: list[float] = []
    predicted_rrs: list[float] = []
    actual_rrs: list[float] = []
    entries_total = 0
    swing_total = 0
    entries_unreachable = 0
    stops_too_tight = 0
    targets_hit = 0
    entries_that_hit = 0
    latest_exit: date | None = None

    for record in daily_records[-rolling_days:]:
        for e in record.get("evaluations", []):
            if e.get("recommendation") not in _ENTRY_ACTIONS:
                continue
            entries_total += 1
            if e.get("plan_type") == PLAN_TYPE_SWING:
                swing_total += 1

            # Track most-recent exit_date among closed evals (won is bool).
            # Closed eval missing exit_date is a data gap — log so we can
            # spot the producer that needs to start emitting it.
            if e.get("won") is not None:
                exit_dt = _parse_exit_date(e.get("exit_date"))
                if exit_dt is None:
                    log_warn(
                        "calibration_missing_exit_date",
                        ticker=e.get("ticker"),
                        scan_date=str(scan_date) if scan_date else None,
                    )
                else:
                    latest_exit = exit_dt if latest_exit is None else max(latest_exit, exit_dt)

            if not e.get("entry_hit"):
                entries_unreachable += 1
            else:
                entries_that_hit += 1
                if e.get("target_hit"):
                    targets_hit += 1

            gap = e.get("entry_gap_pct")
            if gap is not None:
                entry_gaps.append(float(gap))

            ratio = e.get("stop_vs_atr_ratio")
            if ratio is not None:
                stop_atr_ratios.append(float(ratio))
                if float(ratio) < 1.0:
                    stops_too_tight += 1

            pred = e.get("predicted_rr")
            if pred is not None:
                predicted_rrs.append(float(pred))

            actual = e.get("actual_max_rr")
            if actual is not None:
                actual_rrs.append(float(actual))

    if entries_total == 0:
        return {}

    def _avg(lst: list[float]) -> float | None:
        return round(sum(lst) / len(lst), 2) if lst else None

    # swing_sample_size falls back to entries_total when no eval carries
    # plan_type — keeps legacy records observable until plan_type lands.
    swing_sample_size = swing_total if swing_total > 0 else entries_total

    stats: dict = {
        "avg_entry_gap_pct": _avg(entry_gaps),
        "pct_entries_unreachable": round(entries_unreachable / entries_total * 100, 1),
        "avg_stop_vs_atr": _avg(stop_atr_ratios),
        "pct_stops_too_tight": round(stops_too_tight / len(stop_atr_ratios) * 100, 1)
        if stop_atr_ratios
        else None,
        "avg_predicted_rr": _avg(predicted_rrs),
        "avg_actual_rr": _avg(actual_rrs),
        "target_hit_rate": round(targets_hit / entries_that_hit * 100, 1)
        if entries_that_hit
        else 0.0,
        "sample_size": entries_total,
        "swing_sample_size": swing_sample_size,
        "last_trade_exit_date": latest_exit.isoformat() if latest_exit else None,
    }

    return _phantom_guard(stats, swing_sample_size)
