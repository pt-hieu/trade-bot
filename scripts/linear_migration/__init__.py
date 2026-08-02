"""Linear seam helpers: client, labels, findings contract, dedup, export renderers.

Post-cutover the YAML issues tree lives in ``the pre-cutover legacy issue export``; Linear
team Swingy is the source of truth. This package holds the small Python
pieces that glue /pipeline-review and /audit to Linear:

- client.py: shared httpx GraphQL client with 429 backoff + ``require_api_key``.
- findings_schema.py: Pydantic contract the orchestrator validates against
  fenced-JSON blocks emitted by /pipeline-review and /audit subagents.
- dedup.py: content-hash report_id + sentinel bookkeeping so re-running the
  write-back is idempotent.
- export_render.py: pure markdown renderers for ``monitoring_items.md`` +
  ``resolved_items.md`` consumed by ``scripts/export_issues.py``.
- labels.json: legacy-enum -> Linear-label-id map consumed by
  ``process_review_findings.py`` on every new-finding write-back.
- id_map.json: legacy-id -> Linear-id lookup (one-shot migration output,
  repo-tracked for grep).
- last_export.md: 7-day stale cache served when Linear is unreachable.
"""
