#!/usr/bin/env python3
"""
Seed golden eval cases from retrospective production data.

Queries Neon (read-only) to extract labeled outcomes:
- market_regimes + daily_records → regime classification with EOD accuracy
- daily_technicals + daily_levels → VN-Index inputs for that day
- sector_rotations → rotation context

Usage:
    SWINGY_ENV=production uv run python evals/scripts/seed_from_retro.py
    SWINGY_ENV=production uv run python evals/scripts/seed_from_retro.py --days 30
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

OUTPUT_DIR = Path(__file__).parent.parent / "datasets" / "market_level"


async def fetch_regime_data(days: int = 14) -> list[dict]:
    """Fetch regime + technicals + rotation for recent trading days."""
    from shared.database import Database, fetch_all

    async with Database():
        # Get regimes with next-day outcome
        regimes = await fetch_all(
            """
            SELECT
                mr.scan_date,
                mr.regime,
                mr.regime_confidence,
                mr.vn_index_value,
                mr.vn_index_change_pct,
                mr.key_signal,
                dr.next_day_change_pct,
                dr.win_rate,
                dr.entry_hit_rate,
                dr.market_regime AS retro_regime
            FROM market_regimes mr
            LEFT JOIN daily_records dr ON dr.record_date = mr.scan_date
            WHERE mr.scan_date >= CURRENT_DATE - $1
            ORDER BY mr.scan_date DESC
            """,
            days,
        )

        cases = []
        for row in regimes:
            scan_date = str(row["scan_date"])

            # daily_technicals and daily_levels tables were dropped (migration 150).
            # Historical per-date technicals are no longer available; eval cases use
            # vn_index_value / vn_index_change_pct from market_regimes instead.
            vnindex = []
            levels = []

            # Get sector rotation
            rotation = await fetch_all(
                """
                SELECT rotation_signal
                FROM sector_rotations
                WHERE scan_date = $1
                LIMIT 1
                """,
                row["scan_date"],
            )

            # Get regime history (5 days before)
            history = await fetch_all(
                """
                SELECT scan_date, regime, regime_confidence
                FROM market_regimes
                WHERE scan_date < $1
                ORDER BY scan_date DESC
                LIMIT 5
                """,
                row["scan_date"],
            )

            # Build inputs
            vn_tech = vnindex[0] if vnindex else {}
            vn_levels = levels[0] if levels else {}
            rot = rotation[0] if rotation else {}

            case = {
                "name": f"retro_{scan_date}",
                "inputs": {
                    "vnindex_technicals": {
                        "close": float(row["vn_index_value"]) if row["vn_index_value"] else None,
                        "rsi": float(vn_tech.get("rsi", 0)) if vn_tech.get("rsi") else None,
                        "ma20": float(vn_tech.get("ma20_vnd", 0))
                        if vn_tech.get("ma20_vnd")
                        else None,
                        "ma50": float(vn_tech.get("ma50_vnd", 0))
                        if vn_tech.get("ma50_vnd")
                        else None,
                        "price_vs_ma20": vn_tech.get("price_vs_ma20"),
                        "price_vs_ma50": vn_tech.get("price_vs_ma50"),
                        "levels": {
                            "swing_high": float(vn_levels.get("swing_high_vnd", 0))
                            if vn_levels.get("swing_high_vnd")
                            else None,
                            "swing_low": float(vn_levels.get("swing_low_vnd", 0))
                            if vn_levels.get("swing_low_vnd")
                            else None,
                            "nearest_support": float(vn_levels.get("nearest_support_vnd", 0))
                            if vn_levels.get("nearest_support_vnd")
                            else None,
                            "nearest_resistance": float(vn_levels.get("nearest_resistance_vnd", 0))
                            if vn_levels.get("nearest_resistance_vnd")
                            else None,
                        },
                    },
                    "sector_rotation": {
                        "hot": [],
                        "cold": [],
                        "signal": rot.get("rotation_signal", "Unknown"),
                    },
                    "regime_history": [
                        {
                            "date": str(h["scan_date"]),
                            "regime": h["regime"],
                            "confidence": float(h["regime_confidence"]),
                        }
                        for h in history
                    ],
                },
                "expected_output": {
                    "regime": row["regime"],
                    "min_confidence": 0.3,
                },
                "metadata": {
                    "source": "retrospective",
                    "scan_date": scan_date,
                    "next_day_change_pct": float(row["next_day_change_pct"])
                    if row.get("next_day_change_pct")
                    else None,
                    "retro_win_rate": float(row["win_rate"]) if row.get("win_rate") else None,
                },
            }
            cases.append(case)

        return cases


async def main():
    parser = argparse.ArgumentParser(description="Seed eval cases from retrospective data")
    parser.add_argument("--days", type=int, default=14, help="Days of history to extract")
    parser.add_argument("--output", default="regression", help="Output dataset name")
    args = parser.parse_args()

    # Load env
    from shared.env import load_env

    load_env()

    print(f"Fetching {args.days} days of regime data from production...")
    cases = await fetch_regime_data(args.days)
    print(f"Found {len(cases)} cases")

    if not cases:
        print("No cases found. Check database connection.")
        return

    # Write YAML
    output_path = OUTPUT_DIR / f"{args.output}.yaml"
    dataset = {"cases": cases}
    output_path.write_text(yaml.dump(dataset, default_flow_style=False, allow_unicode=True))
    print(f"Written to {output_path}")

    # Print summary
    regimes = {}
    for c in cases:
        r = c["expected_output"]["regime"]
        regimes[r] = regimes.get(r, 0) + 1
    print(f"Regime distribution: {regimes}")


if __name__ == "__main__":
    asyncio.run(main())
