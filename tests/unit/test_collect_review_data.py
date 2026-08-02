"""Tests for collect_review_data.py — Logfire fetch path."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import collect_review_data  # noqa: E402


def test_fetch_logfire_traces_passes_limit_2000_for_per_trace_span_fetch():
    """Per-trace span fetch must request limit=2000 to avoid chronological
    truncation of late-phase spans (previously capped at 100 which hid
    phases 3-6 and masked real pipeline defects as silent fall-throughs).
    """
    recorded_calls: list[dict] = []

    def fake_logfire_query(token: str, sql: str, limit: int = 500) -> list[dict]:
        recorded_calls.append({"sql": sql, "limit": limit})
        # First call = traces discovery → return one trace so span fetch fires.
        # Subsequent calls = per-trace span fetch → return empty.
        if "WHERE trace_id" not in sql:
            return [
                {
                    "trace_id": "abc123",
                    "span_name": "morning_brief_generation",
                    "start_timestamp": "2026-04-14T00:00:00Z",
                    "end_timestamp": "2026-04-14T00:05:00Z",
                    "duration": 300.0,
                }
            ]
        return []

    with patch.object(collect_review_data, "logfire_query", side_effect=fake_logfire_query):
        collect_review_data.fetch_logfire_traces(token="fake-token", target_date="2026-04-14")

    # Identify the per-trace span fetch call (has "WHERE trace_id" in SQL).
    per_trace_calls = [call for call in recorded_calls if "WHERE trace_id" in call["sql"]]
    assert len(per_trace_calls) == 1, "Expected exactly one per-trace span fetch"
    assert per_trace_calls[0]["limit"] == 2000, (
        f"Per-trace span fetch must use limit=2000, got {per_trace_calls[0]['limit']}"
    )
