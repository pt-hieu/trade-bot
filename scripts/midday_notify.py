#!/usr/bin/env python3
"""
Midday Check Telegram Notification Script

Sends the midday market check to Telegram.

Usage:
    python scripts/midday_notify.py [--date YYYY-MM-DD]
"""

import argparse
import re
import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from shared.config import get_scan_date
from shared.telegram import send_telegram
from shared.telegram_format import (
    bold_to_html,
    collapse_newlines,
    strip_markdown_headers,
    strip_tool_citations,
)

RESEARCH_BASE = Path(__file__).parent.parent / "research"


def load_midday_check(date: str) -> str | None:
    """Load the midday check markdown file."""
    filepath = RESEARCH_BASE / date / "midday-check.md"
    if not filepath.exists():
        return None

    with open(filepath, encoding="utf-8") as f:
        return f.read()


def format_for_telegram(content: str) -> str:
    """Convert midday check to Telegram HTML format."""
    content = strip_markdown_headers(content)
    content = strip_tool_citations(content)

    # ## Headers → <b>HEADER</b>
    content = re.sub(r"^## (.+)$", r"<b>\1</b>", content, flags=re.MULTILINE)

    # Convert markdown tables to simple text
    content = re.sub(r"^\|(.+)\|$", r"\1", content, flags=re.MULTILINE)
    content = re.sub(r"\|[-]+", "", content)

    content = bold_to_html(content)
    content = collapse_newlines(content)
    return content.strip()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Send midday check to Telegram")
    parser.add_argument(
        "--date",
        default=get_scan_date(),
        help="Date of midday check (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    today = args.date

    print(f"\n{'=' * 60}")
    print(f"Midday Check Notification - {today}")
    print(f"{'=' * 60}\n")

    # Load midday check
    content = load_midday_check(today)
    if not content:
        # Graceful exit — midday_check writes a skip-stub in the 0-rec
        # path (MON-2026-04-16-001), but belt-and-suspenders here in
        # case stub write fails for any reason. Exiting 0 keeps the
        # workflow green so the commit step + downstream jobs still run.
        print(
            f"Warning: Midday check not found at {RESEARCH_BASE / today / 'midday-check.md'}",
        )
        print("Skipping Telegram notification.")
        sys.exit(0)

    print(f"Midday check length: {len(content):,} characters")

    # Format and send
    try:
        formatted = format_for_telegram(content)

        # Add header for Telegram
        header = f"<b>MIDDAY CHECK - {today}</b>\n\n"
        message = header + formatted

        send_telegram(message, parse_mode="HTML")

        print(f"\n{'=' * 60}")
        print("Notification sent!")
        print(f"{'=' * 60}\n")

    except Exception as e:
        print(f"Error sending notification: {e}")
        raise


if __name__ == "__main__":
    main()
