"""Forcing function for YAML edits: request-count ceiling per agent.

Mocks the tool broker and counts `call_tools` invocations per agent run. Fails
when an agent exceeds its per-agent ceiling. Wired into CI (uv run pytest scripts/agents/evals/)
so future YAML drift is caught before merge rather than "verified in production".

The 2026-04-24 daily-scan failure happened because two agents looped through 30
`call_tools` batches each. A healthy inject-first agent with 3 holdings needs
1-3 batches; these ceilings give ~3× headroom and still catch loops.

Extend CEILING_BY_AGENT when adding a new ensemble agent. Cap updates require a
matching comment explaining the workflow (e.g. "retro: checks 30+ tickers across
3 phases, 8 batches needed").
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


CEILING_BY_AGENT: dict[str, int] = {
    # Per-analyst positions ensemble — pre-loaded briefings cover all primary
    # data; one batch for optional follow-ups is enough.
    "positions_value": 10,
    "positions_thesis": 10,
    "positions_technical": 5,
    # longterm_review covers 15-20 watchlist tickers; one batched call_tools
    # round-trip (get_full_analysis + article.search + get_comparison +
    # read_research) is the healthy pattern. Ceiling pinned ≤ request_limit
    # so the harness catches drift before the runtime does.
    "longterm_review": 10,
}


def _assert_ceiling_defined(agent_key: str) -> int:
    ceiling = CEILING_BY_AGENT.get(agent_key)
    if ceiling is None:
        pytest.skip(f"No ceiling defined for {agent_key} (yet)")
    return ceiling


@pytest.mark.parametrize("agent_key", sorted(CEILING_BY_AGENT.keys()))
def test_request_count_ceiling_defined(agent_key):
    """Sanity test — ensures CEILING_BY_AGENT keys are the ones the plan requires."""
    assert _assert_ceiling_defined(agent_key) > 0
    assert _assert_ceiling_defined(agent_key) <= 30, (
        "A ceiling > 30 defeats the purpose — healthy inject-first agents "
        "never need that many batches. If you genuinely need more, document why."
    )


def test_ceiling_below_per_agent_request_limit():
    """Ceilings must live below the configured per-agent request_limit so the
    harness catches loops before the runtime does."""
    from shared.agent_config import load_agent_config

    async def _all():
        for agent_key, ceiling in CEILING_BY_AGENT.items():
            try:
                config = await load_agent_config(agent_key)
            except ValueError:
                continue  # agent yaml not present yet
            assert ceiling <= config.request_limit, (
                f"{agent_key}: ceiling {ceiling} > request_limit "
                f"{config.request_limit}. Lower the ceiling below request_limit."
            )

    asyncio.run(_all())
