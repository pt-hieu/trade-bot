"""Phase 4: Synthesis + 1-pass narrative critic.

Structural correctness (R:R, mode compliance, cross-section dedup) is now
enforced deterministically by recommendation_builder.py + recommendation_validator.py.
The critic only validates narrative quality for human-readable brief.
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

NARRATIVE_CRITIC_TIMEOUT_SECONDS = 600


def _append_critic_error_stub(brief: str, *, reason: str, label: str) -> str:
    """Append a NARRATIVE REVIEW (PIPELINE ERROR) stub when the critic fails.

    Guarantees the auditor can distinguish "critic said nothing" (section
    absent) from "critic crashed" (section present with PIPELINE ERROR).
    """
    stub = (
        "\n\nNARRATIVE REVIEW (PIPELINE ERROR)\n"
        f"- Critic agent {reason} — review not performed; "
        "reader should apply extra caution."
    )
    print(
        f"  Critic PIPELINE ERROR: {label} — NARRATIVE REVIEW stub appended",
        flush=True,
    )
    return brief + stub


from agents import synthesize_with_agent
from agents.critic import critique_with_agent
from agents.synthesis import validate_synthesis_output
from shared.observability import span

from .types import GeopoliticalShockDict


async def run_synthesis_and_reflection(
    sector_results: list[str],
    position_alerts: dict,
    trading_mode: dict | None,
    scan_date,
    holdings: list[dict],
    holdings_snapshot_at: datetime | None,
    holdings_tickers: list[str],
    pre_computed_picks: list[dict] | None,
    entry_strategy: str | None,
    entries_blocked_reason: str | None,
    deployable_cash: float,
    market_regime: str,
    global_risk_regime: str,
    geopolitical_context: str = "",
    position_beliefs: list[dict] | None = None,
    advocate_reviews: dict | None = None,
    gated_tickers: list[dict] | None = None,
    portfolio_context: str = "",
    catalyst_context: str = "",
    regime_context: str = "",
    recent_trades_context: str = "",
    sector_signals: list[dict] | None = None,
    longterm_watchlist: dict[str, dict] | None = None,
    rolling_win_rate: float | None = None,
    expectancy_floor: float | None = None,
    min_rr_floor: float | None = None,
    geo_shock: GeopoliticalShockDict | None = None,
) -> tuple[str, str]:
    """Run synthesis agent + 1-pass narrative critic.

    Returns (final_brief, reflection_status).
    """

    async def _synthesize(critic_feedback: str | None = None) -> str:
        return await synthesize_with_agent(
            sector_results=sector_results,
            position_alerts=position_alerts,
            trading_mode=trading_mode,
            scan_date=scan_date,
            holdings_tickers=holdings_tickers,
            pre_computed_picks=pre_computed_picks,
            entry_strategy=entry_strategy,
            entries_blocked_reason=entries_blocked_reason,
            position_beliefs=position_beliefs,
            advocate_reviews=advocate_reviews,
            gated_tickers=gated_tickers,
            portfolio_context=portfolio_context,
            catalyst_context=catalyst_context,
            regime_context=regime_context,
            geopolitical_context=geopolitical_context,
            recent_trades_context=recent_trades_context,
            sector_signals=sector_signals,
            longterm_watchlist=longterm_watchlist,
            rolling_win_rate=rolling_win_rate,
            expectancy_floor=expectancy_floor,
            min_rr_floor=min_rr_floor,
            holdings=holdings,
            holdings_snapshot_at=holdings_snapshot_at,
            geo_shock=geo_shock,
            critic_feedback=critic_feedback,
        )

    draft_brief = await _synthesize()
    print(f"  Draft brief: {len(draft_brief):,} characters", flush=True)

    final_brief = draft_brief
    mode = trading_mode.get("mode") if trading_mode else "NORMAL"

    # Inter-day drift detection (deterministic, logged only)
    previous_context = await _load_interday_context(draft_brief, scan_date, holdings)

    # Pre-validate for structural issues
    _, pre_warnings = validate_synthesis_output(draft_brief, mode, deployable_cash)
    if pre_warnings:
        print(f"  Pre-validation found {len(pre_warnings)} warning(s):", flush=True)
        for warning in pre_warnings:
            print(f"    - {warning}", flush=True)
        previous_context = {**(previous_context or {}), "pre_validation_warnings": pre_warnings}

    # 1-pass narrative critic (qualitative checks only — no refiner)
    reflection_status = "reviewed"
    with span("narrative_critic"):
        try:
            critique = await asyncio.wait_for(
                critique_with_agent(
                    draft_brief=final_brief,
                    trading_mode=mode,
                    deployable_cash=deployable_cash,
                    market_regime=market_regime,
                    global_macro_regime=global_risk_regime,
                    portfolio_tickers=holdings_tickers,
                    portfolio_holdings=holdings,
                    previous_context=previous_context or None,
                    directive_context=entry_strategy or None,
                    geopolitical_context=geopolitical_context,
                ),
                timeout=NARRATIVE_CRITIC_TIMEOUT_SECONDS,
            )
            if critique.has_issues:
                print(
                    f"  Critic ({critique.severity}, {len(critique.issues)} issues): "
                    f"{critique.summary}",
                    flush=True,
                )
                issue_text = "\n".join(f"- {issue}" for issue in critique.issues)
                # SWI-361: on a MAJOR finding, reconcile IN THE LLM — feed the
                # finding back into synthesis once so the brief itself re-issues
                # the affected action (e.g. BUY → EVALUATE) BEFORE save_morning_brief.
                # This closes the reader-facing gap (the brief, not just the rec
                # table, reflects the downgrade) and complies with the Python/LLM
                # split — no deterministic post-LLM action override. A single
                # regeneration pass is bounded; the publish-with-stub policy below
                # still governs minor findings.
                if critique.severity == "major" and critique.issues:
                    try:
                        final_brief = await _synthesize(critic_feedback=issue_text)
                        final_brief += (
                            "\n\nNARRATIVE REVIEW (major — reconciled)\n"
                            "The draft was regenerated to address:\n"
                            f"{issue_text}"
                        )
                        # CRITIC_MAJOR_DOWNGRADE marker: the regenerated brief may
                        # re-issue a BUY as EVALUATE, but the rec table + alerts are
                        # built from pre-critic `advocate.filtered_picks` (D1: no
                        # deterministic rec-table override). Log loudly so the
                        # brief↔rec divergence is auditable, not silent.
                        logger.error(
                            "CRITIC_MAJOR_DOWNGRADE: brief regenerated for major critic "
                            "finding; rec table + alerts reflect PRE-critic picks and may "
                            "diverge from the reconciled brief. scan_date=%s issues=%s",
                            scan_date,
                            critique.issues,
                        )
                        print("  Critic MAJOR — regenerated brief with feedback", flush=True)
                    except Exception as regen_exc:
                        logger.error(
                            "Critic-feedback regeneration failed: %s — keeping draft + banner",
                            regen_exc,
                            exc_info=True,
                        )
                        final_brief += f"\n\nNARRATIVE REVIEW ({critique.severity})\n{issue_text}"
                elif critique.issues:
                    # DELIBERATE: publish-with-stub policy (commits 4eb608da
                    # 2026-04-16, 43dbdbef 2026-04-19). Non-major critic issues
                    # append to the brief; the brief still publishes — banners
                    # make crashes visually distinguishable from clean runs. Do
                    # NOT add a publish gate here; user reviewed 2026-05-14 and
                    # re-affirmed.
                    final_brief += f"\n\nNARRATIVE REVIEW ({critique.severity})\n{issue_text}"
            else:
                print(f"  Critic approved: {critique.summary}", flush=True)
        except TimeoutError:
            logger.error(
                "Narrative critic timed out after %ds",
                NARRATIVE_CRITIC_TIMEOUT_SECONDS,
            )
            reflection_status = "skipped_timeout"
            final_brief = _append_critic_error_stub(
                final_brief,
                reason=f"timed out after {NARRATIVE_CRITIC_TIMEOUT_SECONDS}s",
                label="timeout",
            )
        except Exception as e:
            logger.error("Narrative critic failed: %s", e, exc_info=True)
            reflection_status = "skipped_error"
            final_brief = _append_critic_error_stub(
                final_brief,
                reason=f"raised {type(e).__name__}: {e}",
                label=type(e).__name__,
            )

    # Prepend directive sections (excluded from synthesis/critic scope)
    if entry_strategy and entry_strategy.strip():
        final_brief = _strip_directive_echo(final_brief, entry_strategy)
        final_brief = entry_strategy.strip() + "\n\n<!-- STRATEGY_BREAK -->\n\n" + final_brief
        print(f"  Prepended directive sections ({len(entry_strategy):,} chars)", flush=True)

    print(f"  Final brief: {len(final_brief):,} characters", flush=True)

    # Validate mode compliance (defense-in-depth for narrative)
    _, mode_warnings = validate_synthesis_output(final_brief, mode, deployable_cash)
    if mode_warnings:
        print("  MODE COMPLIANCE WARNINGS:", flush=True)
        for warning in mode_warnings:
            print(f"    - {warning}", flush=True)
        # DELIBERATE: publish-with-stub policy (commits 4eb608da 2026-04-16,
        # 43dbdbef 2026-04-19). Mode-compliance warnings append to the brief;
        # the brief still publishes — banners + warnings make crashes visually
        # distinguishable from clean runs. Do NOT add a publish gate here;
        # user reviewed 2026-05-14 and re-affirmed.
        if "MODE COMPLIANCE WARNINGS" not in final_brief:
            final_brief += "\n\nMODE COMPLIANCE WARNINGS (Pipeline Validation)\n"
            final_brief += "\n".join(f"- {w}" for w in mode_warnings)

    return final_brief, reflection_status


async def _load_interday_context(draft_brief: str, scan_date, holdings: list[dict]) -> dict:
    """Load previous day context for inter-day drift detection."""
    try:
        from agents.tools.interday import detect_interday_drifts, load_previous_day_context

        prev_ctx = await load_previous_day_context(scan_date)
        if prev_ctx.get("previous_brief"):
            drifts = detect_interday_drifts(
                today_draft=draft_brief,
                previous_brief=prev_ctx["previous_brief"],
                current_holdings=holdings,
            )
            prev_ctx["detected_drifts"] = drifts
            if drifts:
                print(f"  [interday] {len(drifts)} drift(s) detected:", flush=True)
                for drift in drifts:
                    print(f"    {drift}", flush=True)
            return prev_ctx
    except Exception as e:
        logger.warning("[interday] Skipped (non-fatal): %s", e)
    return {}


def _strip_directive_echo(brief: str, entry_strategy: str) -> str:
    """Remove directive sections echoed by synthesis agent."""
    directive_headers = [
        line.strip()
        for line in entry_strategy.split("\n")
        if line.strip().isupper() and len(line.strip()) > 3 and not line.strip().startswith("#")
    ]
    if not directive_headers:
        return brief

    lines = brief.split("\n")
    cleaned = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(header) for header in directive_headers):
            skip = True
            continue
        if (
            skip
            and stripped
            and stripped.isupper()
            and len(stripped) > 3
            and not any(stripped.startswith(header) for header in directive_headers)
        ):
            skip = False
        if not skip:
            cleaned.append(line)
    result = "\n".join(cleaned)
    # Safety: if stripping removed >50% of content, return original
    if len(brief) > 200 and len(result) < len(brief) * 0.5:
        logger.warning(
            "Directive stripping removed >50%% of brief (%d→%d chars) — returning original",
            len(brief),
            len(result),
        )
        return brief
    return result
