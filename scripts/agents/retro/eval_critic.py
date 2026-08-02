#!/usr/bin/env python3
"""LLM critic for retro evaluation commentary — deterministic pre-flight + LLM confirm.

Reviews LLM-generated commentary for quality issues that deterministic
validation cannot fully catch:

  1. Python pre-flight (``eval_critic_preflight.run_preflight``) emits candidates
     for 3 mechanical rules: vague_lesson, missing_citation, error_type_mismatch.
  2. LLM confirms/dismisses each candidate AND flags the 3 qualitative rules
     freely: weak_insight, temporal_leak, metric_misuse.
  3. Structured ``IssueItem`` schema controls token shape without ``max_length``
     caps (CLAUDE.md forbids schema caps as a token-budget band-aid).

Failure handling: the outer ``except`` catches only transient infra
(``asyncio.TimeoutError``, ``ConnectionError``) and returns a no-issues stub.
``pydantic.ValidationError`` and ``UnexpectedModelBehavior`` translate to
``RetroEvalCriticContractFailure`` and propagate to the retro pipeline entrypoint.
"""

import logging
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator
from pydantic_ai.exceptions import UnexpectedModelBehavior

from shared.agent_config import build_usage_limits, load_agent_config
from shared.observability import observe_agent_output
from shared.rules.critic_coercion import coerce_severity_when_issues_empty

from ..agent_factory import AgentDeps, create_agent
from .commentary import format_evals_for_llm, format_midday_context_block
from .eval_critic_preflight import format_preflight_candidates, run_preflight

logger = logging.getLogger(__name__)


class RetroEvalCriticContractFailure(RuntimeError):
    """Raised when the retro_eval_critic LLM violates its output contract.

    Propagates to the retro pipeline entrypoint so the run aborts with
    non-zero exit instead of silently absorbing the failure into a stub
    no-issues result. Distinct from the transient-infra TimeoutError /
    ConnectionError path which DOES return a stub to keep retro shipping.
    """


class IssueItem(BaseModel):
    """A single critic-flagged issue, structured so the LLM cannot expand into narrative.

    `rule_id` is intentionally an open string so future rule categories can
    be added via prompt edit alone (no schema change). The six current rules
    are: vague_lesson, missing_citation, error_type_mismatch (mechanical,
    pre-flight-seeded) + weak_insight, temporal_leak, metric_misuse (LLM-driven).
    """

    ticker: str = Field(description="Ticker the issue concerns, or '?' if none.")
    rule_id: str = Field(description="Rule category (see docstring for canonical list).")
    confirmed: bool = Field(
        description="True for pre-flight candidates the LLM confirms; True for LLM-originated findings."
    )
    note: str = Field(
        description="One sentence. Cite the specific data point that triggered this issue."
    )


class EvalCritiqueResult(BaseModel):
    """Structured critique of evaluation commentary.

    LLM emits ONLY `severity`, `issues`. `has_issues` and `summary` derive
    from the issues list to close the cross-field contradiction class
    (sibling of CritiqueResult — FPT 2026-05-07).
    """

    severity: Literal["none", "minor", "major", "critical"] = Field(description="Overall severity.")
    # HOOK-ALLOW: empty-output-permitted (a clean retro has no issues — empty list is correct)
    issues: list[IssueItem] = Field(default_factory=list, description="Structured issues.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> str:
        if not self.issues:
            return "No issues."
        first = self.issues[0]
        head = f"{first.rule_id} @ {first.ticker}: {first.note}"[:200]
        extra = f" (+{len(self.issues) - 1} more)" if len(self.issues) > 1 else ""
        return f"{head}{extra}"

    @model_validator(mode="after")
    def _coerce_severity_when_issues_empty(self) -> "EvalCritiqueResult":
        coerce_severity_when_issues_empty(self, agent="retro_eval_critic")
        return self


async def critique_eval_commentary(
    analyses: list[dict],
    pre_evals: list[dict],
    scan_date: date,
    midday_data: dict | None = None,
) -> EvalCritiqueResult:
    """Run LLM critic on evaluation commentary.

    Args:
        analyses: TickerAnalysis dicts from LLM commentary
        pre_evals: Pre-computed evaluation dicts
        scan_date: Date being evaluated
        midday_data: Midday context (position_alerts, recommendation_overrides,
            afternoon_plan). Required for the critic to verify commentary
            claims about midday events; absent context produces confidently
            wrong "fabrication" findings (SWI-141 / Fix 4).

    Returns:
        EvalCritiqueResult. On transient infra failure (TimeoutError /
        ConnectionError) returns a no-issues stub. On contract failure
        (ValidationError / UnexpectedModelBehavior) raises
        RetroEvalCriticContractFailure.
    """
    try:
        config = await load_agent_config("retro_eval_critic")
        # HOOK-ALLOW: no-tickers-scope (retro critic reads pre-computed evaluations)
        agent = create_agent(config, output_type=EvalCritiqueResult)

        pre_text = format_evals_for_llm(pre_evals)
        commentary_text = _format_analyses(analyses)
        preflight_block = format_preflight_candidates(run_preflight(analyses))
        midday_block = format_midday_context_block(midday_data)

        prompt = (
            f"Review evaluation commentary for {scan_date:%Y-%m-%d}.\n\n"
            f"## PRE-COMPUTED DATA (ground truth)\n{pre_text}\n\n"
            f"{midday_block}"
            f"## LLM COMMENTARY TO REVIEW\n{commentary_text}\n\n"
            f"## {preflight_block}\n\n"
            "Apply the system-prompt checklist to the data above. Cross-check\n"
            "every commentary claim about midday events against the MIDDAY\n"
            "DATA section above before flagging it as fabrication.\n"
            "Return EvalCritiqueResult. Keep each `note` to one sentence."
        )
        # HOOK-ALLOW: unguarded-agent-run reason=retro_eval_critic_non_blocking
        try:
            deps = AgentDeps(scan_date=scan_date, agent_key=config.agent_key)
            result = await agent.run(prompt, deps=deps, usage_limits=build_usage_limits(config))
        except UnexpectedModelBehavior as exc:
            raise RetroEvalCriticContractFailure(
                f"retro_eval_critic violated output contract: {exc}"
            ) from exc
        observe_agent_output(
            agent="retro_eval_critic",
            result=result,
            max_tokens=config.max_tokens or 96000,
            logger=logger,
        )
        return result.output

    except (TimeoutError, ConnectionError) as e:
        # Transient infra: return stub so retro keeps shipping.
        logger.warning("retro_eval_critic transient failure: %s", e)
        return EvalCritiqueResult(
            severity="none",
            issues=[],
        )


def _format_analyses(analyses: list[dict]) -> str:
    """Format commentary analyses for critic review."""
    lines = []
    for a in analyses:
        ticker = a.get("ticker") or "?"
        error_type = a.get("error_type") or "N/A"
        analysis = a.get("analysis") or ""
        lesson = a.get("lesson") or ""
        lines.append(f"- {ticker} [{error_type}]: {analysis}")
        if lesson:
            lines.append(f"  Lesson: {lesson}")
    return "\n".join(lines)
