"""Narrative dedup thresholds — single source of truth (SWI-74).

CLAUDE.md mandates centralized rules in ``shared/rules/`` for any
cross-cutting deterministic logic. The narrative-tracker write-time
match, intra-batch coalesce, and post-write SQL merger all read from
this module so the three thresholds cannot drift apart.

The migration ``NNN_narrative_same_sentiment_merge.sql`` cites
``POSTWRITE_MERGE`` in a header comment. ``tests/unit/
test_narrative_threshold_parity.py`` regex-extracts the cosine literal
from any narrative-merge migration and asserts equality with the
Python constant — turns the comment into a structural guard
(per project_schema_migrations_guard.md).
"""

from __future__ import annotations

# Article-to-centroid cosine similarity floor at write time.
# Existing behaviour (was inline ``SIMILARITY_THRESHOLD = 0.72``).
WRITE_TIME_MATCH: float = 0.72

# Adaptive tightening cap for write-time match: the matcher adds
# ``min(article_count * 0.003, WRITE_TIME_TIGHTEN_CAP)`` so mature
# narratives need a closer fit. Existing behaviour (was inline 0.04).
WRITE_TIME_TIGHTEN_CAP: float = 0.04

# Intra-batch article-to-article mutual cosine for coalescing
# unmatched articles into the same new narrative (Layer 1, SWI-74).
INTRABATCH_COALESCE: float = 0.80

# Tighter intra-batch threshold used when no member of a raw cluster
# carries trusted sentiment confidence — the Fix 6 opposite-sentiment
# split cannot fire on untrusted members so we compensate with a
# stricter embedding match. See narrative_clustering.py.
INTRABATCH_COALESCE_UNTRUSTED: float = 0.85

# Post-write SQL merger cosine for collapsing same-sentiment same-day
# duplicates that slipped past write-time + intra-batch (Layer 2).
# Cited verbatim in narrative-merge migrations.
POSTWRITE_MERGE: float = 0.82

# Sentiment magnitude floor for the opposite-sign reject gate. Hoisted
# from data.narrative_matching so the intra-batch split predicate uses
# the identical constant (Fix 6 parity, SWI-103).
SENTIMENT_REJECT_MIN_MAGNITUDE: float = 0.15
