"""
Sub-agent writer for synthesis: MY HOLDINGS section.

Holdings writer runs first; picks writer (synthesis_picks_writer) runs after
and receives EXIT tickers extracted from this output.

This writer returns ``HoldingsTheses`` — a structured list of
(ticker, thesis paragraph) rows. The caller bridges those rows into a
ticker-keyed dict and feeds them to ``pipeline.rendering.render_my_holdings``
alongside an extended ``HoldingAction`` list so stop prices, P/L, and geo
badges stay deterministic Python output instead of LLM prose.
"""

import logging
from datetime import date

from pydantic import BaseModel, Field
from pydantic_ai.exceptions import UnexpectedModelBehavior

from pipeline.rendering.models import HoldingAction
from shared.agent_config import build_usage_limits, load_agent_config
from shared.observability import span as logfire_span
from shared.observability_post_llm import emit_rule_outcome
from shared.rules.synthesis_verb_match import verb_mismatches

logger = logging.getLogger(__name__)

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_DISABLE_FALLBACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout


class EmptyStructuredOutputError(Exception):
    """Raised when an agent returns a structurally-valid but empty payload.

    Pydantic accepts ``HoldingsTheses(theses=[])`` because the field
    carries ``default_factory=list``, so a model that drafts paragraphs in
    its thinking block but fails to emit them in the final structured
    output slips past schema validation. Raising on empty theses
    forces the caller to retry or fall back loudly instead of silently
    publishing a degraded brief.
    """


class ThesisParagraph(BaseModel):
    """One holding's qualitative thesis paragraph.

    The list-of-objects shape is the canonical structured-output pattern
    (sibling: ``SectorAnalystView`` in ``sector_analysts.py``). Open-key
    ``dict[str, str]`` schemas are unreliable across providers — see
    ``.claude/skills/agent-development/instructions.md`` Gotchas.
    """

    ticker: str = Field(min_length=1)
    paragraph: str = Field(min_length=1)


class HoldingsTheses(BaseModel):
    """Qualitative thesis paragraphs, one row per holding ticker.

    The renderer concatenates these with deterministic fields
    (stop prices, P/L, geo badges) produced from portfolio state.

    ``theses`` keeps ``default_factory=list`` so the model parses on
    instantiation, but ``_run_holdings_writer`` attaches an
    ``Agent.output_validator`` closure that enforces a paragraph per
    held ticker via ``ModelRetry`` when the held set is non-empty.
    The Python caller skips the agent run entirely when held_tickers
    is empty (no write attempted), so an empty list cannot reach
    persistence in steady state.
    """

    # HOOK-ALLOW: empty-output-permitted — runtime non-emptiness enforced
    # via the closure-bound `agent.output_validator` in
    # `_run_holdings_writer` when held_tickers is non-empty. Empty list at
    # parse time stays valid so the model parses cleanly when the caller
    # legitimately runs the agent with zero held tickers (caller path
    # already guards with `if held_set` short-circuit).
    theses: list[ThesisParagraph] = Field(default_factory=list)


async def _run_holdings_writer(
    held_actions: list[HoldingAction],
    position_alerts: dict | None,
    correlation: dict | None,
    trading_mode: dict | None,
    flow_context: str,
    scan_date: date,
    position_beliefs: list[dict] | None = None,
    portfolio_context: str = "",
    catalyst_context: str = "",
    regime_context: str = "",
    geopolitical_context: str = "",
    recent_trades_context: str = "",
) -> HoldingsTheses:
    """Run synthesis_holdings agent to produce per-ticker thesis paragraphs.

    Returns:
        ``HoldingsTheses`` — ``theses=[ThesisParagraph(ticker, paragraph), ...]``.
        All structural fields (stop prices, P/L, shock phase) are rendered
        downstream from ``HoldingAction`` rather than LLM prose.
    """
    config = await load_agent_config("synthesis_holdings")
    held_set: list[str] = [a.ticker.upper() for a in held_actions if a.ticker.strip()]
    expected_verbs: dict[str, str] = {a.ticker.upper(): a.verb for a in held_actions}
    agent = create_agent(config, output_type=HoldingsTheses)
    deps = AgentDeps(
        scan_date=scan_date,
        agent_key="synthesis_holdings",
        tickers_in_scope=sorted(held_set),
        holdings_tickers=sorted(held_set),
    )

    if held_set:
        # Held-ticker contract: every in-scope ticker MUST receive a
        # paragraph. ModelRetry is Pydantic-AI's native retry signal;
        # output_retries on the agent (set via config.output_retries)
        # bounds total attempts. The closure pattern is the documented
        # way to bridge runtime values into the validator.
        from pydantic_ai import ModelRetry

        @agent.output_validator
        async def _validate_held_tickers(  # pyright: ignore[reportUnusedFunction]
            _ctx: object, output: HoldingsTheses
        ) -> HoldingsTheses:
            seen: set[str] = set()
            for thesis in output.theses:
                key = thesis.ticker.upper()
                if key in seen:
                    logger.warning(
                        "synthesis_holdings duplicate ticker %s — bridge will keep last-emitted paragraph",
                        key,
                    )
                seen.add(key)
            missing = [t for t in held_set if t not in seen]
            if missing:
                raise ModelRetry(
                    "Missing thesis paragraphs for held tickers: "
                    f"{missing}. Emit one ThesisParagraph per held ticker "
                    f"(in-scope set: {held_set})."
                )
            mismatches = verb_mismatches(output.theses, expected_verbs)
            if mismatches:
                details = "; ".join(
                    f"{ticker}: paragraph={actual} expected={expected}"
                    for ticker, actual, expected in mismatches
                )
                emit_rule_outcome(
                    "synthesis_verb_match",
                    "raised_retry",
                    agent="synthesis_holdings",
                    reason="paragraph_verb_diverged",
                    boundary="output_validator",
                    metadata={"mismatch_count": len(mismatches), "details": details[:500]},
                )
                raise ModelRetry(
                    "[STRUCTURAL_GATE] Verb mismatch — every paragraph MUST start with "
                    "the RESOLVED VERB for that ticker. Mismatches: "
                    f"{details}."
                )
            return output

    context_parts = []

    if regime_context:
        context_parts.append(regime_context)

    if geopolitical_context:
        context_parts.append(geopolitical_context)

    if portfolio_context:
        from pipeline.context_blocks import PORTFOLIO_HEADER

        context_parts.append(PORTFOLIO_HEADER + "\n" + portfolio_context)

    if held_actions:
        verb_lines = "\n".join(
            f"{action.ticker} [{action.verb}]: {(action.rationale or '—')[:120]}"
            for action in held_actions
        )
        context_parts.append(
            "## RESOLVED VERBS (authoritative — your paragraph MUST start with these)\n"
            + verb_lines
        )

    if position_alerts:
        alerts_str = ""
        for alert in position_alerts.get("alerts", []):
            action = alert["action"]
            line = f"- {alert['ticker']}: {action} ({alert['urgency']}) - {alert['reason']}"
            counter_thesis = alert.get("counter_thesis")
            if counter_thesis:
                line += f"\n  COUNTER: {counter_thesis}"
            consensus = alert.get("consensus")
            if consensus:
                line += f" [consensus: {consensus}]"
            dissent = alert.get("dissenting_views", [])
            if dissent:
                line += "\n  Dissent: " + "; ".join(dissent)
            alerts_str += line + "\n"
        if alerts_str:
            context_parts.append("## POSITION ALERTS\n" + alerts_str)

    if correlation and correlation.get("level") in ("HIGH", "MEDIUM"):
        corr_str = f"Level: {correlation['level']}\n"
        corr_str += f"{correlation['note']}\n"
        if correlation.get("diversification_advice"):
            corr_str += f"Diversification: {correlation['diversification_advice']}"
        context_parts.append("## PORTFOLIO CORRELATION\n" + corr_str)

    if trading_mode:
        mode_str = f"Mode: {trading_mode.get('mode', 'NORMAL')}\n"
        mode_str += f"Reason: {trading_mode.get('reason', 'N/A')}\n"
        if trading_mode.get("stagnant_positions"):
            mode_str += f"Stagnant positions: {', '.join(trading_mode['stagnant_positions'])}\n"
        if trading_mode.get("reallocation_targets"):
            mode_str += f"Reallocation targets: {', '.join(trading_mode['reallocation_targets'])}"
        context_parts.append("## TRADING MODE\n" + mode_str)

    if flow_context:
        context_parts.append("## FOREIGN FLOW CONTEXT\n" + flow_context)

    if recent_trades_context:
        context_parts.append(recent_trades_context)

    if catalyst_context:
        from pipeline.context_blocks import CATALYST_HEADER

        context_parts.append(f"{CATALYST_HEADER}\n{catalyst_context}")

    if position_beliefs:
        from shared.formatting import format_belief_lines

        belief_lines = format_belief_lines(position_beliefs)
        context_parts.append(
            "## POSITION BELIEFS (analyst committee view)\n" + "\n".join(belief_lines)
        )

    context = "\n\n".join(context_parts)

    held_block = ""
    if held_set:
        bullets = "\n".join(f"- {t}" for t in held_set)
        held_block = f"\n## YOU MUST EMIT PARAGRAPHS FOR THESE TICKERS (held set):\n{bullets}\n"

    prompt = f"""Write qualitative thesis paragraphs for MY HOLDINGS ({scan_date.strftime("%Y-%m-%d")}).
{held_block}
## PRE-COMPUTED CONTEXT
{context}

## YOUR TASK
For each holding ticker return ONE thesis paragraph (1-3 sentences) that
explains the qualitative "why" behind today's POSITION GUIDANCE verb.
The Python renderer will attach deterministic fields (entry price,
current price, P/L, catastrophic floor, breakeven stop, trailing stop,
geo badges) around your paragraph — focus exclusively on the qualitative
narrative.

## HOW TO WRITE A GOOD THESIS PARAGRAPH
- Begin every paragraph with the RESOLVED VERB for that ticker (the verb
  shown in the RESOLVED VERBS block above). The renderer enforces this —
  any paragraph starting with a different verb is rejected.
- Explain the conviction behind the verb (why HOLD stays, why TRIM now,
  why EXIT today). Keep it tight — fit each paragraph within 280 characters.
- Cite the thesis driver (earnings visibility, catalyst timing, relative
  strength, sector rotation). Name the signal that shifted conviction
  today where one exists.
- Keep the paragraph qualitative so the renderer's numeric fields
  (prices, P/L, stop levels, geo badges) can carry the structural story
  — use your characters for the narrative.

The final brief is assembled as MY HOLDINGS (Python) + TOP PICKS +
SKIP THESE + WHAT TO DO TODAY — all other sections are produced by
separate writers, so scope your output to the `theses` list only."""

    # Outer except UnexpectedModelBehavior catches structural-gate retry
    # exhaustion (verb-mismatch / held-ticker validators) and ships a
    # deterministic stub so the brief still ships.
    usage_limits = build_usage_limits(config)
    try:
        for attempt in range(2):
            # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
            try:
                # HOOK-ALLOW: unguarded-agent-run reason=wrapped by run_agent_with_total_timeout
                result = await run_agent_with_total_timeout(
                    agent,
                    prompt,
                    agent_name="synthesis_holdings",
                    deps=deps,
                    total_timeout_s=float(OUTER_DISABLE_FALLBACK_WALL_S),
                    usage_limits=usage_limits,
                )
                output = result.output
                # Empty-theses guard. Pydantic's ``default_factory=list``
                # makes ``theses=[]`` a valid output shape, so without
                # this check a thinking-block-only draft would silently ship
                # as a degraded brief. Treat empty theses as a structured
                # output failure and let the outer retry / caller fallback
                # handle it loudly.
                if not output.theses:
                    with logfire_span(
                        "synthesis_empty_paragraphs",
                        agent="synthesis_holdings",
                        attempt=attempt,
                        scan_date=str(scan_date),
                    ):
                        logger.error(
                            "synthesis_holdings emitted empty theses "
                            "(attempt %d) — treating as structured-output failure",
                            attempt,
                        )
                    if attempt == 0:
                        continue
                    raise EmptyStructuredOutputError(
                        f"synthesis_holdings produced empty theses after "
                        f"{attempt + 1} attempts for {scan_date}"
                    )
                return output
            except EmptyStructuredOutputError:
                raise
            except UnexpectedModelBehavior:
                # Bubble out — structural-gate retry exhaustion is handled
                # by the outer fallback, not by re-running the whole agent.
                raise
            except Exception as e:
                if attempt == 0:
                    logger.warning("synthesis_holdings failed (attempt 1): %s — retrying", e)
                    continue
                raise ValueError(f"synthesis_holdings agent failed for {scan_date}: {e}") from e

        raise ValueError(
            f"synthesis_holdings agent failed for {scan_date}: exhausted retries"
        )  # unreachable, satisfies type checker
    except UnexpectedModelBehavior as exc:
        if "[STRUCTURAL_GATE]" in str(exc) and held_actions:
            emit_rule_outcome(
                "synthesis_verb_match",
                "fallback_applied",
                agent="synthesis_holdings",
                reason="fallback_after_retry",
                boundary="output_validator",
                metadata={"exc_message": str(exc)[:200]},
            )
            logger.warning(
                "synthesis_holdings structural-gate retry exhausted (%s) — shipping deterministic stub",
                exc,
            )
            return HoldingsTheses(
                theses=[
                    ThesisParagraph(
                        ticker=action.ticker,
                        paragraph=f"{action.verb} — thesis intact (auto-fallback).",
                    )
                    for action in held_actions
                ]
            )
        raise
