#!/usr/bin/env python3
"""
Telegram Notification Script

Sends the morning brief to a Telegram chat via Bot API.
Formats for phone-first reading: Message 1 = action brief, Message 2 = context.

Setup:
1. Create bot via @BotFather, get token
2. Get your chat_id (message @userinfobot or @get_id_bot)
3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as GitHub secrets
"""

import re

from shared.config import get_research_dir, get_scan_date
from shared.telegram import send_telegram
from shared.telegram_format import (
    allcaps_to_bold,
    bold_to_html,
    collapse_newlines,
    strip_tool_citations,
)
from telegram_compress import extract_holdings_tickers, filter_skip_holdings

TODAY = get_scan_date()
RESEARCH_DIR = get_research_dir()

# Sections to include in Message 1 (action-first)
_MSG1_SECTIONS = ["STANCE", "WHAT TO DO TODAY", "MY HOLDINGS", "TOP PICKS", "ENTRY CRITERIA TODAY"]

# Sections to include in Message 2 (context)
_MSG2_SECTIONS = [
    "TODAY'S THEME",
    "CAPITAL STATUS",
    "GLOBAL CONTEXT",
    "MARKET MOOD",
    "NEWS THAT MATTERS",
    "SECTOR FOCUS",
    "KEY RISK",
    "SKIP THESE",
]

# Sections to drop from Telegram entirely (available in web app / research file)
_SKIP_SECTIONS = {
    "GOAL PROGRESS",
    "MINDSET",
    "NARRATIVE REVIEW",
    "STRUCTURAL CATALYSTS",
    "CAPITAL EVENTS",
    "RETRO CONSTRAINTS",
    "PORTFOLIO NOTES",
}

# All known section header names (for boundary detection)
# Sorted longest-first to avoid prefix conflicts (e.g., "ENTRY CRITERIA TODAY" before "ENTRY")
_ALL_KNOWN_SORTED = sorted(
    set(_MSG1_SECTIONS) | set(_MSG2_SECTIONS) | _SKIP_SECTIONS,
    key=len,
    reverse=True,
)
_ALL_KNOWN = set(_ALL_KNOWN_SORTED)


def _match_section_header(stripped: str) -> str | None:
    """Match a line against known section headers.

    Exact-line equality only (SWI-127). ``_split_inline_sections`` already
    promotes inline-glued sections to their own lines, so the parser only
    needs to recognise bare ALL-CAPS headers here. Lenient ``startswith``
    previously matched prose citations like ``MY HOLDINGS / FPT:`` as
    real headers, corrupting downstream renders.
    """
    return stripped if stripped in _ALL_KNOWN else None


def _split_inline_sections(text: str) -> str:
    """Insert newlines before known section names embedded mid-line.

    LLM sometimes outputs all post-STRATEGY_BREAK sections on a single giant line.
    This ensures each section starts on its own line for the parser.
    """
    for name in _ALL_KNOWN_SORTED:
        # Insert newline before section name when preceded by non-newline content
        # Look for ". NAME" or "  NAME" patterns mid-line
        text = re.sub(
            rf"(?<=[.;!?\s])(?<!\n)\s*({re.escape(name)})(?=[ :(—\n])",
            r"\n\1",
            text,
        )
    return text


def _parse_sections(text: str) -> dict[str, str]:
    """Split brief text into a dict of {section_name: content}.

    Handles:
    - Strategy directive sections (THEME, STANCE, etc.) — plain ALL-CAPS headers
    - Stock sections (MY HOLDINGS, TOP PICKS, etc.) — same format, after STRATEGY_BREAK
    - Inline section headers like 'MY HOLDINGS (context): content...'
    - Sections on a single giant line (post-STRATEGY_BREAK LLM output)
    - The "## Final Brief Construction" preamble before stock sections is stripped
    """
    # Strip the file header and STRATEGY_BREAK marker
    text = re.sub(r"^# .+\n", "", text)
    text = re.sub(r"^\*Generated.+\*\n", "", text)
    text = re.sub(r"^---\n", "", text, flags=re.MULTILINE)
    text = text.replace("<!-- STRATEGY_BREAK -->", "")

    # Split sections that appear mid-line onto their own lines
    text = _split_inline_sections(text)

    # Strip "## Final Brief Construction\nBased on..." preamble before MY HOLDINGS
    text = re.sub(r"##.+?\n.*?\n\n", "", text, flags=re.DOTALL)

    # Strip "PORTFOLIO NOTES: ..." trailing line
    text = re.sub(r"\nPORTFOLIO NOTES:.*$", "", text, flags=re.DOTALL)

    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        matched = _match_section_header(stripped)
        if matched is not None:
            if current_name is not None:
                sections[current_name] = "\n".join(current_lines).strip()
            if matched in sections:
                # First occurrence wins — don't let inline references
                # (e.g. "SKIP THESE" inside NARRATIVE REVIEW bullets)
                # overwrite the real section parsed earlier.
                current_name = None
                current_lines = []
            else:
                current_name = matched
                # Capture inline content after the header name
                remainder = stripped[len(matched) :].lstrip(" :()\u2014\u2013\u2012-").strip()
                current_lines = [remainder] if remainder else []
        else:
            current_lines.append(line)

    if current_name is not None:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections


def _compress_capital(content: str) -> str:
    """Compress CAPITAL STATUS to a single summary line."""
    # Extract key values and inline them
    cash_m = re.search(r"Cash:\s*(\S+)", content)
    reserve_m = re.search(r"Reserve:\s*(\S+)", content)
    deploy_m = re.search(r"Deployable:\s*(\S+)", content)
    scale_m = re.search(r"Scale:\s*(\S+)", content)
    wr_m = re.search(r"(\d+)%\s*win rate", content)

    parts = []
    if cash_m:
        parts.append(f"{cash_m.group(1)} cash")
    if reserve_m:
        parts.append(f"{reserve_m.group(1)} reserve")
    if deploy_m:
        parts.append(f"{deploy_m.group(1)} deploy")
    if scale_m and wr_m:
        parts.append(f"{scale_m.group(1)} ({wr_m.group(1)}% WR)")
    elif scale_m:
        parts.append(f"scale {scale_m.group(1)}")

    if parts:
        return " | ".join(parts)
    return content


def _compress_market(global_ctx: str, market_mood: str) -> str:
    """Merge GLOBAL CONTEXT + MARKET MOOD into compact MARKET block."""
    lines = []

    # Regime from MARKET MOOD
    regime_m = re.search(r"Regime:\s*(\w+)\s*\((\d+)%\)", market_mood or "")
    if regime_m:
        lines.append(f"Regime: {regime_m.group(1)} ({regime_m.group(2)}%)")

    # Risk regime from GLOBAL CONTEXT
    risk_m = re.search(r"Risk Regime:\s*(\w+)", global_ctx or "")
    if risk_m:
        risk_text = f"Risk: {risk_m.group(1)}"
        if lines:
            lines[-1] += f" | {risk_text}"
        else:
            lines.append(risk_text)

    # Macro numbers (DXY | VIX | USD/VND line)
    macro_m = re.search(r"(DXY:.+)", global_ctx or "")
    if macro_m:
        lines.append(macro_m.group(1))

    return "\n".join(lines) if lines else (global_ctx or "").strip()


def _compress_entry_criteria(content: str) -> str:
    """Compress ENTRY CRITERIA TODAY to a single line."""
    # Keep the first data line (Min R:R | Max entries | Budget)
    first = next(
        (line.strip() for line in content.splitlines() if line.strip().startswith("-")), None
    )
    if first:
        return first.lstrip("- ")
    return content.strip()


def _stance_line(content: str) -> str:
    """Extract the first non-empty line from STANCE section."""
    for line in content.splitlines():
        if line.strip():
            return line.strip()
    return content.strip()


def _to_html(text: str) -> str:
    """Convert plain text to minimal Telegram HTML (bold headers only)."""
    text = strip_tool_citations(text)
    text = allcaps_to_bold(text)
    text = bold_to_html(text)
    text = collapse_newlines(text)
    return text.strip()


def _assemble_action_brief(sections: dict[str, str]) -> str:
    """Build Message 1: action-first brief for phone scanning."""
    parts = []

    # STANCE (first line only — the stance + why)
    if "STANCE" in sections:
        parts.append(_stance_line(sections["STANCE"]))
        parts.append("")

    # WHAT TO DO TODAY
    if "WHAT TO DO TODAY" in sections:
        parts.append("WHAT TO DO TODAY")
        parts.append(sections["WHAT TO DO TODAY"])
        parts.append("")

    # MY HOLDINGS
    if "MY HOLDINGS" in sections:
        parts.append("MY HOLDINGS")
        parts.append(sections["MY HOLDINGS"])
        parts.append("")

    # TOP PICKS
    if "TOP PICKS" in sections:
        parts.append("TOP PICKS")
        parts.append(sections["TOP PICKS"])
        parts.append("")

    # ENTRY CRITERIA — compressed to 1 line
    if "ENTRY CRITERIA TODAY" in sections:
        parts.append("Entry: " + _compress_entry_criteria(sections["ENTRY CRITERIA TODAY"]))

    return "\n".join(parts).strip()


def _assemble_context_brief(sections: dict[str, str]) -> str:
    """Build Message 2: context for reference."""
    parts = []

    # TODAY'S THEME (just the content, no header)
    if "TODAY'S THEME" in sections:
        parts.append(sections["TODAY'S THEME"])
        parts.append("")

    # CAPITAL STATUS — compressed to 1 line
    if "CAPITAL STATUS" in sections:
        parts.append("CAPITAL: " + _compress_capital(sections["CAPITAL STATUS"]))
        parts.append("")

    # MARKET — merged GLOBAL CONTEXT + MARKET MOOD
    market = _compress_market(
        sections.get("GLOBAL CONTEXT", ""),
        sections.get("MARKET MOOD", ""),
    )
    if market:
        parts.append("MARKET")
        parts.append(market)
        parts.append("")

    # NEWS THAT MATTERS
    if "NEWS THAT MATTERS" in sections:
        parts.append("NEWS")
        parts.append(sections["NEWS THAT MATTERS"])
        parts.append("")

    # SECTOR FOCUS
    if "SECTOR FOCUS" in sections:
        parts.append("SECTORS")
        parts.append(sections["SECTOR FOCUS"])
        parts.append("")

    # KEY RISK — first line only
    if "KEY RISK" in sections:
        key_risk = sections["KEY RISK"]
        first_line = next((line.strip() for line in key_risk.splitlines() if line.strip()), "")
        parts.append("KEY RISK: " + first_line.lstrip("- "))
        parts.append("")

    # SKIP THESE — filter out held stocks
    if "SKIP THESE" in sections:
        held_tickers = extract_holdings_tickers(sections.get("MY HOLDINGS", ""))
        skip_content = filter_skip_holdings(sections["SKIP THESE"], held_tickers)
        if skip_content:
            parts.append("SKIP")
            parts.append(skip_content)

    return "\n".join(parts).strip()


def load_morning_brief() -> str | None:
    """Load the morning brief markdown file."""
    filepath = RESEARCH_DIR / "morning-brief.md"
    if not filepath.exists():
        return None
    with open(filepath, encoding="utf-8") as f:
        return f.read()


def main():
    """Main entry point."""
    print(f"\n{'=' * 60}")
    print(f"Telegram Notification - {TODAY}")
    print(f"{'=' * 60}\n")

    content = load_morning_brief()
    if not content:
        print(f"Error: Morning brief not found at {RESEARCH_DIR / 'morning-brief.md'}")
        print("Run llm_analysis.py first.")
        return

    print(f"Brief length: {len(content):,} characters")

    sections = _parse_sections(content)
    print(f"Parsed sections: {list(sections.keys())}")

    if not sections:
        # Brief is an error message (e.g., no market data) — send raw text
        print("No sections parsed — sending raw brief as notification")
        try:
            send_telegram(content.strip(), parse_mode=None)
            print("Raw brief sent.")
        except Exception as raw_error:
            print(f"Failed to send raw brief: {raw_error}")
        return

    action_brief = _assemble_action_brief(sections)
    context_brief = _assemble_context_brief(sections)

    messages = [
        ("Action brief", action_brief),
        ("Context", context_brief),
    ]

    try:
        for label, text in messages:
            if not text.strip():
                print(f"Skipping {label} (empty)")
                continue
            html = _to_html(text)
            print(f"Sending {label} ({len(html):,} chars)...")
            send_telegram(html, parse_mode="HTML", split_on="\n\n")
        print(f"\n{'=' * 60}")
        print("Notification sent!")
        print(f"{'=' * 60}\n")
    except Exception as e:
        print(f"Error sending notification: {e}")
        raise


if __name__ == "__main__":
    main()
