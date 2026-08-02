#!/usr/bin/env python3
"""SWI-241 News v2 read-path chokepoint guard.

Rejects new ``FROM narratives`` / ``FROM catalysts`` SQL outside the
sanctioned set of helper modules. Protects the v2 pipeline_version filter
from being bypassed by ad-hoc queries.

Sanctioned read sites:
  * scripts/shared/neon/narratives.py
  * scripts/shared/neon/catalysts.py
  * scripts/shared/neon/catalyst_signals.py
  * scripts/shared/neon/catalyst_summaries.py
  * scripts/news_pipeline_v2.py            (orchestrator self-queries)
  * scripts/db/migrations/*.sql            (schema operations)
  * scripts/maintenance/narrative_cluster_scan.py
  * scripts/adhoc/verify_catalyst_coverage.py
  * scripts/db/backfill_article_sentiment.py
  * web/src/server/fns/narratives.ts
  * web/src/server/fns/catalysts.ts
  * web/src/lib/chat/tools/watchlist.ts

Add new sanctioned files to ``ALLOWED`` only after the file's queries
include the explicit ``pipeline_version = 'v2'`` filter.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED = frozenset(
    {
        "scripts/shared/neon/narratives.py",
        "scripts/shared/neon/catalysts.py",
        "scripts/shared/neon/catalyst_signals.py",
        "scripts/shared/neon/catalyst_summaries.py",
        "scripts/news_pipeline_v2.py",
        "scripts/pipeline/news_v2_persist.py",
        "scripts/maintenance/narrative_cluster_scan.py",
        "scripts/adhoc/verify_catalyst_coverage.py",
        "scripts/eval/catalyst_coverage_audit.py",
        "scripts/db/backfill_article_sentiment.py",
        "web/src/server/fns/narratives.ts",
        "web/src/server/fns/catalysts.ts",
        "web/src/lib/chat/tools/watchlist.ts",
    }
)

PATTERN = re.compile(r"FROM\s+(narratives|catalysts)\b", re.IGNORECASE)


def main(argv: list[str]) -> int:
    failures: list[str] = []
    for path in argv[1:]:
        rel = path.lstrip("./")
        if rel in ALLOWED:
            continue
        if rel.startswith("scripts/db/migrations/") or rel.startswith("scripts/db/migrations\\"):
            continue
        if rel.startswith("scripts/hooks/"):
            continue
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                failures.append(f"{path}:{line_no}: {line.strip()}")
    if failures:
        sys.stderr.write(
            "News v2 read-path chokepoint violation — every read of "
            "`narratives` / `catalysts` must go through shared/neon helpers "
            "so the `pipeline_version = 'v2'` filter applies.\n"
        )
        sys.stderr.write(
            "If a new helper file is genuinely required, add the path to "
            "ALLOWED in scripts/hooks/check_news_v2_pipeline_version_filter.py "
            "AFTER its query carries the explicit version filter.\n\n"
        )
        for f in failures:
            sys.stderr.write(f + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
