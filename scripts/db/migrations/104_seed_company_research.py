#!/usr/bin/env python3
"""
Migration 104: Seed company_research table from static markdown files.

Parses research/companies/*.md files and inserts structured sections
into the company_research table with auto_generated=FALSE.

Run after migration 103:
    uv run python scripts/db/migrations/104_seed_company_research.py
"""

import asyncio
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.database import Database, get_db

RESEARCH_DIR = Path(__file__).parent.parent.parent.parent / "research" / "companies"
RESEARCH_DATE = date(2026, 1, 23)

# Map heading keywords → section keys
SECTION_MAP = {
    "overview": "overview",
    "company overview": "overview",
    "financial health": "financials",
    "financials": "financials",
    "competitive moat": "moat",
    "moat": "moat",
    "management": "management",
    "governance": "management",
    "growth": "growth",
    "growth drivers": "growth",
    "risks": "risks",
    "valuation": "valuation",
    "valuation assessment": "valuation",
    "investment thesis": "thesis",
    "thesis": "thesis",
    "thesis summary": "thesis",
}


def _extract_sections(text: str) -> dict:
    """Parse markdown into section dict using heading detection."""
    sections: dict[str, list[str]] = {}
    current_key = None
    current_lines: list[str] = []

    for line in text.splitlines():
        # Detect ## or ### headings
        heading_match = re.match(r"^#{2,3}\s+\d*\.?\s*(.+)", line)
        if heading_match:
            if current_key and current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections[current_key] = sections.get(current_key, "") + "\n" + content
            raw_heading = heading_match.group(1).strip().lower()
            # Remove trailing punctuation
            raw_heading = raw_heading.rstrip(".:").strip()
            current_key = None
            for keyword, key in SECTION_MAP.items():
                if keyword in raw_heading:
                    current_key = key
                    break
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)

    # Flush last section
    if current_key and current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            existing = sections.get(current_key, "")
            sections[current_key] = (existing + "\n" + content).strip() if existing else content

    # Trim each section to a reasonable length for storage
    return {k: v.strip()[:3000] for k, v in sections.items() if v.strip()}


async def seed_research():
    md_files = sorted(RESEARCH_DIR.glob("*.md"))
    md_files = [f for f in md_files if not f.name.startswith("_")]

    if not md_files:
        print(f"No markdown files found in {RESEARCH_DIR}")
        return

    db = await get_db()
    inserted = 0
    skipped = 0

    for md_path in md_files:
        ticker = md_path.stem.upper()
        text = md_path.read_text(encoding="utf-8")
        sections = _extract_sections(text)

        if not sections:
            print(f"  [SKIP] {ticker}: no sections extracted")
            skipped += 1
            continue

        await db.execute(
            """
            INSERT INTO company_research (ticker, sections, research_date, auto_generated, version)
            VALUES ($1, $2::jsonb, $3, FALSE, 1)
            ON CONFLICT (ticker) DO UPDATE
            SET sections = EXCLUDED.sections,
                research_date = EXCLUDED.research_date,
                auto_generated = EXCLUDED.auto_generated,
                version = company_research.version,
                updated_at = NOW()
            """,
            ticker,
            json.dumps(sections),
            RESEARCH_DATE,
        )
        print(f"  [OK] {ticker}: {list(sections.keys())}")
        inserted += 1

    print(f"\nDone: {inserted} inserted, {skipped} skipped")


async def main():
    async with Database():
        await seed_research()


if __name__ == "__main__":
    asyncio.run(main())
