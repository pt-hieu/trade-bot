"""Test PydanticAI Agent.run with MiniMax as primary (not Kimi).

Raw SDK test showed 6/6 MiniMax parallel calls succeed in 9-40s with no
empty content. Raw Kimi showed 10/10 succeed but 2/10 with chars=0. If
PydanticAI + MiniMax also succeeds in parallel, the hang is Kimi-specific
within PydanticAI too. If PydanticAI + MiniMax still hangs, the problem
is PydanticAI's streaming layer under concurrent load, not Kimi.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic_ai.usage import UsageLimits  # type: ignore

from agents.positions_ensemble_models import AnalystReport  # type: ignore
from agents.tools.portfolio import get_holdings_async  # type: ignore
from pipeline.context_blocks import (  # type: ignore
    format_portfolio_block,
    format_ticker_briefings,
)
from pipeline.enrichment_loader import batch_fetch_enrichment  # type: ignore
from shared.agent_config import load_agent_config  # type: ignore
from shared.api.technicals import get_technicals  # type: ignore
from shared.trading_config import init_trading_config  # type: ignore


async def create_agent_with_model(agent_key: str, model_id: str):
    import dataclasses as dc

    config = await load_agent_config(agent_key)
    config = dc.replace(config, model_id=model_id, output_retries=0)
    from agents.agent_factory import create_agent

    return create_agent(config, output_type=AnalystReport)


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
    return f"{briefings}\n\nPORTFOLIO:\n{portfolio_ctx}\n\nAnalyze positions."


async def run_trial(agent, prompt) -> tuple[float, str, int]:
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(
            agent.run(
                prompt, usage_limits=UsageLimits(request_limit=30)
            ),  # HOOK-ALLOW: config-literal reason=bug-repro
            timeout=240,
        )
        wall = time.monotonic() - start
        views = len(result.output.views or [])
        return wall, "SUCCESS" if views else f"EMPTY ({result.output.summary[:50]})", views
    except Exception as exc:
        wall = time.monotonic() - start
        return wall, f"EXC {type(exc).__name__}", 0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--model", default="minimax/minimax-m2.7")
    args = ap.parse_args()

    prompt = await build_prompt()
    print(f"[setup] prompt_bytes={len(prompt)}")
    print(f"\n=== {args.trials} parallel trials | model={args.model} | PydanticAI ===\n")

    for i in range(args.trials):
        agent_v = await create_agent_with_model("positions_value", args.model)
        agent_t = await create_agent_with_model("positions_thesis", args.model)
        res_v, res_t = await asyncio.gather(
            run_trial(agent_v, prompt),
            run_trial(agent_t, prompt),
        )
        print(
            f"Trial {i + 1}: value={res_v[0]:5.1f}s views={res_v[2]} {res_v[1][:40]} | thesis={res_t[0]:5.1f}s views={res_t[2]} {res_t[1][:40]}"
        )


if __name__ == "__main__":
    asyncio.run(main())
