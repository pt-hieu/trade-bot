#!/usr/bin/env python3
"""Pre-code verification V2 — are Vin-family tickers tagged to POSITIVE catalysts
in eligible lifecycle {ACTIVE, APPROACHING, APPROACHING_RESOLUTION} on rally dates?

Usage:
    uv run python scripts/adhoc/verify_catalyst_coverage.py \\
      --dates 2025-12-10 2025-12-15 2025-12-20 \\
      --tickers VHM VIC VRE
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.database import Database
from shared.rules.catalyst_lifecycle import resolve_phase_status
from shared.rules.catalyst_override import _BOOST_LIFECYCLES

_ELIGIBLE_CONFIDENCE = {"HIGH", "MEDIUM"}


async def _fetch_catalysts_for_ticker_on_date(
    db: Database, ticker: str, scan_date: str
) -> list[dict]:
    """Pull active catalyst rows that list this ticker in affected_tickers."""
    rows = await db.fetch_all(
        """
        SELECT catalyst_key, event, impact, confidence, affected_tickers, phases
        FROM catalysts
        WHERE $1 = ANY(affected_tickers)
          AND pipeline_version = 'v2'
          AND COALESCE(deprecated, FALSE) = FALSE
          AND (expires_at IS NULL OR expires_at >= $2::date)
          AND (created_at IS NULL OR created_at <= ($2::date + INTERVAL '1 day'))
        """,
        ticker.upper(),
        scan_date,
    )
    return [dict(row) for row in rows]


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--tickers", nargs="+", required=True)
    args = parser.parse_args()

    summary = {"total": 0, "eligible": 0, "positive_active": 0}
    rows_out: list[str] = []

    async with Database() as db:
        for scan_date in args.dates:
            for ticker in args.tickers:
                summary["total"] += 1
                catalysts = await _fetch_catalysts_for_ticker_on_date(db, ticker, scan_date)
                if not catalysts:
                    rows_out.append(f"{scan_date} {ticker:6s} 0 catalysts")
                    continue

                hits = []
                for catalyst in catalysts:
                    impact = (catalyst.get("impact") or "").upper()
                    confidence = (catalyst.get("confidence") or "").upper()
                    if impact != "POSITIVE" or confidence not in _ELIGIBLE_CONFIDENCE:
                        continue
                    phases = catalyst.get("phases")
                    if not phases:
                        hits.append(("STATIC", catalyst.get("catalyst_key") or ""))
                        continue
                    status = resolve_phase_status(phases)
                    if status.is_relevant and status.lifecycle in _BOOST_LIFECYCLES:
                        hits.append((status.lifecycle, catalyst.get("catalyst_key") or ""))

                if hits:
                    summary["positive_active"] += 1
                    summary["eligible"] += len(hits)
                    lifecycles = ", ".join(f"{lc}:{key}" for lc, key in hits[:3])
                    rows_out.append(
                        f"{scan_date} {ticker:6s} {len(catalysts)} catalysts, "
                        f"{len(hits)} boost-eligible [{lifecycles}]"
                    )
                else:
                    rows_out.append(
                        f"{scan_date} {ticker:6s} {len(catalysts)} catalysts, 0 boost-eligible"
                    )

    print("=" * 80)
    print("VIN-FAMILY CATALYST COVERAGE (Phase 0 V2)")
    print("=" * 80)
    for row in rows_out:
        print(row)
    print("-" * 80)
    print(f"Total (ticker, date) pairs:           {summary['total']}")
    print(f"Pairs with >=1 boost-eligible row:    {summary['positive_active']}")
    print(f"Total boost-eligible catalysts:       {summary['eligible']}")
    print("=" * 80)
    if summary["positive_active"] == 0:
        print(
            "WARNING: zero positive-active catalysts for Vin-family on rally dates — "
            "catalyst ingestion likely needs fixing before promotion logic ships."
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
