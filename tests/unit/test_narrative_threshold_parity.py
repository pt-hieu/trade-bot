"""Parity guard: SQL narrative-merge migrations must cite the Python POSTWRITE_MERGE.

Per ``project_schema_migrations_guard.md``: the post-write merger's
cosine threshold lives in two places — the Python rules module and the
SQL migration that enforces it. The plain-text comment ``cosine >= 0.82``
inside the migration is the only thing tying them together; this test
turns that comment into a structural guard so a future migration that
forgets to update one side fails the build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.rules.narrative_thresholds import POSTWRITE_MERGE

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _REPO_ROOT / "scripts" / "db" / "migrations"

# Match SQL files that touch narrative merge logic — narrowed by filename
# rather than content so a refactor that adds another mention of the
# merge SQL inside an unrelated migration doesn't trip the guard.
_NARRATIVE_MERGE_PATTERN = re.compile(r"^\d+_narrative_(?:dedup|same_sentiment|merge).*\.sql$")
_COSINE_LITERAL_PATTERN = re.compile(
    r"1\s*-\s*\([a-z0-9_.]+\.centroid_embedding\s*<=>\s*[a-z0-9_.]+\.centroid_embedding\)\s*\)*\s*>=\s*([0-9.]+)",
    re.IGNORECASE,
)


def _narrative_merge_migrations() -> list[Path]:
    return sorted(
        path
        for path in _MIGRATIONS_DIR.iterdir()
        if path.is_file() and _NARRATIVE_MERGE_PATTERN.match(path.name)
    )


def test_at_least_one_narrative_merge_migration_exists() -> None:
    """Sanity: the guard must cover at least one migration."""
    assert _narrative_merge_migrations(), (
        "Expected at least one narrative-merge migration; "
        "rename matcher in test_narrative_threshold_parity if directory layout changed."
    )


@pytest.mark.parametrize(
    "migration_path",
    _narrative_merge_migrations(),
    ids=lambda path: path.name,
)
def test_postwrite_merge_constant_matches_sql_literal(migration_path: Path) -> None:
    """Each narrative-merge migration's centroid-cosine literal must equal POSTWRITE_MERGE.

    324 (opposite-sentiment) does not gate on cosine — it has no centroid
    distance clause — so the matcher returns no hits and the test skips
    that file. 337 and any future same-sentiment merge must include the
    literal.
    """
    body = migration_path.read_text(encoding="utf-8")
    matches = _COSINE_LITERAL_PATTERN.findall(body)
    if not matches:
        pytest.skip(f"{migration_path.name} does not gate on centroid cosine; nothing to verify.")
    for raw in matches:
        sql_literal = float(raw)
        assert sql_literal == POSTWRITE_MERGE, (
            f"{migration_path.name}: SQL cosine threshold {sql_literal} "
            f"!= shared.rules.narrative_thresholds.POSTWRITE_MERGE={POSTWRITE_MERGE}. "
            "Update both sites together."
        )
