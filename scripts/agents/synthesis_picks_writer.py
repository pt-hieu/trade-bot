"""
Sub-agent writer for synthesis: picks section (TOP PICKS, SKIP THESE, WHAT TO DO TODAY).

Runs after holdings writer — receives EXIT tickers extracted from holdings output
to enforce REALLOCATION mode rules.
"""

import logging
from datetime import date

from pipeline.context_compression import compress_sector_for_synthesis
from shared.agent_config import build_usage_limits, load_agent_config
from shared.observability import emit_ticker_drop_span
from shared.text_utils import TICKER_TOKEN_RE

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_DISABLE_FALLBACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)


async def _run_picks_writer(
    entry_strategy: str | None,
    sector_results: list[str],
    pre_computed_picks: list[dict] | None,
    entries_blocked_reason: str | None,
    trading_mode: dict | None,
    exit_tickers: list[str],
    scan_date: date,
    advocate_reviews: dict | None = None,
    skip_tickers: set[str] | None = None,
    catalyst_context: str = "",
    regime_context: str = "",
    holdings_tickers: list[str] | None = None,
    longterm_watchlist: dict[str, dict] | None = None,
    rolling_win_rate: float | None = None,
    expectancy_floor: float | None = None,
    min_rr_floor: float | None = None,
    critic_feedback: str | None = None,
) -> str:
    """Run synthesis_picks agent to produce the TOP PICKS section only.

    SKIP THESE is rendered deterministically downstream (MON-2026-04-23-001)
    from `select_skip_tickers`; the resolved set is injected here as a
    negative filter so the LLM never emits a ticker that is about to be
    SKIP-rendered. WHAT TO DO TODAY is likewise rendered deterministically.

    Args:
        skip_tickers: Tickers that will appear in the deterministic
            SKIP THESE section. Passed in so the LLM can be told "do NOT
            include these in TOP PICKS".
    Returns:
        Text containing the TOP PICKS section only.
    """
    from pipeline.enrichment_position_data import extract_held_tickers

    config = await load_agent_config("synthesis_picks")
    pick_tickers = extract_held_tickers(pre_computed_picks)
    agent = create_agent(config)
    deps = AgentDeps(
        scan_date=scan_date,
        agent_key="synthesis_picks",
        tickers_in_scope=pick_tickers,
    )

    # Interpolate today's R:R floor into the prompt — never hardcode the
    # literal. Fallback 3.0 preserves prior behavior when the caller omits
    # a directive floor (MON-2026-04-16-006).
    floor_str = f"{min_rr_floor:.1f}" if min_rr_floor else "2.5"

    context_parts = []

    if regime_context:
        context_parts.append(regime_context)

    if entry_strategy:
        context_parts.append(
            "## ENTRY STRATEGY (CONTEXT ONLY — do NOT embed in output; used for stance/regime rules)\n"
            + entry_strategy
        )

    mode_value = (trading_mode or {}).get("mode") or "NORMAL"
    if trading_mode:
        mode_str = f"Mode: {mode_value}\n"
        mode_str += f"Reason: {trading_mode.get('reason', 'N/A')}\n"
        if trading_mode.get("stagnant_positions"):
            mode_str += f"Stagnant positions: {', '.join(trading_mode['stagnant_positions'])}\n"
        if trading_mode.get("reallocation_targets"):
            mode_str += f"Reallocation targets: {', '.join(trading_mode['reallocation_targets'])}"
        context_parts.append("## TRADING MODE\n" + mode_str)

    # EXIT-TICKERS context applies ONLY to REALLOCATION mode — emitting it
    # under NORMAL caused the LLM to mis-apply the REALLOCATION BUY-with-EXIT
    # rule and refuse all BUYs.
    if mode_value == "REALLOCATION":
        if exit_tickers:
            context_parts.append(
                "## EXIT TICKERS FROM HOLDINGS\n"
                + ", ".join(exit_tickers)
                + "\n(REALLOCATION mode: BUY is only valid when corresponding EXIT is listed above)"
            )
        else:
            context_parts.append(
                "## EXIT TICKERS FROM HOLDINGS\nNone\n"
                "(REALLOCATION mode: no EXIT found — do NOT recommend BUY)"
            )

    if entries_blocked_reason:
        context_parts.append(f"## ENTRY GATE\n{entries_blocked_reason}")

    if sector_results:
        relevant_results = [
            result for result in sector_results if ": BUY" in result or ": ADD" in result
        ]
        if relevant_results:
            compressed_results = [
                compress_sector_for_synthesis(result) for result in relevant_results
            ]
            context_parts.append(
                "## SECTOR ANALYSES (compressed)\n" + "\n\n".join(compressed_results)
            )
        else:
            context_parts.append("## SECTOR ANALYSES\nNo sectors produced BUY/ADD signals.")

    has_valid_picks = bool(pre_computed_picks)

    if pre_computed_picks:
        from .synthesis_formatters import _format_expectancy_header, _format_pre_computed_picks

        expectancy_header = _format_expectancy_header(rolling_win_rate, expectancy_floor)
        if expectancy_header:
            context_parts.append(expectancy_header)
        picks_ctx = _format_pre_computed_picks(pre_computed_picks, min_rr_floor=min_rr_floor)
        if picks_ctx:
            context_parts.append(picks_ctx)

    if advocate_reviews:
        from .advocate_models import format_advocate_reviews

        formatted_reviews = format_advocate_reviews(advocate_reviews)
        if formatted_reviews:
            context_parts.append("## ADVOCATE STRESS-TEST\n" + formatted_reviews)

    if skip_tickers:
        context_parts.append(
            "## DETERMINISTIC SKIP THESE (already rendered downstream — do NOT emit in TOP PICKS)\n"
            + ", ".join(sorted(skip_tickers))
        )

    if catalyst_context:
        from pipeline.context_blocks import CATALYST_HEADER

        context_parts.append(f"{CATALYST_HEADER}\n{catalyst_context}")

    if holdings_tickers:
        context_parts.append(
            "## CURRENT HOLDINGS\n"
            + ", ".join(sorted(holdings_tickers))
            + "\nDo NOT include these in TOP PICKS — they are already covered in MY HOLDINGS."
        )

    if longterm_watchlist:
        from shared.formatting import format_price_k

        entry_zone_lines = []
        for ticker, info in sorted(longterm_watchlist.items()):
            entry_zone = info.get("entry_zone") or 0
            conviction = info.get("conviction") or "Medium"
            if entry_zone > 0:
                entry_zone_lines.append(
                    f"{ticker}: entry zone {format_price_k(entry_zone)} ({conviction})"
                )
        if entry_zone_lines:
            context_parts.append(
                "## LONGTERM ENTRY ZONES (for WHAT TO DO TODAY alert placement)\n"
                + "\n".join(entry_zone_lines)
            )

    context = "\n\n".join(context_parts)

    # Emit only the rule that applies under today's mode — stacking them
    # all unconditionally cross-contaminates the LLM's reasoning.
    mode_specific_rule_lines: list[str] = []
    if mode_value == "LOW_CASH":
        mode_specific_rule_lines.append(
            "- LOW_CASH mode with 0 deployable: TOP PICKS must be empty (no BUYs)"
        )
    elif mode_value == "REALLOCATION":
        mode_specific_rule_lines.append(
            "- REALLOCATION mode: BUY only allowed if matching EXIT ticker exists "
            "in EXIT TICKERS FROM HOLDINGS"
        )
    mode_specific_rules = (
        "\n".join(mode_specific_rule_lines) + "\n" if mode_specific_rule_lines else ""
    )

    if has_valid_picks:
        tasks_section = (
            "1. Call portfolio.get_position_scale to get the sizing multiplier for pick candidates\n"
            "2. Use PRE-COMPUTED PICKS R:R data above for entry/stop/target/R:R values\n"
            "3. Call statistic.get_stats for historical accuracy data on high-conviction setups\n"
            "4. Use CATALYST PREVIEW above for upcoming event exposure on pick candidates\n"
            "5. Write the TOP PICKS section ONLY (SKIP THESE and WHAT TO DO TODAY are rendered downstream)"
        )
    else:
        tasks_section = (
            "No valid BUY setups found today. Do NOT call portfolio.get_position_scale "
            "or statistic.get_stats — there are no picks to size.\n"
            f"1. Write TOP PICKS as empty (state: no setups meeting R:R >= {floor_str} criteria today)"
        )

    # SWI-361: on a major-severity critic finding the orchestrator regenerates
    # this section with the finding injected here, so the brief itself resolves
    # the issue (e.g. re-issues a contradicted BUY as EVALUATE) BEFORE publish.
    # Placed adjacent to the tasks so the most specific instruction wins.
    review_section = ""
    if critic_feedback:
        review_section = (
            "\n## PRIOR REVIEW — MAJOR ISSUE(S) TO RESOLVE\n"
            "A narrative review of your previous draft flagged the issue(s) below. "
            "Revise the affected TOP PICKS so the section resolves them: for a BUY "
            "the review found unjustified or contradicted, re-issue it as EVALUATE "
            "with the reason; keep every well-supported BUY.\n"
            f"{critic_feedback}\n"
        )

    prompt = f"""Write the TOP PICKS section of the morning brief for {scan_date.strftime("%Y-%m-%d")}.

Do NOT write SKIP THESE or WHAT TO DO TODAY — they are rendered deterministically from structured data after your output.

## PRE-COMPUTED CONTEXT
{context}
{review_section}
## YOUR TASKS
{tasks_section}

## OUTPUT FORMAT
Produce ONLY the TOP PICKS section in PLAIN ASCII (no markdown, no emojis):

TOP PICKS
[BUY candidates with Entry/Stop/Target/R:R/Shares — only if valid setup and R:R >= {floor_str}]

RULES:
- PLAIN ASCII only (no markdown headers with #, no ** bold, no emojis)
- Section header (TOP PICKS) must appear ALONE on its own line — no parenthetical notes, no colons, no inline content after the header name
- R:R >= {floor_str} for ALL BUY recommendations — no exceptions
- Respect STANCE from entry strategy for regime rules
{mode_specific_rules}- Do NOT include MY HOLDINGS, LONG-TERM PORTFOLIO, SKIP THESE, or WHAT TO DO TODAY in your output"""

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="synthesis_picks",
            deps=deps,
            total_timeout_s=float(OUTER_DISABLE_FALLBACK_WALL_S),
            usage_limits=build_usage_limits(config),
        )
        output_text = result.output
        if pre_computed_picks:
            expected = {
                (pick.get("ticker") or "").upper()
                for pick in pre_computed_picks
                if pick.get("ticker")
            }
            # Regex over LLM prose: only the intersection with `expected`
            # matters, so 3-letter English-word false positives can't
            # suppress real drops (they just fail to mask one).
            mentioned = set(TICKER_TOKEN_RE.findall(output_text or ""))
            emit_ticker_drop_span(
                agent="synthesis_picks",
                expected=expected,
                produced=expected & mentioned,
                logger=logger,
            )
        return output_text
    except Exception as e:
        raise ValueError(f"synthesis_picks agent failed for {scan_date}: {e}") from e
