"""Brief section extraction for pipeline consumers.

Parses morning brief markdown into sections by ALL-CAPS headers.
Extracts only actionable sections, skipping preamble (theme, stance, macro, news).
"""

import re

# Sections the alert registrar needs
ACTIONABLE_SECTIONS = frozenset(
    {
        "MY HOLDINGS",
        "TOP PICKS",
        "WHAT TO DO TODAY",
    }
)

# All known section headers in the brief (for boundary detection)
ALL_BRIEF_SECTIONS = frozenset(
    {
        "TODAY'S THEME",
        "STANCE",
        "GOAL PROGRESS",
        "CAPITAL STATUS",
        "ENTRY CRITERIA TODAY",
        "GLOBAL CONTEXT",
        "MARKET MOOD",
        "NEWS THAT MATTERS",
        "SECTOR FOCUS",
        "KEY RISK",
        "MY HOLDINGS",
        "TOP PICKS",
        "SKIP THESE",
        "WHAT TO DO TODAY",
        "MINDSET",
        "STRUCTURAL CATALYSTS",
        "CAPITAL EVENTS",
        "RETRO CONSTRAINTS",
        "PORTFOLIO NOTES",
        # Retrospective brief sections (for collect_review_data parsing)
        "SCORECARD",
        "HITS",
        "PATTERN UPDATE",
        "STREAK ALERT",
        "TOMORROW'S EDGE",
        "MODE COMPLIANCE",
    }
)

# Sorted longest-first to avoid prefix conflicts (e.g., "ENTRY CRITERIA TODAY" before "ENTRY")
_SORTED_HEADERS = sorted(ALL_BRIEF_SECTIONS, key=len, reverse=True)


def _match_header(stripped: str) -> str | None:
    """Match a stripped line against known section headers.

    Exact-line equality only (SWI-127). Lenient ``startswith`` matched
    critic citations like ``MY HOLDINGS / FPT: [verb_plan_mismatch]`` as
    a section header, then last-write-wins overwrote the real stanza
    with the prose-only continuation.
    """
    return stripped if stripped in ALL_BRIEF_SECTIONS else None


def _split_inline_sections(text: str) -> str:
    """Insert newlines before section names embedded mid-line.

    LLM sometimes outputs all post-STRATEGY_BREAK sections on a single line.
    """
    for name in _SORTED_HEADERS:
        text = re.sub(
            rf"(?<=[.;!?\s])(?<!\n)\s*({re.escape(name)})(?=[ :(—\n])",
            r"\n\1",
            text,
        )
    return text


def extract_actionable_sections(
    brief_text: str,
    section_names: frozenset[str] | None = None,
) -> dict[str, str]:
    """Parse brief into {section_name: content}, returning only requested sections.

    Args:
        brief_text: Full morning brief markdown text.
        section_names: Which sections to extract. Defaults to ACTIONABLE_SECTIONS.

    Returns:
        Dict mapping section name to its content (without the header line).
    """
    if not brief_text:
        return {}

    target_sections = section_names or ACTIONABLE_SECTIONS

    # Strip STRATEGY_BREAK marker and file header
    text = brief_text.replace("<!-- STRATEGY_BREAK -->", "")
    text = re.sub(r"^# .+\n", "", text)
    text = re.sub(r"^\*Generated.+\*\n", "", text)
    text = _split_inline_sections(text)

    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        matched_header = _match_header(stripped)
        if matched_header is not None:
            if current_name is not None and current_name in target_sections:
                sections[current_name] = "\n".join(current_lines).strip()
            # First-occurrence-wins (SWI-127): a later duplicate header
            # (e.g. inline-split critic citation) must not clobber the
            # real stanza already captured.
            current_name = None if matched_header in sections else matched_header
            current_lines = []
        else:
            current_lines.append(line)

    # Flush last section
    if current_name is not None and current_name in target_sections:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections
