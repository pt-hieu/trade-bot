"""Asserts only news_v2_persist writes articles.affected_tickers (SWI-390)."""

from __future__ import annotations

import pathlib
import re

ALLOWED = {
    "scripts/pipeline/news_v2_persist.py",
    # insert_content.py writes an empty `[]` at INSERT time and *intentionally*
    # excludes affected_tickers from its ON CONFLICT UPDATE list (SWI-390), so
    # it never sets a non-empty tag. Allowed for the schema-column write only.
    "scripts/shared/neon/insert_content.py",
}

# Scope the regex to the `articles` table only. The earlier broad pattern
# matched narratives.affected_tickers and catalysts.affected_tickers writes
# (legitimate, different tables) → would fire on a clean tree, force devs to
# add them to ALLOWED, defang the test.
PATTERN = re.compile(
    r"UPDATE\s+articles\s+[^;]*SET\s+[^;]*affected_tickers\s*=|"
    r"INSERT\s+INTO\s+articles\s*\([^)]*affected_tickers",
    re.IGNORECASE | re.DOTALL,
)


def test_single_writer_for_affected_tickers() -> None:
    root = pathlib.Path(__file__).resolve().parents[2] / "scripts"
    offenders = []
    for path in root.rglob("*.py"):
        rel = str(path.relative_to(root.parent))
        if rel in ALLOWED:
            continue
        if PATTERN.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], (
        f"affected_tickers writer outside allowed list: {offenders}. "
        f"If intentional, update ALLOWED in this test AND document why."
    )
