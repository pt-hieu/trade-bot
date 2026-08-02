"""
Advocate Reviewer Agents — bull and bear stress-testing of pick candidates.

Sits downstream of beliefs (Phase 2.5) and picks extraction (Phase 3b).
Reviewers consume aggregated beliefs and pre-computed picks, producing
qualitative stress-test verdicts. They do NOT produce new beliefs.

Key design: reviewers can AGREE when evidence is strong. ~90% agreement
rate is healthy per research. Forced contrarianism is counterproductive.
"""

import logging
from collections.abc import Mapping
from datetime import date

from shared.agent_config import build_usage_limits, load_agent_config
from shared.observability import span

from .advocate_models import AdvocateReport
from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)

BULL_AGENT_KEY = "bull_reviewer"
BEAR_AGENT_KEY = "bear_reviewer"


async def run_bull_reviewer(
    picks: list[dict],
    beliefs: Mapping[str, object],
    phase1_context: str,
    scan_date: date,
    accuracy_prefix: str = "",
) -> AdvocateReport:
    """Run bull reviewer on pick candidates."""
    return await _run_advocate(
        BULL_AGENT_KEY, picks, beliefs, phase1_context, scan_date, accuracy_prefix
    )


async def run_bear_reviewer(
    picks: list[dict],
    beliefs: Mapping[str, object],
    phase1_context: str,
    scan_date: date,
    accuracy_prefix: str = "",
) -> AdvocateReport:
    """Run bear reviewer on pick candidates."""
    return await _run_advocate(
        BEAR_AGENT_KEY, picks, beliefs, phase1_context, scan_date, accuracy_prefix
    )


async def _run_advocate(
    agent_key: str,
    picks: list[dict],
    beliefs: Mapping[str, object],
    phase1_context: str,
    scan_date: date,
    accuracy_prefix: str = "",
) -> AdvocateReport:
    """Shared advocate runner — loads config, builds prompt, runs agent.

    Args:
        agent_key: YAML config key (bull_reviewer or bear_reviewer)
        picks: Pre-computed pick candidates with R:R from real levels
        beliefs: Deterministic beliefs dict keyed by source (e.g. "sector")
        phase1_context: Formatted market regime + macro context
        scan_date: Trading date being analyzed
        accuracy_prefix: Pre-fetched accuracy stats string (avoids duplicate DB query)

    Returns:
        AdvocateReport with per-ticker reviews.
        On failure, returns empty report (non-fatal).
    """
    from pipeline.enrichment_position_data import extract_held_tickers

    config = await load_agent_config(agent_key)
    pick_tickers = extract_held_tickers(picks)
    agent = create_agent(config, output_type=AdvocateReport)
    deps = AgentDeps(
        scan_date=scan_date,
        agent_key=agent_key,
        tickers_in_scope=pick_tickers,
    )

    prompt = _build_advocate_prompt(picks, beliefs, phase1_context, scan_date)

    if accuracy_prefix:
        prompt = accuracy_prefix + "\n\n" + prompt

    with span(agent_key, scan_date=str(scan_date)):
        # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
        try:
            result = await run_agent_with_total_timeout(
                agent,
                prompt,
                agent_name=agent_key,
                deps=deps,
                total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
                usage_limits=build_usage_limits(config),
            )
            report = result.output
            logger.info(
                "Agent '%s' reviewed %d picks: %d AGREE, %d CHALLENGE, %d MIXED",
                agent_key,
                len(report.reviews),
                sum(1 for review in report.reviews if review.verdict == "AGREE"),
                sum(1 for review in report.reviews if review.verdict == "CHALLENGE"),
                sum(1 for review in report.reviews if review.verdict == "MIXED"),
            )
            return report
        except Exception as e:
            logger.warning(
                "Agent '%s' advocate review failed for %d picks: %s",
                agent_key,
                len(picks),
                e,
            )
            return AdvocateReport(reviews=[])


def _build_advocate_prompt(
    picks: list[dict],
    beliefs: Mapping[str, object],
    phase1_context: str,
    scan_date: date,
) -> str:
    """Build the user prompt with picks, beliefs, and market context."""
    parts = [f"DATE: {scan_date}", ""]

    # Market context
    if phase1_context:
        parts.append("## MARKET CONTEXT")
        parts.append(phase1_context)
        parts.append("")

    # Pick candidates
    parts.append("## PICK CANDIDATES TO REVIEW")
    for pick in picks:
        ticker = pick.get("ticker") or "UNKNOWN"
        entry = pick.get("entry") or "N/A"
        stop = pick.get("stop") or "N/A"
        target = pick.get("target") or "N/A"
        risk_reward = pick.get("risk_reward") or "N/A"
        signal = pick.get("signal") or "BUY"
        note = pick.get("note") or ""

        parts.append(f"### {ticker}")
        parts.append(f"- Signal: {signal}")
        parts.append(f"- Entry: {entry} VND | Stop: {stop} VND | Target: {target} VND")
        rr_display = (
            f"{risk_reward:.1f}" if isinstance(risk_reward, (int, float)) else str(risk_reward)
        )
        parts.append(f"- R:R: {rr_display}")
        if note:
            parts.append(f"- Note: {note}")
        parts.append("")

    # Aggregated beliefs for pick tickers
    raw_sector = beliefs.get("sector") or []
    sector_beliefs: list[dict] = raw_sector if isinstance(raw_sector, list) else []
    pick_tickers = {pick.get("ticker") for pick in picks}
    relevant_beliefs = [belief for belief in sector_beliefs if belief.get("ticker") in pick_tickers]

    if relevant_beliefs:
        parts.append("## AGGREGATED BELIEFS FOR THESE TICKERS")
        for belief in relevant_beliefs:
            ticker = belief.get("ticker") or "UNKNOWN"
            direction = belief.get("direction") or "NEUTRAL"
            conviction = belief.get("conviction") or 0
            bull_probability = belief.get("bull_probability") or 0
            bear_probability = belief.get("bear_probability") or 0
            narrative = belief.get("belief_narrative") or ""

            parts.append(f"### {ticker}")
            parts.append(f"- Direction: {direction} | Conviction: {conviction:.2f}")
            parts.append(f"- Bull prob: {bull_probability:.2f} | Bear prob: {bear_probability:.2f}")
            if narrative:
                parts.append(f"- Narrative: {narrative}")
            parts.append("")

    parts.append("## YOUR TASK")
    parts.append(
        "Review each pick candidate above. "
        "Output an AdvocateReport with one AdvocateReview per ticker."
    )

    return "\n".join(parts)
