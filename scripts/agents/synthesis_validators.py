"""
Validation and conflict-detection functions for synthesis output.

Pure text-parsing functions — no agent, no async, no LLM dependencies.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_LEVEL_PREFIXES = ("entry", "stop", "target", "r:r", "shares", "leg ", "time stop")

_NON_TICKERS = frozenset(
    {
        "TOP",
        "SKIP",
        "BUY",
        "THE",
        "AND",
        "FOR",
        "NOT",
        "ALL",
        "BUT",
        "SET",
        "ADD",
        "ANY",
        "USE",
        "GET",
        "HAS",
        "HOT",
        "LOW",
        "MAX",
        "MIN",
        "NEW",
        "OLD",
        "OUR",
        "RUN",
        "WAR",
        "DAY",
        "KEY",
        "NET",
        "RSI",
        "HOLD",
        "WAIT",
        "TRIM",
        "EXIT",
        "WHAT",
        "LONG",
        "TERM",
        "EACH",
        "ALSO",
        "KEEP",
        "THIS",
        "THAT",
        "WITH",
        "FROM",
        "WILL",
        "WERE",
        "BEEN",
        "HAVE",
        "DOES",
        "GOES",
    }
)


def validate_synthesis_output(
    output: str,
    mode: str | None,
    deployable: float | None,
    pre_computed_picks: list[dict] | None = None,
) -> tuple[str, list[str]]:
    """Validate synthesis output respects trading mode rules.

    Args:
        output: The raw synthesis output string
        mode: Trading mode (NORMAL/LOW_CASH/REALLOCATION)
        deployable: Deployable cash amount
        pre_computed_picks: Structured pick payloads — used to exempt
            ATR_TRAIL picks (which legitimately carry no fixed target)
            from the incomplete-BUY "missing: target" check (SWI-340 SSOT).

    Returns:
        Tuple of (possibly modified output, list of warnings)
    """
    from shared.rules.exit_strategy import is_trailing_exit

    warnings = []

    if not mode or not output:
        return output, warnings

    # Trailing picks (ATR_TRAIL family or target=None) have no fixed
    # target by design — reading the structured exit-family via the SSOT
    # predicate breaks the text-grep coupling that flagged only VRE while
    # VCB/VHM escaped incidentally (run2 2026-05-14, 5th ATR_TRAIL recurrence).
    trailing_tickers = {
        (pick.get("ticker") or "").upper()
        for pick in (pre_computed_picks or [])
        if is_trailing_exit(pick)
    }

    # Parse TOP PICKS section to check for BUY recommendations
    top_picks_start = output.find("TOP PICKS")
    skip_these_start = output.find("SKIP THESE")

    if top_picks_start == -1:
        return output, warnings

    # Extract TOP PICKS section
    if skip_these_start > top_picks_start:
        top_picks_section = output[top_picks_start:skip_these_start]
    else:
        top_picks_section = output[top_picks_start:]

    # Check for BUY-like entries (lines with Entry/Stop/Target or R:R)
    has_buy_recs = "Entry" in top_picks_section and "Target" in top_picks_section

    # LOW_CASH mode with 0 deployable: No BUYs allowed
    if mode == "LOW_CASH" and (deployable is None or deployable <= 0):
        if has_buy_recs:
            warnings.append(
                f"MODE VIOLATION: {mode} mode with 0 deployable cash - TOP PICKS should be empty"
            )

    # REALLOCATION mode: BUYs require EXIT
    elif mode == "REALLOCATION" and has_buy_recs:
        # Check MY HOLDINGS for EXIT
        my_holdings_start = output.find("MY HOLDINGS")
        top_picks_idx = output.find("TOP PICKS")

        if my_holdings_start != -1 and top_picks_idx > my_holdings_start:
            holdings_section = output[my_holdings_start:top_picks_idx]
            has_exit = "EXIT" in holdings_section.upper()

            if not has_exit:
                warnings.append(
                    "MODE VIOLATION: REALLOCATION mode - "
                    "TOP PICKS with BUY requires EXIT recommendation in MY HOLDINGS"
                )

    # ── Duplicate rationale + incomplete BUY validation ─────────────────
    seen_rationales: dict[str, str] = {}  # normalized_text -> first ticker
    ticker_blocks = re.split(r"\n(?=[A-Z]{3}[\s:(])", top_picks_section)

    for block in ticker_blocks:
        ticker_match = re.match(r"([A-Z]{3})", block.strip())
        if not ticker_match:
            continue
        ticker_name = ticker_match.group(1)
        block_upper = block.upper()

        # Duplicate rationale: check non-structural lines
        for line in block.split("\n"):
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("#")
                or any(stripped.lower().startswith(prefix) for prefix in _LEVEL_PREFIXES)
            ):
                continue
            normalized = stripped.lower()
            if normalized in seen_rationales:
                first_ticker = seen_rationales[normalized]
                if first_ticker != ticker_name:
                    truncated = stripped[:80]
                    ellipsis = "..." if len(stripped) > 80 else ""
                    warnings.append(
                        f"DUPLICATE RATIONALE: {first_ticker} and {ticker_name} "
                        f"share identical text: '{truncated}{ellipsis}'"
                    )
            else:
                seen_rationales[normalized] = ticker_name

        # Incomplete BUY: verify entry/stop/target present. Trailing picks
        # are exempt from the TARGET requirement (no fixed target by design).
        if "BUY" in block_upper and ticker_name not in trailing_tickers:
            missing = [field for field in ("ENTRY", "STOP", "TARGET") if field not in block_upper]
            if missing:
                warnings.append(
                    f"INCOMPLETE BUY: {ticker_name} has BUY but missing: "
                    f"{', '.join(field.lower() for field in missing)}"
                )
        elif "WATCH" in block_upper and "ENTRY" not in block_upper:
            logger.info("TOP_PICKS WATCH without entry level: %s — may be intentional", ticker_name)

    # ── Cross-section conflict detection ──────────────────────────────
    _detect_cross_section_conflicts(output, warnings)

    return output, warnings


def _extract_section_tickers(text: str, section_name: str) -> dict[str, str]:
    """Extract tickers and their actions from a named section.

    Returns dict of {ticker: action} found in the section.
    """
    section_start = text.upper().find(section_name.upper())
    if section_start == -1:
        return {}

    # Find next section boundary
    remaining = text[section_start + len(section_name) :]
    next_sections = [
        "TOP PICKS",
        "SKIP THESE",
        "MY HOLDINGS",
        "WHAT TO DO TODAY",
    ]
    end_idx = len(remaining)
    for next_section in next_sections:
        next_section_upper = next_section.upper()
        if next_section_upper == section_name.upper():
            continue
        idx = remaining.upper().find(next_section_upper)
        if idx != -1 and idx < end_idx:
            end_idx = idx

    section_text = remaining[:end_idx]
    tickers = {}
    for match in re.finditer(r"^([A-Z]{2,4})\b", section_text, re.MULTILINE):
        ticker = match.group(1)
        if ticker in _NON_TICKERS:
            continue
        # Determine action from surrounding text
        line_start = section_text.rfind("\n", 0, match.start()) + 1
        line_end = section_text.find("\n", match.end())
        if line_end == -1:
            line_end = len(section_text)
        line = section_text[line_start:line_end].upper()
        for action in (
            "LIMIT_BUY",
            "BUY",
            "WATCH",
            "WAIT",
            "HOLD",
            "TRIM",
            "EXIT",
            "ADD",
            "SKIP",
            "AVOID",
        ):
            if action in line:
                tickers[ticker] = action
                break
        else:
            tickers[ticker] = "MENTIONED"
    return tickers


def _detect_cross_section_conflicts(output: str, warnings: list[str]) -> None:
    """Detect tickers appearing in both actionable and skip sections."""
    skip_tickers = _extract_section_tickers(output, "SKIP THESE")
    top_pick_tickers = _extract_section_tickers(output, "TOP PICKS")

    # HOLD excluded: ticker can be HOLD (existing position) + SKIP (don't add more)
    actionable_actions = {"BUY", "LIMIT_BUY", "WATCH", "WAIT", "ADD", "ACCUMULATE"}

    for ticker, action in top_pick_tickers.items():
        if ticker in skip_tickers and action in actionable_actions:
            warnings.append(
                f"CROSS-SECTION CONFLICT: {ticker} is {action} in "
                f"TOP PICKS but {skip_tickers[ticker]} in SKIP THESE"
            )
