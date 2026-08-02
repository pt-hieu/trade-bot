"""Bug 1 (run2 2026-05-14): retro_generator omitted TOP_PICKS BUY recs.

Two layers:
  * `select_recs_for_retro` — partition that keeps every BUY / TOP_PICKS rec
    regardless of input order (the old `recommendations[:10]` slice let 10
    alphabetic LONG_TERM rows starve the 4 TOP_PICKS BUYs).
  * `buy_rec_count` cited-fact — injected into the prompt so the narrated
    BUY count cannot drift from the structural fact.
"""

from __future__ import annotations

from datetime import date

import pytest

from agents.retro import generator as generator_module
from agents.retro.generator import select_recs_for_retro
from shared.agent_config import load_agent_config

# ── Layer 1: partition keeps every BUY / TOP_PICKS rec ───────────────────


def test_select_recs_includes_all_buy_and_top_picks_regardless_of_order():
    """10 alphabetic LONG_TERM WATCH rows ahead of 4 TOP_PICKS BUYs — the
    partition must still surface all 4 BUYs (run2 reproduction)."""
    longterm = [
        {"ticker": f"L{i:02d}", "action": "WATCH", "section": "LONG_TERM"} for i in range(10)
    ]
    top_picks = [
        {"ticker": t, "action": "BUY", "section": "TOP_PICKS"} for t in ("NT2", "VCB", "VHM", "VRE")
    ]
    # Alphabetic DB ordering: LONG_TERM before TOP_PICKS (the defect ordering).
    selected = select_recs_for_retro(longterm + top_picks)

    selected_tickers = {r["ticker"] for r in selected}
    assert {"NT2", "VCB", "VHM", "VRE"} <= selected_tickers


def test_select_recs_caps_total_but_never_drops_primary():
    """Primary set (BUY + TOP_PICKS) is uncapped; only the WATCH tail is
    bounded by max_total."""
    primary = [{"ticker": f"B{i:02d}", "action": "BUY", "section": "TOP_PICKS"} for i in range(6)]
    tail = [{"ticker": f"W{i:02d}", "action": "WATCH", "section": "LONG_TERM"} for i in range(20)]
    selected = select_recs_for_retro(primary + tail, max_total=12)

    # All 6 primary kept; tail filled to the 12 total.
    assert all(p in selected for p in primary)
    assert len(selected) == 12


# ── Layer 2: buy_rec_count cited-fact threaded into the prompt ───────────


class _StubResult:
    output = "RETRO BODY"


class _CapturingAgent:
    """Captures the prompt passed to .run() so we can assert on it."""

    def __init__(self) -> None:
        self.prompt: str | None = None

    async def run(self, prompt: str, **_kwargs) -> _StubResult:
        self.prompt = prompt
        return _StubResult()


async def _build_prompt_via_agent(monkeypatch, **kwargs) -> str:
    agent = _CapturingAgent()
    config = await load_agent_config("retro_generator")

    async def _create():
        return agent, config

    async def _passthrough(coro, timeout):
        return await coro

    monkeypatch.setattr(generator_module, "create_generator_agent", _create)
    monkeypatch.setattr(generator_module, "await_with_hop_unwrap", _passthrough)

    await generator_module.generate_retro_with_agent(
        recommendations=[],
        evaluations={"evaluations": [], "day_summary": {}},
        patterns={},
        **kwargs,
    )
    assert agent.prompt is not None
    return agent.prompt


@pytest.mark.asyncio
async def test_prompt_emits_buy_count_cited_fact(monkeypatch):
    prompt = await _build_prompt_via_agent(
        monkeypatch, scan_date=date(2026, 5, 14), buy_rec_count=4
    )
    assert "BUY COUNT (deterministic, cite verbatim" in prompt
    assert "produced 4 BUY recommendations" in prompt
    # Bug 4: header date is pinned from the Python-supplied scan_date.
    assert "MARKET CLOSE DATE (use verbatim in the header): 2026-05-14" in prompt


@pytest.mark.asyncio
async def test_prompt_omits_buy_count_when_none(monkeypatch):
    prompt = await _build_prompt_via_agent(monkeypatch, buy_rec_count=None)
    assert "BUY COUNT" not in prompt
