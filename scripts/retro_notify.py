#!/usr/bin/env python3
"""
Retrospective Telegram Notification Script

Sends the market close retrospective to Telegram.

Usage:
    python scripts/retro_notify.py [--date YYYY-MM-DD]
"""

import argparse
import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from shared.config import get_scan_date
from shared.telegram import send_telegram
from shared.telegram_format import (
    allcaps_to_bold,
    collapse_newlines,
    strip_markdown_headers,
    strip_tool_citations,
)

RESEARCH_BASE = Path(__file__).parent.parent / "research"


def load_retrospective(date: str) -> str | None:
    """Load the retrospective markdown file."""
    filepath = RESEARCH_BASE / date / "retrospective.md"
    if not filepath.exists():
        return None

    with open(filepath, encoding="utf-8") as f:
        return f.read()


def format_for_telegram(content: str) -> str:
    """Convert retrospective to Telegram HTML format."""
    content = strip_markdown_headers(content)
    content = strip_tool_citations(content)
    content = allcaps_to_bold(content)
    content = collapse_newlines(content)
    return content.strip()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Send retrospective to Telegram")
    parser.add_argument(
        "--date",
        default=get_scan_date(),
        help="Date of retrospective (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    today = args.date

    print(f"\n{'=' * 60}")
    print(f"Retrospective Notification - {today}")
    print(f"{'=' * 60}\n")

    # Load retrospective
    content = load_retrospective(today)
    if not content:
        print(f"Error: Retrospective not found at {RESEARCH_BASE / today / 'retrospective.md'}")
        print("Run retrospective.py first.")
        sys.exit(1)

    print(f"Retrospective length: {len(content):,} characters")

    # Format and send
    try:
        formatted = format_for_telegram(content)

        # Add header for Telegram
        header = f"<b>MARKET CLOSE RETROSPECTIVE - {today}</b>\n\n"
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
