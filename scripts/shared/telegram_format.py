"""Shared markdown → Telegram HTML formatting helpers.

Used by retro_notify.py, midday_notify.py, telegram_notify.py to avoid
duplicating the same regex transformations.
"""

import re


def strip_markdown_headers(text: str) -> str:
    """Strip common markdown report headers.

    Removes:
    - `# Title` heading (first line)
    - `*Generated at ...* ` timestamp line
    - `---` horizontal rules
    """
    text = re.sub(r"^# .+\n", "", text)
    text = re.sub(r"^\*Generated.+\*\n", "", text)
    text = re.sub(r"^---\n", "", text, flags=re.MULTILINE)
    return text


def bold_to_html(text: str) -> str:
    """Convert markdown **bold** to Telegram <b>bold</b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def allcaps_to_bold(text: str) -> str:
    """Convert ALL-CAPS header lines (>3 chars) to <b>HEADER</b>."""
    return re.sub(
        r"^([A-Z][A-Z '\-]+)$",
        lambda m: f"<b>{m.group(1).strip()}</b>" if len(m.group(1).strip()) > 3 else m.group(0),
        text,
        flags=re.MULTILINE,
    )


def strip_tool_citations(text: str) -> str:
    """Strip internal [tool_name/field] citation markers from LLM output.

    Removes patterns like [tool_get_similar_days/regime], [STRUCTURAL_CATALYSTS],
    [trading_rules/AVOID_HOLD_signals], [articles: #uuid/source].
    """
    return re.sub(r"\s*\[[a-zA-Z_][a-zA-Z0-9_/:#\- .]*\]", "", text)


def collapse_newlines(text: str) -> str:
    """Collapse 3+ consecutive newlines to 2."""
    return re.sub(r"\n{3,}", "\n\n", text)


def md_to_telegram_html(text: str) -> str:
    """Full pipeline: strip headers → citations → bold → ALL-CAPS → collapse newlines."""
    text = strip_markdown_headers(text)
    text = strip_tool_citations(text)
    text = bold_to_html(text)
    text = allcaps_to_bold(text)
    text = collapse_newlines(text)
    return text.strip()
