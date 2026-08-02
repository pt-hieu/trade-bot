#!/usr/bin/env python3
"""
Critic Agent using PydanticAI.

Reviews morning brief drafts for quality, completeness, and rule compliance.
Part of the Reflection pattern: Generator (Synthesis) -> Critic -> Refiner

Returns structured CritiqueResult with issues and severity.
Uses flat schema (no nested models) for Together AI GLM-4.7 compatibility.
"""

import logging
from typing import Literal, TypedDict

from pydantic import BaseModel, Field, computed_field, model_validator
from pydantic_ai import Agent


class _CriticHoldingRequired(TypedDict):
    """Fields the critic verb-mismatch rule MUST have to operate."""

    ticker: str
    plan_type: str
    entry_price_vnd: float


class CriticHoldingContext(_CriticHoldingRequired, total=False):
    """Per-holding context for verb-vs-plan correctness checks.

    `entry_date` and `held_days` are pre-included so future thesis-aging
    judgments do not require a TypedDict bump.
    """

    current_price_vnd: float | None
    catastrophic_floor_vnd: float | None
    swing_max_loss_floor_vnd: float | None
    pnl_pct: float | None
    entry_date: str | None
    held_days: int | None


from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.rules.critic_coercion import coerce_severity_when_issues_empty

logger = logging.getLogger(__name__)

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_DISABLE_FALLBACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout


class CritiqueIssue(BaseModel):
    """A single critic-flagged issue, structured so issues + summary cannot contradict.

    Closed `category` set + required `description` + `fix` blocks the FPT-class
    failure where the LLM populated `summary` describing a defect but emitted
    `issues=[]`. Both `has_issues` and `summary` derive from the issues list,
    so the LLM cannot drift between them.
    """

    category: Literal[
        "verb_mismatch",
        "stale_data",
        "compliance_drift",
        "missing_section",
        "rule_violation",
        "fabrication",
        "regime_tone",
        "coherence_issue",
        "interday_drift",
        "stop_regression",
        "unfollowed_exit",
        "missing_counter_thesis",
        "weak_counter_thesis",
        "borderline_hidden",
        "borderline_vague",
        "other",
    ]
    location: str = Field(description="Section name + ticker, e.g. 'MY HOLDINGS / FPT'")
    description: str = Field(description="One sentence stating what is wrong.")
    fix: str = Field(description="One sentence stating the corrective action.")

    def __str__(self) -> str:
        return f"[{self.category}] {self.location}: {self.description}. Fix: {self.fix}"


class CritiqueResult(BaseModel):
    """Structured critique of a morning brief draft.

    LLM emits ONLY `severity`, `issues`, `sections_reviewed`. `has_issues` and
    `summary` are derived — closing the cross-field contradiction class
    (FPT 2026-05-07: summary described a defect, issues=[]).
    """

    severity: Literal["none", "minor", "major", "critical", "error"] = Field(
        description="Overall severity: none, minor, major, critical, or error (agent failure)"
    )
    # HOOK-ALLOW: empty-output-permitted (a clean brief has no issues — empty list is correct)
    issues: list[CritiqueIssue] = Field(
        default_factory=list,
        description="Structured issues. Each emits category, location, description, fix.",
    )
    # HOOK-ALLOW: empty-output-permitted (sections_reviewed may be empty when nothing scanned)
    sections_reviewed: list[str] = Field(
        default_factory=list,
        description="Sections that were reviewed",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> str:
        if not self.issues:
            return f"No issues across {len(self.sections_reviewed)} sections."
        first = self.issues[0]
        head = f"{first.category} @ {first.location}: {first.description}"[:200]
        extra = f" (+{len(self.issues) - 1} more)" if len(self.issues) > 1 else ""
        return f"{head}{extra}"

    @model_validator(mode="after")
    def _coerce_severity_when_issues_empty(self) -> "CritiqueResult":
        coerce_severity_when_issues_empty(self, agent="critic")
        return self


async def create_critic_agent() -> tuple[Agent[AgentDeps, CritiqueResult], AgentConfig]:
    """Create a critic agent for morning brief review."""
    config = await load_agent_config("critic")
    # HOOK-ALLOW: no-broker-tools (critic reviews the draft brief, no tool surface)
    agent = create_agent(config, output_type=CritiqueResult)
    return agent, config


def _build_critic_holdings_ctx(holdings: list[dict] | None) -> list[CriticHoldingContext]:
    """Project raw portfolio_holdings rows into the TypedDict the critic needs.

    Catastrophic floor (LONGTERM) and swing_max_loss floor (SWING) are
    derived from `trading_config` so the critic compares verbs against the
    same threshold values the rest of the pipeline uses.
    """
    if not holdings:
        return []
    from shared.rules.max_loss import LONGTERM_PLAN, SWING_PLAN, floor_for_slice
    from shared.trading_config import get_trading_config

    config = get_trading_config()

    out: list[CriticHoldingContext] = []
    for row in holdings:
        ticker = row.get("ticker") or ""
        if not ticker:
            continue
        plan_type = (row.get("plan_type") or SWING_PLAN).upper()
        avg_cost_vnd = float(row.get("avg_cost_vnd") or row.get("avg_cost") or 0.0)
        current_value = row.get("current_price_vnd")
        current_price_vnd = float(current_value) if current_value else None
        catastrophic_floor_vnd = float(row.get("catastrophic_floor_vnd") or 0.0) or None
        if catastrophic_floor_vnd is None and plan_type == LONGTERM_PLAN:
            catastrophic_floor_vnd = floor_for_slice(avg_cost_vnd, plan_type, config)
        swing_max_loss_floor_vnd = (
            floor_for_slice(avg_cost_vnd, plan_type, config) if plan_type == SWING_PLAN else None
        )
        out.append(
            {
                "ticker": ticker,
                "plan_type": plan_type,
                "entry_price_vnd": avg_cost_vnd,
                "current_price_vnd": current_price_vnd,
                "catastrophic_floor_vnd": catastrophic_floor_vnd,
                "swing_max_loss_floor_vnd": swing_max_loss_floor_vnd,
                "pnl_pct": row.get("pct_from_entry"),
                "entry_date": row.get("entry_date"),
                "held_days": row.get("held_days"),
            }
        )
    return out


def _format_critic_holdings_block(rows: list[CriticHoldingContext]) -> str:
    """Render the authoritative PORTFOLIO HOLDINGS block injected into the critic.

    Format mirrors the example in critic.yaml rule 2b so the LLM reads each
    holding's plan-type + floor on the same line.
    """
    if not rows:
        return ""
    lines = ["## PORTFOLIO HOLDINGS (authoritative, plan-type-scoped)"]
    for row in rows:
        ticker = row.get("ticker") or "?"
        plan_type = row.get("plan_type") or "SWING"
        entry_val = row.get("entry_price_vnd")
        entry = int(entry_val) if entry_val else 0
        current_val = row.get("current_price_vnd")
        current = f"{int(current_val):,}" if current_val else "stale"
        if plan_type == "LONGTERM":
            floor_label = "catastrophic_floor"
            floor_val = row.get("catastrophic_floor_vnd")
        else:
            floor_label = "swing_max_loss_floor"
            floor_val = row.get("swing_max_loss_floor_vnd")
        floor_repr = f"{int(floor_val):,}" if floor_val else "n/a"
        pnl = row.get("pnl_pct")
        pnl_repr = f"{pnl:+.1f}%" if pnl is not None else "n/a"
        lines.append(
            f"{ticker} [{plan_type}] | entry {entry:,} | current {current} | "
            f"{floor_label} {floor_repr} | pnl {pnl_repr}"
        )
    return "\n".join(lines)


async def critique_with_agent(
    draft_brief: str,
    trading_mode: str | None = None,
    deployable_cash: float | None = None,
    market_regime: str | None = None,
    global_macro_regime: str | None = None,
    portfolio_tickers: list[str] | None = None,
    portfolio_holdings: list[dict] | None = None,
    previous_context: dict | None = None,
    directive_context: str | None = None,
    geopolitical_context: str = "",
) -> CritiqueResult:
    """Critique a morning brief draft.

    Args:
        draft_brief: The draft brief to review
        trading_mode: Current trading mode
        deployable_cash: Available cash
        market_regime: VN market regime
        global_macro_regime: Global macro regime
        portfolio_tickers: Current holdings tickers
        previous_context: Optional inter-day context with previous_brief and drifts

    Returns:
        CritiqueResult with issues and severity.
        On failure, returns CritiqueResult(has_issues=False) to avoid blocking pipeline.
    """
    agent, config = await create_critic_agent()

    # Phase 2 §2.8 — dual-label injection via shared formatter so the
    # AUTHORITATIVE/context wording stays consistent across agents.
    from pipeline.context_blocks_macro import format_dual_regime_labels

    context_parts = [
        f"Trading Mode: {trading_mode or 'NORMAL'}",
        f"Deployable Cash: {deployable_cash:,.0f} VND"
        if deployable_cash is not None
        else "Deployable Cash: Unknown",
        format_dual_regime_labels(
            global_risk_regime=global_macro_regime,
            technical_regime=market_regime,
            style="pair",
        ),
    ]

    if portfolio_tickers:
        context_parts.append(f"Portfolio Tickers: {', '.join(portfolio_tickers)}")
    else:
        context_parts.append("Portfolio Tickers: Unknown (cannot validate MY HOLDINGS)")

    holdings_ctx = _build_critic_holdings_ctx(portfolio_holdings)
    holdings_block = _format_critic_holdings_block(holdings_ctx)
    if holdings_block:
        context_parts.append(holdings_block)

    if geopolitical_context:
        context_parts.append(f"Geopolitical Context:\n{geopolitical_context}")

    context = "\n".join(context_parts)

    # Build inter-day consistency section
    interday_section = ""
    if previous_context:
        prev_date = previous_context.get("previous_date")
        drifts = previous_context.get("detected_drifts", [])
        if drifts and prev_date:
            drift_lines = "\n".join(f"- {d}" for d in drifts)
            interday_section = f"""
INTER-DAY CONSISTENCY CHECK (vs {prev_date})
The following drifts were auto-detected between yesterday and today's draft:
{drift_lines}

Checklist item 15: For each flagged drift, verify whether the underlying data
(price, P/L, stop level) actually changed. If not, the action change is unjustified.
"""

    # Inject pre-validation warnings (auto-detected structural issues)
    pre_warnings = (previous_context or {}).get("pre_validation_warnings", [])
    if pre_warnings:
        warning_lines = "\n".join(f"- {w}" for w in pre_warnings)
        interday_section += f"""
PRE-VALIDATION WARNINGS (auto-detected, must be addressed)
{warning_lines}
"""

    directive_section = ""
    if directive_context:
        directive_section = f"""
STRATEGY DIRECTIVE (context for compliance validation — NOT part of the brief being reviewed)
{directive_context}

"""

    prompt = f"""Review this morning brief draft for issues.

CONTEXT
{context}
{interday_section}{directive_section}
DRAFT BRIEF TO REVIEW
{draft_brief}

YOUR TASK
The brief contains ONLY stock-level sections (MY HOLDINGS, TOP PICKS, SKIP THESE, WHAT TO DO TODAY).
Directive sections (THEME, STANCE, GOAL PROGRESS, etc.) are in the STRATEGY DIRECTIVE above — use them for compliance validation.
Check all items on your checklist including inter-day consistency.
If ALL pass, return has_issues=False with severity="none".
Otherwise return all issues found."""

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        # HOOK-ALLOW: unguarded-agent-run reason=wrapped by
        # run_agent_with_total_timeout. Outer narrative_critic wrapper is
        # 600s, so this inner cap still surfaces silent hangs.
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="critic",
            deps=AgentDeps(scan_date=None, agent_key="critic"),
            total_timeout_s=float(OUTER_DISABLE_FALLBACK_WALL_S),
            usage_limits=build_usage_limits(config),
        )
        return result.output  # type: ignore[return-value]
    except Exception as e:
        logger.warning("Critic agent failed: %s", e)
        return CritiqueResult(
            severity="error",
            issues=[
                CritiqueIssue(
                    category="other",
                    location="critic",
                    description=f"Critic execution failed: {e}",
                    fix="Investigate critic agent failure logs.",
                )
            ],
            sections_reviewed=[],
        )
