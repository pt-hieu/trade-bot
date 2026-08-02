"""Unit tests for OpenRouter session tracking."""

import re

from shared.session import (
    add_provider_exclusion,
    get_extra_body,
    get_session_id,
    init_session,
    reset_session,
)


def setup_function():
    """Reset session state before each test."""
    reset_session()


def test_get_extra_body_returns_none_before_init():
    assert get_extra_body() is None
    assert get_extra_body(agent_name="market_level") is None


def test_get_session_id_returns_none_before_init():
    assert get_session_id() is None


def test_init_session_returns_valid_session_id():
    session_id = init_session("morning")
    assert session_id is not None
    assert re.match(r"^morning_\d{4}-\d{2}-\d{2}_[0-9a-f]{6}$", session_id)


def test_session_id_max_128_chars():
    session_id = init_session("very_long_pipeline_name_that_is_still_valid")
    assert len(session_id) <= 128


def test_get_session_id_after_init():
    expected = init_session("retro")
    assert get_session_id() == expected


def test_get_extra_body_structure():
    init_session("midday")
    body = get_extra_body(agent_name="market_level")
    assert body is not None
    assert "session_id" in body
    assert "trace" in body

    trace = body["trace"]
    assert trace["trace_id"] == body["session_id"]
    assert trace["trace_name"] == "midday"
    assert trace["generation_name"] == "market_level"
    assert "environment" in trace


def test_get_extra_body_without_agent_name():
    init_session("morning")
    body = get_extra_body()
    assert body is not None
    assert "generation_name" not in body["trace"]


def test_get_extra_body_with_agent_name():
    init_session("morning")
    body = get_extra_body(agent_name="sector_analysts")
    assert body is not None
    assert body["trace"]["generation_name"] == "sector_analysts"


def test_get_extra_body_excludes_siliconflow_provider():
    """Every OpenRouter call must opt-out of SiliconFlow backend.

    SiliconFlow was implicated in the 2026-04-21 synthesis_picks 180s hang (pre-SWI-318)
    (50% lower throughput on GLM-5 than z-ai direct). Regression guard.
    """
    init_session("morning")
    body = get_extra_body(agent_name="synthesis_picks")
    assert body is not None
    provider = body.get("provider")
    assert provider is not None, "provider routing block missing"
    assert "siliconflow" in provider.get("ignore", []), (
        "siliconflow must remain in provider.ignore list"
    )
    assert provider.get("allow_fallbacks") is True, (
        "allow_fallbacks must stay true so other healthy backends still serve"
    )


def test_get_extra_body_routing_unpinned_speed_sort():
    """Routing must be unpinned + throughput-sorted, never re-pinned to one upstream.

    Encodes the unpin+speed-sort decision (SWI-369/375/378): c5d69301 had pinned
    every model to a single upstream via `order:["chutes"]`/`quantizations:["fp8"]`,
    making one slow/cold upstream hang every model alike. The absence of `order`
    and `quantizations` is the load-bearing assertion — it prevents a silent
    regression back to that pin.
    """
    init_session("morning")
    add_provider_exclusion("some-bad-upstream")
    body = get_extra_body(agent_name="synthesis_picks")
    assert body is not None
    provider = body.get("provider")
    assert provider is not None, "provider routing block missing"

    assert provider.get("sort") == "throughput", "must restore SWI-126 throughput-sort"
    assert provider.get("require_parameters") is True, (
        "require_parameters must be true — also kills the SWI-376 tool_choice 404 storm"
    )
    assert provider.get("allow_fallbacks") is True
    assert "siliconflow" in provider.get("ignore", [])
    assert "together" in provider.get("ignore", []), (
        "together must remain excluded (SWI-126 throughput regression)"
    )
    assert "some-bad-upstream" in provider.get("ignore", []), (
        "dynamic excludes must still merge into ignore"
    )

    assert "order" not in provider, "must NOT re-pin to a single upstream (c5d69301 regression)"
    assert "quantizations" not in provider, "must NOT pin quantizations (c5d69301 regression)"


def test_reset_session_clears_state():
    init_session("morning")
    assert get_session_id() is not None
    reset_session()
    assert get_session_id() is None
    assert get_extra_body() is None
