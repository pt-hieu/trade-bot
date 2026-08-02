"""Test whether output_retries=0 eliminates the empty-content retry hang.

OBSOLETE — premise referenced a 180s per-attempt wall. PRIMARY_HOP_WALL_S
was cut to 75s in SWI-318 (2026-05-11), so the original 3 × 60s ≈ 180s
arithmetic no longer fits inside one hop. Kept as historic reference for
the empty-content retry class.

Theory (historic): Kimi-K2.5 sometimes returns empty content (~10-20% rate).
PydanticAI cannot parse empty content into AnalystReport, triggers
output_retries. Each retry is a fresh ~60s model call.

If output_retries=0 eliminates hangs (only single-attempt empty-content
failures observable), the fix class is "cap retry compounding" not
"provider flake."
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic_ai import Agent  # type: ignore
from pydantic_ai.usage import UsageLimits  # type: ignore

from agents.positions_ensemble_models import AnalystReport  # type: ignore
from agents.tools.native_tools import AgentDeps  # type: ignore
from agents.tools.portfolio import get_holdings_async  # type: ignore
from pipeline.context_blocks import (  # type: ignore
    format_portfolio_block,
    format_ticker_briefings,
)
from pipeline.enrichment_loader import batch_fetch_enrichment  # type: ignore
from shared.agent_config import load_agent_config  # type: ignore
from shared.api.technicals import get_technicals  # type: ignore
from shared.trading_config import init_trading_config  # type: ignore


async def create_agent_with_retries(agent_key: str, output_retries: int):
    """Rebuild agent with explicit output_retries override."""
    import dataclasses

    config = await load_agent_config(agent_key)
    config = dataclasses.replace(config, output_retries=output_retries)
    from agents.agent_factory import create_agent

    return create_agent(config, output_type=AnalystReport)


async def run_trial(agent: Agent[AgentDeps, AnalystReport], prompt: str) -> tuple[float, str, int]:
    start = time.monotonic()
    deps = AgentDeps(scan_date=date.today())
    try:
        result = await asyncio.wait_for(
            agent.run(
                prompt, deps=deps, usage_limits=UsageLimits(request_limit=30)
            ),  # HOOK-ALLOW: config-literal reason=bug-repro
            timeout=240,
        )
        wall = time.monotonic() - start
        output = result.output
        if not isinstance(output, AnalystReport):
            return wall, f"EXC NonAnalystReport: {type(output).__name__}", 0
        views_count = len(output.views or [])
        return wall, "SUCCESS" if views_count else f"EMPTY ({output.summary[:60]})", views_count
    except Exception as exc:
        wall = time.monotonic() - start
        return wall, f"EXC {type(exc).__name__}: {str(exc)[:120]}", 0


async def build_prompt() -> str:
    await init_trading_config()
    holdings_data = await get_holdings_async()
    holdings_dict = holdings_data.get("holdings", {})
    held_tickers = [t for t in holdings_dict if t != "CASH"]
    technicals = await get_technicals(held_tickers)
    enrichment_data = await batch_fetch_enrichment(held_tickers, date.today())

    briefings = format_ticker_briefings(
        tickers=held_tickers,
        technicals=technicals,
        enrichment_data=enrichment_data,
        commodity_prices={},
        macro_metrics={"geopolitical_shock": None},
        geopolitical_shock=None,
        agent_key="positions_value",
    )
    portfolio_ctx = format_portfolio_block(holdings_dict, 20_000_000, 20_000_000)
    prompt = (
        f"{briefings}\n\nPORTFOLIO:\n{portfolio_ctx}\n\n"
        "Analyze all portfolio positions from your value perspective."
    )
    return prompt


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retries", type=int, default=0, help="output_retries value")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--parallel", action="store_true")
    args = ap.parse_args()

    prompt = await build_prompt()
    print(f"[setup] prompt_bytes={len(prompt)}")

    print(
        f"\n=== {args.trials} trial(s) output_retries={args.retries} mode={'parallel' if args.parallel else 'serial'} ===\n"
    )

    for i in range(args.trials):
        print(f"--- Trial {i + 1}/{args.trials} ---")
        if args.parallel:
            agent_v = await create_agent_with_retries("positions_value", args.retries)
            agent_t = await create_agent_with_retries("positions_thesis", args.retries)
            res_v, res_t = await asyncio.gather(
                run_trial(agent_v, prompt),
                run_trial(agent_t, prompt),
            )
            print(f"  [value ] wall={res_v[0]:6.1f}s views={res_v[2]} outcome={res_v[1]}")
            print(f"  [thesis] wall={res_t[0]:6.1f}s views={res_t[2]} outcome={res_t[1]}")
        else:
            agent = await create_agent_with_retries("positions_value", args.retries)
            wall, outcome, views = await run_trial(agent, prompt)
            print(f"  [value ] wall={wall:6.1f}s views={views} outcome={outcome}")


if __name__ == "__main__":
    asyncio.run(main())
