"""Compress sector analysis text into structured summaries for synthesis."""

import logging
import re

logger = logging.getLogger(__name__)


def compress_sector_for_synthesis(sector_text: str, max_chars: int = 1500) -> str:
    """Compress a sector analysis text into a structured summary.

    Extracts per-ticker: signal, confidence, key_risk, one-line thesis.
    Returns ~3 lines per ticker instead of full paragraphs.

    If parsing fails, truncates at last complete ticker boundary
    (not arbitrary char count) to avoid misleading the LLM.
    """
    if not sector_text or len(sector_text) < 200:
        return sector_text  # Already short enough

    try:
        return _parse_and_compress(sector_text)
    except Exception as parse_error:
        logger.warning(
            "Sector compression parse failed, truncating at ticker boundary: %s",
            parse_error,
        )
        return _truncate_at_ticker_boundary(sector_text, max_chars)


def _parse_and_compress(sector_text: str) -> str:
    """Parse sector text and extract structured per-ticker summaries."""
    lines = sector_text.split("\n")
    compressed_lines = []
    current_ticker = None
    current_signal = ""
    current_confidence = ""
    current_risk = ""
    current_thesis = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect ticker headers: "### FPT" or "FPT:" or "FPT (Banking)"
        ticker_match = re.match(r"^(?:#{1,3}\s+)?([A-Z]{2,4})(?:\s*[:(]|\s*$)", stripped)
        if ticker_match:
            # Flush previous ticker
            if current_ticker:
                compressed_lines.append(
                    _format_ticker_summary(
                        current_ticker,
                        current_signal,
                        current_confidence,
                        current_risk,
                        current_thesis,
                    )
                )
            current_ticker = ticker_match.group(1)
            current_signal = ""
            current_confidence = ""
            current_risk = ""
            current_thesis = ""
            continue

        # Extract signal (BUY/WATCH/WAIT/AVOID/SKIP)
        signal_match = re.search(r"\b(BUY|WATCH|WAIT|AVOID|SKIP|HOLD|TRIM|EXIT|ADD)\b", stripped)
        if signal_match and not current_signal:
            current_signal = signal_match.group(1)

        # Extract confidence
        confidence_match = re.search(r"\b(HIGH|MEDIUM|LOW)\b", stripped, re.IGNORECASE)
        if confidence_match and not current_confidence:
            current_confidence = confidence_match.group(1).upper()

        # Extract key risk
        if "risk" in stripped.lower() and not current_risk:
            current_risk = stripped[:120]

        # First substantive line as thesis (not a field label)
        if (
            not current_thesis
            and len(stripped) > 30
            and not stripped.startswith(("Signal", "Confidence", "Risk", "Key", "-", "*"))
        ):
            current_thesis = stripped[:150]

    # Flush last ticker
    if current_ticker:
        compressed_lines.append(
            _format_ticker_summary(
                current_ticker,
                current_signal,
                current_confidence,
                current_risk,
                current_thesis,
            )
        )

    if not compressed_lines:
        logger.warning("Sector compression produced no tickers, returning original")
        return sector_text

    return "\n".join(compressed_lines)


def _format_ticker_summary(
    ticker: str,
    signal: str,
    confidence: str,
    key_risk: str,
    thesis: str,
) -> str:
    """Format a single ticker's compressed summary."""
    parts = [f"{ticker}: {signal or 'N/A'}"]
    if confidence:
        parts[0] += f" [{confidence}]"
    if thesis:
        parts.append(f"  {thesis}")
    if key_risk:
        parts.append(f"  Risk: {key_risk}")
    return "\n".join(parts)


def _truncate_at_ticker_boundary(text: str, max_chars: int) -> str:
    """Truncate text at the last complete ticker section before max_chars.

    Finds the last section header (### TICKER or TICKER:) before the limit
    and cuts there, preserving complete ticker analyses.
    """
    if len(text) <= max_chars:
        return text

    # Find all potential ticker section boundaries
    boundary_pattern = re.compile(r"\n(?=(?:#{1,3}\s+)?[A-Z]{2,4}[\s:(])", re.MULTILINE)
    boundaries = [match.start() for match in boundary_pattern.finditer(text)]

    # Find the last boundary before max_chars
    last_safe_boundary = 0
    for boundary_position in boundaries:
        if boundary_position <= max_chars:
            last_safe_boundary = boundary_position
        else:
            break

    if last_safe_boundary > 0:
        return text[:last_safe_boundary].rstrip() + "\n[... compressed]"

    # No boundary found — hard truncate at max_chars
    return text[:max_chars].rstrip() + "\n[... truncated]"
