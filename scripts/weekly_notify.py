#!/usr/bin/env python3
"""
Weekly Watchlist Update Telegram Notification

Sends the weekly update report to Telegram with:
- Sector rotation signals
- Removed stocks with reasons
- Added stocks with entry suggestions
- Weekly outlook
"""

import json
from pathlib import Path

from shared.config import get_scan_date
from shared.telegram import send_telegram

TODAY = get_scan_date()
WEEKLY_UPDATES_DIR = Path(__file__).parent.parent / "research" / "weekly-updates"


def load_weekly_report():
    """Load the weekly update report JSON file."""
    filepath = WEEKLY_UPDATES_DIR / f"{TODAY}.json"
    if not filepath.exists():
        return None

    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def format_weekly_message(report: dict) -> str:
    """Format weekly report as Telegram message."""
    # Support both old nested and new flat format (post-PydanticAI migration)
    rotation = report.get("sector_rotation", {})
    scoring = report.get("scoring", {})
    reasoning = report.get("reasoning", {})

    # Prefer flat keys (new format), fall back to nested (old format)
    hot = report.get("hot_sectors") or rotation.get("hot_sectors", [])
    cold = report.get("cold_sectors") or rotation.get("cold_sectors", [])
    rotation_signal = report.get("rotation_signal") or rotation.get("rotation_signal")
    removals = report.get("removals") or scoring.get("removals", [])
    additions = report.get("additions") or scoring.get("additions", [])
    market_summary = report.get("market_summary") or reasoning.get("market_summary")
    weekly_outlook = report.get("weekly_outlook") or reasoning.get("weekly_outlook")

    lines = []

    # Header
    lines.append(f"<b>Weekly Watchlist Update - {TODAY}</b>")
    lines.append("")

    # Sector Rotation
    if hot:
        lines.append(f"HOT: {', '.join(s.upper() for s in hot)}")
    if cold:
        lines.append(f"COLD: {', '.join(s.upper() for s in cold)}")
    if rotation_signal:
        lines.append(f"<i>{rotation_signal}</i>")
    lines.append("")

    # Removals
    if removals:
        lines.append("<b>REMOVED:</b>")
        for r in removals:
            reasons = ", ".join(r.get("reasons", [])[:2])
            lines.append(f"  {r['ticker']} - {reasons}")
        lines.append("")

    # Additions
    if additions:
        lines.append("<b>ADDED:</b>")
        for a in additions:
            sector = a.get("sector", "")
            reasons = ", ".join(a.get("reasons", [])[:2])
            lines.append(f"  {a['ticker']} ({sector}) - {reasons}")
        lines.append("")

    # Market summary and outlook
    if market_summary:
        lines.append(f"<b>Market:</b> {market_summary}")
        lines.append("")

    if weekly_outlook:
        lines.append(f"<b>Outlook:</b> {weekly_outlook}")

    # Summary stats
    lines.append("")
    lines.append(f"Removed: {len(removals)} | Added: {len(additions)}")

    return "\n".join(lines)


def main():
    """Main entry point."""
    print(f"\n{'=' * 60}")
    print(f"Weekly Update Telegram Notification - {TODAY}")
    print(f"{'=' * 60}\n")

    # Load report
    report = load_weekly_report()
    if not report:
        print(f"Error: Weekly report not found at {WEEKLY_UPDATES_DIR / f'{TODAY}.json'}")
        print("Run weekly_watchlist_update.py first.")
        return

    print(f"Report date: {report.get('date', 'unknown')}")

    # Format and send
    try:
        message = format_weekly_message(report)
        print(f"Message length: {len(message):,} characters")
        send_telegram(message, parse_mode="HTML")
        print(f"\n{'=' * 60}")
        print("Weekly notification sent!")
        print(f"{'=' * 60}\n")
    except Exception as e:
        print(f"Error sending notification: {e}")
        raise


if __name__ == "__main__":
    main()
