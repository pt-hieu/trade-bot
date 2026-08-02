#!/usr/bin/env python3
"""
Migration 117: Agent config bugfixes from 2026-02-24 audit.

Changes:
  1. longterm: MiniMax-M2.5 → Kimi-K2.5 (heavy) — structured output failures
  2. entry_strategist: tool_similar_days → tool_get_similar_days (naming convention fix)
  3. midday: add tool_get_executed_trades to enabled_tools + update system_prompt
  4. retro_evaluator: add [UNPLANNED_ENTRY] detection to system_prompt

Run:
    uv run python scripts/db/migrations/117_agent_config_bugfixes.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.database import Database

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agents" / "configs"


def load_config(agent_key: str) -> dict:
    path = CONFIGS_DIR / f"{agent_key}.json"
    with open(path) as f:
        return json.load(f)


async def main():
    async with Database() as db:
        # 1. longterm: model upgrade
        cfg = load_config("longterm")
        await db.execute(
            """
            UPDATE agent_prompts
            SET model_id = $1,
                model_tier = $2,
                system_prompt = $3,
                enabled_tools = $4,
                updated_at = NOW()
            WHERE agent_key = 'longterm'
            """,
            cfg["model_id"],
            cfg["model_tier"],
            cfg["system_prompt"],
            cfg["enabled_tools"],
        )
        print("✅ longterm: model → Kimi-K2.5 (heavy)")

        # 2. entry_strategist: rename tool in enabled_tools + prompt
        cfg = load_config("entry_strategist")
        await db.execute(
            """
            UPDATE agent_prompts
            SET enabled_tools = $1,
                system_prompt = $2,
                updated_at = NOW()
            WHERE agent_key = 'entry_strategist'
            """,
            cfg["enabled_tools"],
            cfg["system_prompt"],
        )
        print("✅ entry_strategist: tool_similar_days → tool_get_similar_days")

        # 3. midday: add tool_get_executed_trades + updated prompt
        cfg = load_config("midday")
        await db.execute(
            """
            UPDATE agent_prompts
            SET enabled_tools = $1,
                system_prompt = $2,
                updated_at = NOW()
            WHERE agent_key = 'midday'
            """,
            cfg["enabled_tools"],
            cfg["system_prompt"],
        )
        print("✅ midday: added tool_get_executed_trades, removed tool_get_goal ref")

        # 4. retro_evaluator: add [UNPLANNED_ENTRY] detection section
        cfg = load_config("retro_evaluator")
        await db.execute(
            """
            UPDATE agent_prompts
            SET system_prompt = $1,
                updated_at = NOW()
            WHERE agent_key = 'retro_evaluator'
            """,
            cfg["system_prompt"],
        )
        print("✅ retro_evaluator: added unplanned entry detection")

        print("\nMigration 117 complete.")


if __name__ == "__main__":
    asyncio.run(main())
