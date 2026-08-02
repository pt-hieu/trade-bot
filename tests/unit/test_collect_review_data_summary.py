"""SWI-125 Surface 6: envelope-error counter coverage in build_logfire_summary.

The May 12 `statistic.get_stats` TypeError emitted
`{"error": "unsupported operand ..."}` as a tool *return* (no exception).
Both is_exception and error_type were unset on the span, so the existing
tool_exception_count / tool_error_count missed it. This test pins the new
tool_error_envelope_count detector across the four observed shapes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import collect_review_data  # noqa: E402


def _make_broker_tool_span(*, tool_name: str, response: str, parent_id: str = "p1") -> dict:
    return {
        "span_id": f"span_{tool_name}_{hash(response) & 0xFFFF:x}",
        "parent_span_id": parent_id,
        "trace_id": "trace_x",
        "span_name": f"running tool: {tool_name}",
        "duration": 0.05,
        "is_exception": False,
        "attributes": {
            "tool_name": tool_name,
            "tool_response": response,
        },
    }


def _wrap(spans: list[dict]) -> dict:
    traces = [
        {
            "trace_id": "trace_x",
            "span_name": "morning_brief_generation",
            "duration": 100.0,
        }
    ]
    return collect_review_data.build_logfire_summary(spans, traces)


def test_envelope_error_dict_double_quotes_counted() -> None:
    span = _make_broker_tool_span(
        tool_name="statistic.get_stats",
        response='{"error": "unsupported operand type", "prose": "Failed to compute"}',
    )
    summary = _wrap([span])
    assert summary["tool_error_envelope_count"] == 1
    assert summary["tool_error_envelopes"][0]["kind"] == "dict"


def test_envelope_error_dict_single_quotes_counted() -> None:
    span = _make_broker_tool_span(
        tool_name="enrichment.get_flow",
        response="{'error': 'timeout', 'prose': 'Failed to fetch'}",
    )
    summary = _wrap([span])
    assert summary["tool_error_envelope_count"] == 1


def test_envelope_error_list_form_counted() -> None:
    span = _make_broker_tool_span(
        tool_name="article.search",
        response='[{"error": "no rows"}]',
    )
    summary = _wrap([span])
    assert summary["tool_error_envelope_count"] == 1
    assert summary["tool_error_envelopes"][0]["kind"] == "list"


def test_envelope_bare_failed_to_prose_counted() -> None:
    span = _make_broker_tool_span(
        tool_name="alerts.create",
        response="Failed to register alert: validation failed",
    )
    summary = _wrap([span])
    assert summary["tool_error_envelope_count"] == 1
    assert summary["tool_error_envelopes"][0]["kind"] == "prose"


def test_healthy_tool_return_not_counted() -> None:
    span = _make_broker_tool_span(
        tool_name="technicals.get",
        response='{"rsi": 42, "ma20": 50000}',
    )
    summary = _wrap([span])
    assert summary["tool_error_envelope_count"] == 0


def test_per_agent_breakdown_groups_by_parent_agent() -> None:
    spans = [
        _make_broker_tool_span(
            tool_name="statistic.get_stats",
            response='{"error": "x"}',
            parent_id="agent_run_1",
        ),
        _make_broker_tool_span(
            tool_name="enrichment.get_flow",
            response="Failed to fetch flow",
            parent_id="agent_run_1",
        ),
        _make_broker_tool_span(
            tool_name="article.search",
            response='[{"error": "y"}]',
            parent_id="agent_run_2",
        ),
    ]
    summary = _wrap(spans)
    assert summary["tool_error_envelope_count"] == 3
    by_agent = summary["tool_error_envelopes_by_agent"]
    # parent_agent falls back to parent_span_id when the agent run isn't seen first
    assert sum(len(v) for v in by_agent.values()) == 3
