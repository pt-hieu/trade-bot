"""SWI-74 Layer 3: weekly narrative-cluster regression watch.

Queries active narratives within the last 7 days, groups by
``(narrative_type, intersected ticker tuple)`` and flags any bucket
with ``COUNT(*) > 3`` plus any pair whose centroid cosine ≥
``POSTWRITE_MERGE`` and is not yet linked via ``merged_into``.

Emits a fenced-JSON block matching the contract consumed by
``scripts/process_review_findings.py`` — when piped into that script
the findings get filed against SWI-74's regression-watch child issue.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.database import get_db  # noqa: E402
from shared.rules.narrative_thresholds import POSTWRITE_MERGE  # noqa: E402

# Bucket size that trips the regression-watch flag — keep aligned with the
# SWI-74 evidence threshold (Hormuz/oil cluster grew to ~140 active rows;
# >3 same-type same-ticker rows is already a smoke signal).
BUCKET_FLAG_FLOOR = 3
WINDOW_DAYS = 7


async def _scan() -> dict:
    """Return ``{"buckets": [...], "pairs": [...]}`` for report rendering."""
    db = await get_db()

    bucket_rows = await db.fetch_all(
        """
        SELECT
          narrative_type,
          affected_tickers,
          COUNT(*) AS row_count,
          ARRAY_AGG(narrative_key ORDER BY first_seen) AS narrative_keys,
          MIN(first_seen) AS first_seen_min,
          MAX(last_seen) AS last_seen_max
        FROM narratives
        WHERE status = 'active'
          AND pipeline_version = 'v2'
          AND first_seen >= CURRENT_DATE - ($1 || ' days')::INTERVAL
          AND narrative_type IS NOT NULL
        GROUP BY narrative_type, affected_tickers
        HAVING COUNT(*) > $2
        ORDER BY COUNT(*) DESC
        """,
        str(WINDOW_DAYS),
        BUCKET_FLAG_FLOOR,
    )

    pair_rows = await db.fetch_all(
        """
        SELECT
          a.id AS a_id,
          a.narrative_key AS a_key,
          b.id AS b_id,
          b.narrative_key AS b_key,
          (1 - (a.centroid_embedding <=> b.centroid_embedding)) AS cosine,
          LEAST(a.first_seen, b.first_seen) AS first_seen_min
        FROM narratives a
        JOIN narratives b ON b.id > a.id
        WHERE a.status = 'active'
          AND b.status = 'active'
          AND a.pipeline_version = 'v2'
          AND b.pipeline_version = 'v2'
          AND a.first_seen >= CURRENT_DATE - ($1 || ' days')::INTERVAL
          AND b.first_seen >= CURRENT_DATE - ($1 || ' days')::INTERVAL
          AND a.centroid_embedding IS NOT NULL
          AND b.centroid_embedding IS NOT NULL
          AND a.merged_into IS NULL
          AND b.merged_into IS NULL
          AND a.narrative_type = b.narrative_type
          AND ((a.affected_tickers && b.affected_tickers)
               OR (a.affected_sectors && b.affected_sectors))
          AND (1 - (a.centroid_embedding <=> b.centroid_embedding)) >= $2
        ORDER BY cosine DESC
        LIMIT 50
        """,
        str(WINDOW_DAYS),
        POSTWRITE_MERGE,
    )

    return {
        "buckets": [dict(r) for r in bucket_rows],
        "pairs": [dict(r) for r in pair_rows],
    }


def _render_findings(scan: dict) -> dict:
    """Map scan results to the FindingsBlock contract."""
    findings: list[dict] = []
    for bucket in scan["buckets"]:
        keys = bucket.get("narrative_keys") or []
        first_seen = bucket.get("first_seen_min")
        evidence_lines = [
            f"narrative_type={bucket.get('narrative_type')}",
            f"affected_tickers={list(bucket.get('affected_tickers') or [])}",
            f"row_count={bucket.get('row_count')}",
            f"first_seen_min={first_seen}",
            f"last_seen_max={bucket.get('last_seen_max')}",
            f"narrative_keys={list(keys)[:10]}",
        ]
        findings.append(
            {
                "category": "regression-watch",
                "title": (
                    f"{bucket.get('row_count')} active narratives on "
                    f"{bucket.get('narrative_type')} cluster "
                    f"({list(bucket.get('affected_tickers') or [])[:3]}...)"
                )[:200],
                "severity": "warning",
                "dimension": "reasoning-and-output",
                "evidence": "\n".join(evidence_lines),
                "watch_for": (
                    "Same-type narratives sharing tickers should collapse via "
                    "intra-batch coalesce or migration 337's same-sentiment merge."
                ),
            }
        )
    for pair in scan["pairs"]:
        findings.append(
            {
                "category": "regression-watch",
                "title": (
                    f"Unmerged near-duplicate pair: "
                    f"{pair.get('a_key')} ↔ {pair.get('b_key')} "
                    f"(cosine={float(pair.get('cosine') or 0):.3f})"
                )[:200],
                "severity": "warning",
                "dimension": "reasoning-and-output",
                "evidence": (
                    f"a_id={pair.get('a_id')} b_id={pair.get('b_id')}\n"
                    f"a_key={pair.get('a_key')}\n"
                    f"b_key={pair.get('b_key')}\n"
                    f"cosine={float(pair.get('cosine') or 0):.4f}\n"
                    f"first_seen_min={pair.get('first_seen_min')}\n"
                    f"threshold=POSTWRITE_MERGE={POSTWRITE_MERGE}"
                ),
                "watch_for": (
                    "Pair should have been linked by migration 337's same-sentiment "
                    "merge; surviving means narrative_type or ticker overlap drifted."
                ),
            }
        )

    return {
        "regressions": [],
        "new": findings,
        "bumps": [],
        "resolved_candidates": [],
    }


async def main() -> int:
    scan = await _scan()
    findings = _render_findings(scan)

    print(f"Narrative cluster scan — window={WINDOW_DAYS}d")
    print(f"  buckets flagged: {len(scan['buckets'])}")
    print(f"  pair candidates: {len(scan['pairs'])}")
    print()
    print("```json")
    print(json.dumps(findings, default=str, indent=2))
    print("```")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
