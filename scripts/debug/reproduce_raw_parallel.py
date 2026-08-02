"""Raw OpenAI client parallel test — bypass PydanticAI entirely.

If raw parallel OpenRouter calls hang like the PydanticAI agents do, the
issue lives in httpx / OpenAI SDK / OpenRouter. If raw calls all succeed,
the hang is specific to PydanticAI FallbackModel / streaming plumbing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.env import load_env  # type: ignore

load_env()

import httpx  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402

API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL_PRIMARY = "moonshotai/Kimi-K2.5"
MODEL_FALLBACK = "minimax/minimax-m2.7"

PROMPT_VALUE = """You are a value analyst evaluating a 3-position portfolio.
Holdings: FPT (IT, PE 15, ROE 22%), TCB (Bank, PE 8, ROE 18%), VHM (Real Estate, PE 10, ROE 14%).
For each position, output JSON: {ticker, action, confidence, reasoning}.
Keep reasoning to 2 sentences."""

PROMPT_THESIS = """You are a thesis analyst evaluating a 3-position portfolio.
Holdings: FPT (IT, thesis: AI services expansion), TCB (Bank, thesis: digital banking leadership),
VHM (Real Estate, thesis: urban land bank monetization).
For each position, output JSON: {ticker, thesis_status, confidence, reasoning}.
Keep reasoning to 2 sentences."""


async def one_call(
    client: AsyncOpenAI, model: str, prompt: str, label: str
) -> tuple[float, str, int]:
    """Streaming chat completion. Returns (wall_s, outcome, output_chars)."""
    start = time.monotonic()
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000,
            stream=True,
        )
        chunks = []
        first_byte_at = None
        async for chunk in stream:
            if first_byte_at is None:
                first_byte_at = time.monotonic() - start
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                chunks.append(delta)
        wall = time.monotonic() - start
        content = "".join(chunks)
        fb_label = f" first_byte={first_byte_at:.1f}s" if first_byte_at else " first_byte=NONE"
        return wall, f"SUCCESS{fb_label}", len(content)
    except Exception as exc:
        wall = time.monotonic() - start
        return wall, f"EXC {type(exc).__name__}: {str(exc)[:100]}", 0


async def run_trials(trials: int, mode: str, share_client: bool, model: str) -> None:
    if share_client:
        client_v = client_t = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=API_KEY,
            http_client=httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)),
            max_retries=0,
        )
    else:
        client_v = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=API_KEY,
            http_client=httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)),
            max_retries=0,
        )
        client_t = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=API_KEY,
            http_client=httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)),
            max_retries=0,
        )

    label = f"mode={mode} share_client={share_client} model={model}"
    print(f"\n=== {trials} trials | {label} ===\n")

    for i in range(trials):
        print(f"--- Trial {i + 1}/{trials} ---")
        if mode == "parallel":
            wall_v, out_v, len_v = 0.0, "", 0
            wall_t, out_t, len_t = 0.0, "", 0
            res_v, res_t = await asyncio.gather(
                one_call(client_v, model, PROMPT_VALUE, "value"),
                one_call(client_t, model, PROMPT_THESIS, "thesis"),
            )
            wall_v, out_v, len_v = res_v
            wall_t, out_t, len_t = res_t
            print(f"  [value  ] wall={wall_v:6.1f}s chars={len_v} outcome={out_v}")
            print(f"  [thesis ] wall={wall_t:6.1f}s chars={len_t} outcome={out_t}")
        else:
            for a_name, client, prompt in (
                ("value", client_v, PROMPT_VALUE),
                ("thesis", client_t, PROMPT_THESIS),
            ):
                wall, out, ln = await one_call(client, model, prompt, a_name)
                print(f"  [{a_name:7s}] wall={wall:6.1f}s chars={ln} outcome={out}")
        print()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--mode", choices=("parallel", "serial"), default="parallel")
    ap.add_argument("--separate-clients", action="store_true", help="Use different AsyncClients")
    ap.add_argument("--model", default=MODEL_PRIMARY)
    args = ap.parse_args()
    await run_trials(
        args.trials, args.mode, share_client=not args.separate_clients, model=args.model
    )


if __name__ == "__main__":
    asyncio.run(main())
