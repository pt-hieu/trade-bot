"""Per-position thesis pillars + fundamental valuation injection blocks.

Both ``positions_thesis`` and ``positions_value`` agents previously had to
issue ``call_tools`` round-trips to ``portfolio.get_thesis`` and
``fundamental.get_full_analysis`` because the data was not present in their
prompt context. The 2026-04-28 morning scan crash showed that this on-demand
path is fragile: GLM-5 mis-rendered the ``args`` dict, the broker mis-coached
the failure (literal hint for a missing-arg error), the analyst burned its
``request_limit`` on identical retries, and the run aborted at the belief
coverage gate.

Phase-0 batches the data once for all held tickers, formats per-ticker prose,
and the position agents' prompts inject these blocks alongside the standard
ticker briefings. Per-ticker truncation caps keep every block under the
≤7K-token-per-agent budget documented in CLAUDE.md.
"""

from __future__ import annotations

from .context_blocks_calibration import _wrap_block

THESIS_PILLARS_HEADER = "## THESIS PILLARS (pre-loaded — analyze directly)"
VALUATION_ANALYSIS_HEADER = "## VALUATION ANALYSIS (pre-loaded — analyze directly)"

# Per-ticker truncation cap. ~600 prose tokens (≈2400 chars) per ticker keeps
# 5 holdings in a single block under 3K tokens — well below the 7K per-agent
# context budget. Increasing this cap is fine when holding count is small but
# would risk Lost-in-the-Middle dilution on larger portfolios.
_PER_TICKER_CHAR_CAP = 2400
_TRUNCATION_SUFFIX = "\n…[truncated for context budget]"


def _truncate_block(prose: str) -> str:
    """Cap one ticker's prose at ``_PER_TICKER_CHAR_CAP`` chars + suffix marker."""
    if len(prose) <= _PER_TICKER_CHAR_CAP:
        return prose
    keep = _PER_TICKER_CHAR_CAP - len(_TRUNCATION_SUFFIX)
    return prose[:keep] + _TRUNCATION_SUFFIX


def _format_per_ticker_block(header: str, prose_by_ticker: dict[str, str]) -> str:
    """Wrap per-ticker prose with ``header``, truncating each ticker's section.

    Sorted by ticker so the rendered prompt is order-stable across runs.
    """
    blocks = [_truncate_block(prose) for _, prose in sorted(prose_by_ticker.items()) if prose]
    return _wrap_block(header, "\n\n".join(blocks))


def format_thesis_pillars_block(thesis_prose_by_ticker: dict[str, str]) -> str:
    """Render thesis tracker pillars + kill criteria + last update for held tickers."""
    return _format_per_ticker_block(THESIS_PILLARS_HEADER, thesis_prose_by_ticker)


def format_valuation_block(valuation_prose_by_ticker: dict[str, str]) -> str:
    """Render `=== VALUATION === / EARNINGS QUALITY === / VALUATION HISTORY ===` per ticker."""
    return _format_per_ticker_block(VALUATION_ANALYSIS_HEADER, valuation_prose_by_ticker)
