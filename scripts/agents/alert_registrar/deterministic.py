"""Deterministic alert registration — picks and trailing stops."""

import asyncio
import json
import logging
from datetime import date

from agents.tools.alerts import default_expiry
from agents.tools.trailing_stops import compute_trailing_stop
from shared.database import fetch_all
from shared.neon import collapse_holdings_by_ticker
from shared.neon.alerts import register_alert as db_register_alert
from shared.rules.entry_gates import RiskRegime, TradingMode
from shared.rules.exit_strategy import CRITICAL_STOP_TYPES, is_trailing_exit, read_rr
from shared.rules.settlement import (
    is_sellable,
    load_open_trades_snapshot,
    settlement_date,
)

logger = logging.getLogger(__name__)


def _log_skip_summary(label: str, entries: list[tuple[str, str]]) -> None:
    """Emit a single WARNING summarising per-row skips/failures from a registrar loop."""
    if not entries:
        return
    detail = ", ".join(f"{ticker}({reason})" for ticker, reason in entries)
    logger.warning("%s: %d row(s) skipped — %s", label, len(entries), detail)


def _build_alert_metadata(
    risk_regime: RiskRegime,
    trading_mode: TradingMode,
    extra: dict | None = None,
) -> str:
    """Build JSON metadata with regime/mode context for all alerts."""
    metadata: dict = {"regime": risk_regime, "trading_mode": trading_mode}
    if extra:
        metadata.update(extra)
    return json.dumps(metadata)


async def register_trailing_stop_alerts(
    scan_date: date,
    current_prices: dict[str, float] | None,
    risk_regime: RiskRegime = "CALM",
    trading_mode: TradingMode = "NORMAL",
    holdings: list[dict] | None = None,
) -> int:
    """Deterministic stop-loss alerts from the trailing_stops table.

    SWI-363: the table is populated by ``compute_and_persist_trailing_stops``,
    but an underwater SWING holding whose stop computes to ``None`` (no
    ``breakeven_stop`` on the record, or a price-fetch outage at persist time)
    never gets a row — so it ships with no catastrophic-floor alert. When
    ``holdings`` is supplied, a second pass computes the breakeven floor
    directly from every SWING holding (regardless of watchlist membership) and
    registers a floor alert for any ticker the table pass did not already cover.
    """
    if not current_prices:
        return 0

    # Parallel: trailing_stops scan + one-shot OPEN-trades snapshot for the
    # T+2 settlement guard. Both are independent single-table reads.
    rows, open_trades = await asyncio.gather(
        fetch_all("SELECT ticker, stop_level, stop_type, updated_at FROM trailing_stops"),
        load_open_trades_snapshot(scan_date),
    )

    settled = open_trades.settled_by_ticker
    earliest_entry_by_ticker = open_trades.earliest_entry_by_ticker

    # HOSE daily price band is ±7% — non-catastrophic stops beyond this can't trigger in 1 day
    vn_max_daily_move = 0.07
    max_stop_staleness_days = 7

    count = 0
    alerted_tickers: set[str] = set()
    failed: list[tuple[str, str]] = []
    for row in rows:
        ticker = row.get("ticker") or "?"
        try:
            stop_level = row.get("stop_level")
            if not stop_level:
                continue

            # Two reasons a stop can be unactionable: no OPEN trade (orphaned stop
            # on a closed/exited position) vs OPEN but unsettled (T+2). Log both
            # separately so cleanup work is distinguishable from settlement drag.
            if not is_sellable(ticker, settled):
                entry_date = earliest_entry_by_ticker.get(ticker)
                if entry_date is None:
                    logger.info(
                        "Skipped %s stop: no OPEN trade (closed or fully exited — consider cleanup)",
                        ticker,
                    )
                else:
                    logger.info(
                        "Skipped %s stop: unsettled (entry %s, settles %s)",
                        ticker,
                        entry_date,
                        settlement_date(entry_date),
                    )
                continue

            stop_type = row.get("stop_type") or "unknown"

            updated_at = row.get("updated_at")
            if updated_at:
                staleness = (scan_date - updated_at).days if isinstance(updated_at, date) else 999
                if staleness > max_stop_staleness_days:
                    logger.info("Skipping stale stop for %s: %d days old", ticker, staleness)
                    continue

            stop_level = float(stop_level)
            current = current_prices.get(ticker)
            if not current or current <= 0:
                continue

            if stop_level >= current:
                logger.info(
                    "Skipping stop alert for %s: stop %.0f >= current %.0f",
                    ticker,
                    stop_level,
                    current,
                )
                continue

            distance_pct = (current - stop_level) / current

            # CRITICAL_STOP_TYPES (catastrophic + breakeven_floor) bypass the
            # 7%-band guard — both are cost-basis-anchored catastrophic floors.
            if stop_type not in CRITICAL_STOP_TYPES and distance_pct > vn_max_daily_move:
                logger.info(
                    "Skipping %s stop for %s: %.1f%% beyond 1-day move limit (7%%)",
                    stop_type,
                    ticker,
                    distance_pct * 100,
                )
                continue

            alert_id = await db_register_alert(
                {
                    "ticker": ticker,
                    "source": "trailing_stop",
                    "source_date": scan_date,
                    "conditions": [{"type": "price_below", "value": int(stop_level)}],
                    "condition_logic": "ALL",
                    "action_type": "notify_and_analyze",
                    "recommended_action": "STOP",
                    "stop_price": int(stop_level),
                    "priority": "high",
                    "rationale": f"Trailing stop ({stop_type}) at {stop_level:.0f} VND",
                    "alert_metadata": _build_alert_metadata(risk_regime, trading_mode),
                }
            )
            if alert_id > 0:
                count += 1
                alerted_tickers.add(ticker)
        except Exception as exc:
            failed.append((ticker, type(exc).__name__))
            logger.error(
                "register_trailing_stop_alerts: %s failed — row=%s",
                ticker,
                row,
                exc_info=True,
            )
            continue

    # SWI-363: breakeven-floor coverage for SWING holdings missing a table row.
    count += await _register_holding_breakeven_floors(
        holdings=holdings,
        scan_date=scan_date,
        current_prices=current_prices,
        settled=settled,
        earliest_entry_by_ticker=earliest_entry_by_ticker,
        already_alerted=alerted_tickers,
        risk_regime=risk_regime,
        trading_mode=trading_mode,
        failed=failed,
    )

    _log_skip_summary("register_trailing_stop_alerts", failed)
    return count


async def _register_holding_breakeven_floors(
    *,
    holdings: list[dict] | None,
    scan_date: date,
    current_prices: dict[str, float],
    settled: dict,
    earliest_entry_by_ticker: dict,
    already_alerted: set[str],
    risk_regime: RiskRegime,
    trading_mode: TradingMode,
    failed: list[tuple[str, str]],
) -> int:
    """Register breakeven-floor alerts for SWING holdings missing a table row.

    Computes the floor directly from each holding via ``compute_trailing_stop``
    so a catastrophic floor is enforced even when the persist step produced no
    ``trailing_stops`` row (SWI-363). Skips tickers already covered by the table
    pass, non-SWING holdings, and holdings whose floor computes to ``None``.
    """
    if not holdings:
        return 0

    count = 0
    for ticker, holding in collapse_holdings_by_ticker(holdings).items():
        if ticker in already_alerted:
            continue
        if (holding.get("plan_type") or "SWING") != "SWING":
            continue
        try:
            avg_cost = holding.get("avg_cost") or 0
            current = current_prices.get(ticker) or holding.get("current_price_vnd")
            if not avg_cost or not current or current <= 0:
                continue
            if not is_sellable(ticker, settled):
                continue

            weight = holding.get("ticker_weight_pct") or holding.get("slice_weight_pct") or 0
            computed = compute_trailing_stop(
                float(avg_cost),
                float(current),
                "SWING",
                float(weight),
                breakeven_stop=holding.get("breakeven_stop"),
            )
            if computed.get("stop_type") != "breakeven_floor":
                continue
            stop_level = computed.get("stop")
            if not stop_level or stop_level >= current:
                continue

            alert_id = await db_register_alert(
                {
                    "ticker": ticker,
                    "source": "trailing_stop",
                    "source_date": scan_date,
                    "conditions": [{"type": "price_below", "value": int(stop_level)}],
                    "condition_logic": "ALL",
                    "action_type": "notify_and_analyze",
                    "recommended_action": "STOP",
                    "stop_price": int(stop_level),
                    "priority": "high",
                    "rationale": f"Breakeven floor (holding) at {stop_level:.0f} VND",
                    "alert_metadata": _build_alert_metadata(risk_regime, trading_mode),
                }
            )
            if alert_id > 0:
                count += 1
                already_alerted.add(ticker)
        except Exception as exc:
            failed.append((ticker, type(exc).__name__))
            logger.error(
                "register_trailing_stop_alerts(holding floor): %s failed — holding=%s",
                ticker,
                holding,
                exc_info=True,
            )
            continue

    return count


def _is_already_triggered(
    ticker: str, threshold: float, prices: dict[str, float], label: str
) -> bool:
    """Return True if price already at/below threshold. Sentinel -1.0 = blocked."""
    current = prices.get(ticker)
    if current is not None and current <= threshold:
        logger.info(
            "Skipping %s alert for %s: price %.0f already at/below %.0f",
            label,
            ticker,
            current,
            threshold,
        )
        return True
    return False


async def register_picks_as_alerts(
    pre_computed_picks: list[dict],
    source: str,
    scan_date: date,
    risk_regime: RiskRegime = "CALM",
    trading_mode: TradingMode = "NORMAL",
    current_prices: dict[str, float] | None = None,
) -> int:
    """Register BUY alerts from pre-computed picks. Returns count registered."""
    if risk_regime == "CRISIS":
        print(f"  Skipping BUY alerts: risk_regime={risk_regime}")
        return 0

    prices = current_prices or {}
    count = 0
    skipped: list[tuple[str, str]] = []
    for pick in pre_computed_picks:
        # SWI-248: a malformed (None / non-dict) pick is scoped per-row, not a
        # systemic failure — keep it from escaping to phase_alerts' re-raise.
        if not isinstance(pick, dict):
            skipped.append(("?", "non_dict_pick"))
            logger.info("Skipping non-dict pick: %r", pick)
            continue
        ticker = pick.get("ticker") or "?"
        try:
            action = pick.get("action") or "BUY"
            if action not in ("BUY", "LIMIT_BUY"):
                skipped.append((ticker, f"non_buy_action:{action}"))
                logger.info("Skipping %s alert: non-BUY action %s", ticker, action)
                continue
            if pick.get("entry") is None:
                skipped.append((ticker, "no_entry"))
                logger.info("Skipping %s alert: no entry price", ticker)
                continue
            if pick.get("stop") is None:
                skipped.append((ticker, "no_stop"))
                logger.info("Skipping %s alert: no stop price", ticker)
                continue

            entry = round(float(pick["entry"]), 0)

            if _is_already_triggered(ticker, entry, prices, "BUY"):
                continue
            stop = round(float(pick["stop"]), 0)

            raw_target = pick.get("target")
            target = round(float(raw_target), 0) if raw_target is not None else None
            raw_rr = read_rr(pick)  # None for trailing exits — preserved for branch below
            risk_reward = round(float(raw_rr), 1) if raw_rr is not None else None
            strategy = pick.get("strategy") or ""

            gap = pick.get("gap_from_support_pct")
            gap_str = f", {gap:.1f}% above support" if gap is not None else ""

            if is_trailing_exit(pick):
                priority = "normal"
                rationale = (
                    f"{ticker} {strategy} ATR_TRAIL entry {entry:,.0f} (trailing stop){gap_str}"
                )
            else:
                rr_val = risk_reward or 0.0
                priority = "high" if rr_val >= 5.0 else "normal"
                rationale = f"{ticker} R:R {rr_val:.1f}, {strategy}, entry {entry:,.0f}{gap_str}"

            alert = {
                "ticker": ticker,
                "conditions": [{"type": "price_below", "value": entry}],
                "condition_logic": "ALL",
                "source": source,
                "source_date": scan_date,
                "recommended_action": action,
                "action_type": "notify_and_analyze",
                "priority": priority,
                "rationale": rationale,
                "entry_price": entry,
                "stop_price": stop,
                "target_price": target,
                "expires_at": default_expiry(source, "normal", scan_date, action),
                "alert_metadata": _build_alert_metadata(risk_regime, trading_mode),
            }
            alert_id = await db_register_alert(alert)
            if alert_id > 0:
                count += 1
                rr_disp = f"R:R {risk_reward:.1f}" if risk_reward is not None else "trailing"
                print(f"  {action} alert #{alert_id}: {ticker} entry {entry:,.0f} {rr_disp}")
        except Exception as exc:
            skipped.append((ticker, f"exc:{type(exc).__name__}"))
            logger.error(
                "register_picks_as_alerts: %s failed — pick=%s",
                ticker,
                pick,
                exc_info=True,
            )
            continue

    _log_skip_summary("register_picks_as_alerts", skipped)
    return count
