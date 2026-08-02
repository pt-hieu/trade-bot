"""Inspect Kimi-K2.5 stream chunks — is it sending reasoning tokens forever?

Theory: Kimi-K2.5 is a reasoning model. If it streams `<reasoning>` chunks
indefinitely without ever emitting `content`, httpx read timeout resets per
chunk (SSE keep-alive equivalent), and PydanticAI waits until the outer
asyncio.wait_for wall fires at 180-240s.

Raw OpenAI SDK treats `delta.content=None` as empty and returns quickly once
the stream closes — but the stream may be very slow to close if reasoning
tokens dominate.
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
MODEL = "moonshotai/Kimi-K2.5"

PROMPT = """You are a value analyst. Analyze 3 stocks: FPT, TCB, VHM.
Output a JSON array: [{"ticker", "action", "confidence", "reasoning"}, ...].
Keep reasoning to 2 sentences each."""


async def one_inspect(label: str, index: int, client: AsyncOpenAI) -> None:
    start = time.monotonic()
    content_chunks = 0
    reasoning_chunks = 0
    empty_chunks = 0
    total_chunks = 0
    content_len = 0
    last_chunk_time = start
    max_gap = 0.0
    finish_reason = None
    try:
        stream = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=0.2,
            max_tokens=2000,
            stream=True,
        )
        async for chunk in stream:
            total_chunks += 1
            now = time.monotonic()
            gap = now - last_chunk_time
            if gap > max_gap:
                max_gap = gap
            last_chunk_time = now
            if not chunk.choices:
                empty_chunks += 1
                continue
            ch = chunk.choices[0]
            if ch.finish_reason:
                finish_reason = ch.finish_reason
            delta = ch.delta
            # Check for reasoning field (OpenRouter-specific, not stock OpenAI)
            raw = chunk.model_dump().get("choices", [{}])[0].get("delta", {})
            reasoning = raw.get("reasoning")
            if delta.content:
                content_chunks += 1
                content_len += len(delta.content)
            elif reasoning:
                reasoning_chunks += 1
            else:
                empty_chunks += 1
        wall = time.monotonic() - start
        print(
            f"[{label} #{index}] wall={wall:5.1f}s chunks(total={total_chunks} "
            f"content={content_chunks} reasoning={reasoning_chunks} empty={empty_chunks}) "
            f"content_len={content_len} max_gap={max_gap:.1f}s finish={finish_reason}"
        )
    except Exception as exc:
        wall = time.monotonic() - start
        print(f"[{label} #{index}] wall={wall:5.1f}s EXC {type(exc).__name__}: {exc}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--parallel", action="store_true")
    args = ap.parse_args()

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
        http_client=httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)),
        max_retries=0,
    )

    print(f"\n=== {args.trials} trials | parallel={args.parallel} | {MODEL} ===\n")

    for i in range(args.trials):
        if args.parallel:
            await asyncio.gather(
                one_inspect("value ", i + 1, client),
                one_inspect("thesis", i + 1, client),
            )
        else:
            await one_inspect("value ", i + 1, client)
            await one_inspect("thesis", i + 1, client)


if __name__ == "__main__":
    asyncio.run(main())
