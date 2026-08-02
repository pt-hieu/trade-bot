"""Text extraction utilities for pipeline."""

import re


def extract_exit_tickers(holdings_text: str) -> list[str]:
    """Extract tickers with EXIT recommendation from holdings writer output.

    Looks for patterns like 'VHM: EXIT' or 'EXIT VHM' or 'VHM ... EXIT' in MY HOLDINGS section.
    Returns list of uppercase ticker strings.
    """
    if not holdings_text:
        return []

    # Narrow to MY HOLDINGS section only (stop at next section boundary)
    upper_text = holdings_text.upper()
    holdings_start = upper_text.find("MY HOLDINGS")

    if holdings_start == -1:
        section = holdings_text
    else:
        # Find the next section after MY HOLDINGS
        next_section_boundaries = [
            "LONG-TERM PORTFOLIO",
            "TOP PICKS",
            "SKIP THESE",
            "WHAT TO DO TODAY",
        ]
        end = len(holdings_text)
        for boundary in next_section_boundaries:
            boundary_pos = upper_text.find(boundary, holdings_start + len("MY HOLDINGS"))
            if boundary_pos > holdings_start and boundary_pos < end:
                end = boundary_pos
        section = holdings_text[holdings_start:end]

    # Match lines containing EXIT alongside a 2-3 char uppercase ticker
    # Patterns: "VHM: EXIT", "EXIT VHM", "VHM - EXIT", "Action: EXIT (VHM)"
    ticker_pattern = re.compile(r"\b([A-Z]{2,4})\b")
    exit_tickers = []

    for line in section.split("\n"):
        line_upper = line.upper()
        if "EXIT" not in line_upper:
            continue
        tickers_in_line = ticker_pattern.findall(line)
        for ticker in tickers_in_line:
            # Filter out common non-ticker words
            if ticker in ("EXIT", "TRIM", "HOLD", "ADD", "BUY", "SELL", "MY", "THE", "AND", "FOR"):
                continue
            if ticker not in exit_tickers:
                exit_tickers.append(ticker)

    return exit_tickers
