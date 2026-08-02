"""Compute and persist trailing stops for portfolio holdings.

Writes stops for all live positions regardless of settlement. Readers must
apply ``shared.rules.settlement.is_sellable`` before acting on a stop.
Stale stops for CLOSED trades are tolerated; readers skip them via the
"no OPEN trade" log branch in ``alert_registrar.deterministic``.
"""

import logging
from datetime import date, datetime

from agents.tools.trailing_stops import compute_trailing_stop
from shared.database import Database

logger = logging.getLogger(__name__)


async def compute_and_persist_trailing_stops(holdings: list[dict], scan_date) -> str:
    """Compute trailing stops for holdings and persist high-water marks to DB.

    Returns trailing_stops_context string for position monitor. One stop per
    ticker, SWING-preferred via :func:`collapse_holdings_by_ticker` — the
    MY HOLDINGS contract.
    """
    if not holdings:
        return ""

    from shared.neon import collapse_holdings_by_ticker

    by_ticker = collapse_holdings_by_ticker(holdings)

    prev_stops: dict[str, float] = {}
    stop_lines = ["PRE-COMPUTED TRAILING STOPS (use these exactly, do NOT override):"]
    new_stops: dict[str, tuple[float, str]] = {}  # ticker -> (stop_val, stop_type)

    async with Database() as db:
        rows = await db.fetch_all("SELECT ticker, stop_level FROM trailing_stops")
        for row in rows:
            if row["stop_level"] is not None:
                prev_stops[row["ticker"]] = float(row["stop_level"])

        for ticker, h in by_ticker.items():
            avg_cost = h.get("avg_cost") or 0
            # Strict pick: when current_price_vnd is missing, skip the stop
            # computation. Substituting avg_cost would emit an unmoving
            # trailing stop at cost basis, masking a real price-fetch
            # outage as "no trail movement" (Phase 2 §2.2 sibling).
            current = h.get("current_price_vnd")
            if not current:
                logger.warning(
                    "trailing_stops: skipping %s — no current_price_vnd "
                    "(price fetch outage; not substituting avg_cost)",
                    ticker,
                )
                continue
            plan_type = h.get("plan_type") or "SWING"
            # Use the aggregated ticker weight so a dual-listed ticker's
            # two-slice concentration is reflected in the stop sizing.
            weight = h.get("ticker_weight_pct") or h.get("slice_weight_pct") or 0
            old_stop = prev_stops.get(ticker)
            # SWI-157 Option A (2026-05-14): thread breakeven_stop so underwater
            # SWING positions persist a `breakeven_floor` row instead of None.
            # The alert registrar reads trailing_stops only — without this, an
            # open underwater position (e.g. ACV today) ships with no morning
            # stop alert because compute_trailing_stop's underwater branch
            # historically returned `stop=None` and the upsert below skipped it.
            ts = compute_trailing_stop(
                avg_cost,
                current,
                plan_type,
                weight,
                old_stop,
                breakeven_stop=h.get("breakeven_stop"),
            )

            if ts.get("catastrophic_stop"):
                # Two-layer LONGTERM stop — persist catastrophic floor for alert registration
                catastrophic_stop = ts["catastrophic_stop"]
                cat_str = f"{catastrophic_stop:.1f}k"
                checkpoints = "; ".join(ts.get("thesis_checkpoints") or [])
                line = f"- {ticker}: LONGTERM, catastrophic_floor={cat_str}, thesis_exits=[{checkpoints}]"
                if ts.get("note"):
                    line += f" ({ts['note']})"
                new_stops[ticker] = (catastrophic_stop, "catastrophic")
            else:
                # SWING trailing stop — ratchet with high-water mark
                stop_val = ts.get("stop")
                stop_str = f"{stop_val:.1f}k" if stop_val else "none"
                line = (
                    f"- {ticker}: stop={stop_str}, type={ts['stop_type']}, hint={ts['action_hint']}"
                )
                if ts.get("note"):
                    line += f" ({ts['note']})"
                if stop_val:
                    new_stops[ticker] = (stop_val, ts["stop_type"])
            stop_lines.append(line)

        # Upsert new stop high-water marks (GREATEST ensures no regression)
        if new_stops:
            today_date = (
                scan_date
                if isinstance(scan_date, date)
                else datetime.strptime(scan_date, "%Y-%m-%d").date()
            )
            for ticker, (stop_val, stop_type) in new_stops.items():
                # SWI-157 (2026-05-14): `breakeven_floor` rows track the holding
                # record's catastrophic floor (which can drop on averaging-down)
                # and therefore bypass the ratchet. Trailing strategies
                # (`trailing_50pct`, `trailing_tight`) keep GREATEST — never
                # give back gains.
                await db.execute(
                    """
                    INSERT INTO trailing_stops (ticker, stop_level, stop_type, updated_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (ticker) DO UPDATE
                      SET stop_level = CASE
                            WHEN EXCLUDED.stop_type = 'breakeven_floor' THEN EXCLUDED.stop_level
                            ELSE GREATEST(trailing_stops.stop_level, EXCLUDED.stop_level)
                          END,
                          stop_type = CASE
                            WHEN EXCLUDED.stop_type = 'breakeven_floor' THEN EXCLUDED.stop_type
                            WHEN EXCLUDED.stop_level > trailing_stops.stop_level THEN EXCLUDED.stop_type
                            ELSE trailing_stops.stop_type
                          END,
                          updated_at = EXCLUDED.updated_at
                    """,
                    ticker,
                    stop_val,
                    stop_type,
                    today_date,
                )
            print(f"Upserted {len(new_stops)} trailing stop high-water marks")

    print(f"Pre-computed trailing stops for {len(by_ticker)} tickers")
    return "\n".join(stop_lines)
