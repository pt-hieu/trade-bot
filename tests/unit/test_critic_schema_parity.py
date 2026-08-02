"""Canary: critic + retro_eval_critic model + fallback parity.

Locks the critic-family model so a casual fleet-wide swap cannot land them
on a primary that has not been verified against the nested CritiqueResult /
EvalCritiqueResult schemas, and locks ``disable_fallback=True`` so the run
never rolls over to minimax-m2.7 (known incompatible with the nested
schema). The pinned model tracks the fleet majority — it moved to
moonshotai/kimi-k2.5 on 2026-05-15 when xiaomi/mimo-v2.5-pro was reverted
after a provider-class silent-hang incident; kimi-k2.5 was the original
critic-era model and parses these schemas.

The optional live test (marked ``@pytest.mark.live``) does a real OpenRouter
call to confirm the pinned model parses the nested schema end-to-end. It is
gated on a fixture file living at ``tests/fixtures/critic/last_brief.txt``;
when the fixture is absent the live test is skipped — the structural
``test_*_model_pinned_*`` assertions are the always-on guard.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from agents.critic import CritiqueResult, create_critic_agent
from agents.retro.eval_critic import EvalCritiqueResult
from shared.agent_config import clear_config_cache, load_agent_config

PINNED_MODEL = "moonshotai/kimi-k2.5"

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
CRITIC_BRIEF_FIXTURE = FIXTURE_DIR / "critic" / "last_brief.txt"
RETRO_FIXTURE = FIXTURE_DIR / "retro_eval" / "last_retro.txt"


def test_critic_model_pinned_to_kimi() -> None:
    """critic.yaml must remain on the schema-verified pinned model."""
    clear_config_cache()
    config = asyncio.run(load_agent_config("critic"))
    assert config.model_id == PINNED_MODEL, (
        f"critic.yaml model_id={config.model_id!r}; expected {PINNED_MODEL!r}. "
        "Do not unpin without re-running test_critic_schema_parses_live "
        "against the new model and recording the evidence."
    )
    assert config.disable_fallback is True, (
        "critic retains disable_fallback=true — the fallback model "
        "(minimax-m2.7) is known incompatible with nested CritiqueResult."
    )


def test_retro_eval_critic_model_pinned_to_kimi() -> None:
    """retro_eval_critic.yaml must remain on the schema-verified pinned model."""
    clear_config_cache()
    config = asyncio.run(load_agent_config("retro_eval_critic"))
    assert config.model_id == PINNED_MODEL, (
        f"retro_eval_critic.yaml model_id={config.model_id!r}; expected {PINNED_MODEL!r}."
    )
    assert config.disable_fallback is True, (
        "retro_eval_critic carries explicit disable_fallback=true; "
        "matches critic.yaml semantics for nested critique schema."
    )


def test_critique_result_schema_shape_unchanged() -> None:
    """Lock the nested-schema shape the model pin was verified against.

    If the schema gains new nesting (or loses the nested CritiqueIssue list),
    re-run the live canary against the pinned model before merging.
    """
    fields = CritiqueResult.model_fields
    assert "issues" in fields, "CritiqueResult.issues missing — re-verify model pin"
    assert "severity" in fields
    eval_fields = EvalCritiqueResult.model_fields
    assert "issues" in eval_fields
    assert "severity" in eval_fields


@pytest.mark.live
def test_critic_schema_parses_live() -> None:
    """Live OpenRouter call — verifies the pinned model parses CritiqueResult.

    Skipped when the fixture brief is absent or OPENROUTER_API_KEY is unset.
    Run locally pre-push: ``uv run pytest tests/unit/test_critic_schema_parity.py -m live``.
    """
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set — skipping live canary")
    if not CRITIC_BRIEF_FIXTURE.exists():
        pytest.skip(f"Fixture missing: {CRITIC_BRIEF_FIXTURE} — capture from a recent good run")

    brief_text = CRITIC_BRIEF_FIXTURE.read_text()

    async def _run() -> CritiqueResult:
        agent, _config = await create_critic_agent()
        result = await agent.run(brief_text)
        return result.output

    output = asyncio.run(_run())
    assert isinstance(output, CritiqueResult)
    assert output.severity is not None
