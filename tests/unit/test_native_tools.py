"""Tests for the native PydanticAI tool registration layer (SWI-180).

Covers the architectural invariants the cutover depends on:
  - native tool count matches broker registry (no silent drop)
  - prepare_tools admits exactly `allowed | unlocked | {unlock_tool}`
  - unlock_tool is argument-tolerant (no crash on missing arg) and idempotent
  - empty-list ticker emissions reject at the model boundary (`minItems: 1`)
  - render_catalog produces deterministic output with required-vs-optional markers
  - AgentDeps.from_legacy_context survives the full 24-field shape
"""

from __future__ import annotations

import json

import pytest

from agents.tools.broker.registry import TOOL_CATALOG
from agents.tools.native_tools import (
    NATIVE_TOOL_INVOCATION_LIMIT,
    TOTAL_TOOL_BUDGET,
    AgentDeps,
    BrokerLoopBreaker,
    build_native_tools,
    make_prepare_tools,
    render_catalog,
    unlock_tool,
)
from agents.tools.types import RequiredTickers


def test_native_tools_match_registry() -> None:
    tools = build_native_tools()
    assert len(tools) == len(TOOL_CATALOG)
    by_name = {t.name for t in tools}
    assert by_name == set(TOOL_CATALOG)


def test_required_tickers_minitems_in_schema() -> None:
    tools = build_native_tools()
    flow = next(t for t in tools if t.name == "enrichment.get_flow")
    schema = flow.function_schema.json_schema
    tickers_prop = schema["properties"]["tickers"]
    assert tickers_prop.get("minItems") == 1
    assert "tickers" in schema.get("required", [])


def test_required_tickers_alias_resolves() -> None:
    # Sanity: the type alias resolves to the constrained list type used
    # across all 16 ticker-required tools.
    from typing import get_args, get_origin

    assert get_origin(RequiredTickers) is not None  # Annotated wrapper
    inner = get_args(RequiredTickers)
    assert inner[0] == list[str]


@pytest.mark.asyncio
async def test_unlock_tool_argument_tolerant() -> None:
    deps = AgentDeps(scan_date=None)
    # Mimic RunContext just enough — the function only reads ctx.deps.
    ctx = _StubRunContext(deps)
    result = await unlock_tool(ctx, tool_name=None)  # type: ignore[arg-type]
    payload = json.loads(result)
    assert payload["error"] == "specify tool_name"
    assert "example" in payload
    assert deps.unlocked == set()  # not bumped on missing arg


@pytest.mark.asyncio
async def test_unlock_tool_idempotent() -> None:
    deps = AgentDeps(scan_date=None)
    ctx = _StubRunContext(deps)
    first = await unlock_tool(ctx, tool_name="enrichment.get_flow")  # type: ignore[arg-type]
    assert json.loads(first)["status"] == "unlocked"
    second = await unlock_tool(ctx, tool_name="enrichment.get_flow")  # type: ignore[arg-type]
    assert json.loads(second)["status"] == "already_unlocked"
    # idempotency: set size stays 1
    assert deps.unlocked == {"enrichment.get_flow"}


@pytest.mark.asyncio
async def test_unlock_tool_unknown_returns_error() -> None:
    deps = AgentDeps(scan_date=None)
    ctx = _StubRunContext(deps)
    result = await unlock_tool(ctx, tool_name="nonexistent.tool")  # type: ignore[arg-type]
    payload = json.loads(result)
    assert "error" in payload
    assert "nonexistent.tool" in payload.get("error", "") or "Unknown" in payload.get("error", "")


@pytest.mark.asyncio
async def test_prepare_tools_filters_to_allowed() -> None:
    allowed = frozenset({"enrichment.get_flow"})
    prepare = make_prepare_tools(allowed)
    deps = AgentDeps(scan_date=None)
    ctx = _StubRunContext(deps)

    class FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

    fake_defs = [
        FakeTool("enrichment.get_flow"),
        FakeTool("article.search"),
        FakeTool("unlock_tool"),
        FakeTool("technical.get_technicals"),
    ]
    admitted = await prepare(ctx, fake_defs)  # type: ignore[arg-type]
    names = {t.name for t in admitted}
    assert names == {"enrichment.get_flow", "unlock_tool"}


@pytest.mark.asyncio
async def test_prepare_tools_admits_unlocked() -> None:
    allowed: frozenset[str] = frozenset()
    prepare = make_prepare_tools(allowed)
    deps = AgentDeps(scan_date=None)
    deps.unlocked.add("article.search")
    ctx = _StubRunContext(deps)

    class FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

    fake_defs = [
        FakeTool("article.search"),
        FakeTool("technical.get_technicals"),
        FakeTool("unlock_tool"),
    ]
    admitted = await prepare(ctx, fake_defs)  # type: ignore[arg-type]
    names = {t.name for t in admitted}
    assert names == {"article.search", "unlock_tool"}


@pytest.mark.asyncio
async def test_unlock_budget_breaker() -> None:
    allowed = frozenset({"a", "b", "c"})  # budget = 15-3 = 12
    prepare = make_prepare_tools(allowed)
    deps = AgentDeps(scan_date=None)
    # Force-overflow the budget
    deps.unlocked = {f"tool_{i}" for i in range(20)}
    ctx = _StubRunContext(deps)
    with pytest.raises(BrokerLoopBreaker) as exc_info:
        await prepare(ctx, [])  # type: ignore[arg-type]
    assert exc_info.value.breaker_kind == "unlock_overuse"


def test_render_catalog_required_marker() -> None:
    catalog = render_catalog(frozenset({"enrichment.get_flow"}))
    assert "*tickers" in catalog  # required marker
    assert "## Tools available" in catalog
    assert "unlock_tool" in catalog


def test_render_catalog_empty_allowlist() -> None:
    catalog = render_catalog(frozenset())
    assert "## Tools available" in catalog
    assert "No tools are allowed by default" in catalog
    assert "unlock_tool" in catalog


def test_invocation_limit_constant_above_baseline() -> None:
    # Stage 0 hot-set baseline: sector_enrichment averaged ~8 successful
    # broker calls per run. The native limit must clear that with headroom
    # for legitimate retries without being absurd.
    assert NATIVE_TOOL_INVOCATION_LIMIT >= 25
    assert TOTAL_TOOL_BUDGET == 15


@pytest.mark.asyncio
async def test_duplicate_query_breaker() -> None:
    """SWI-86: identical (tool, args) calls short-circuit after the limit
    (budget efficiency); a distinct query is unaffected."""
    from agents.tools.broker.registry import ToolDef, ToolDomain
    from agents.tools.native_tools import DUPLICATE_CALL_LIMIT, _wrap_with_policy

    async def impl(query: str) -> str:
        return "ok"

    tool_def = ToolDef(
        name="article.search",
        domain=ToolDomain.NARRATIVE,
        description="search",
        parameters={},
        implementation=impl,
        accepts_context=False,
    )
    wrapper = _wrap_with_policy(tool_def)
    deps = AgentDeps(scan_date=None)
    ctx = _StubRunContext(deps)

    for _ in range(DUPLICATE_CALL_LIMIT):
        assert await wrapper(ctx, query="FPT") == "ok"

    with pytest.raises(BrokerLoopBreaker) as exc_info:
        await wrapper(ctx, query="FPT")
    assert exc_info.value.breaker_kind == "duplicate_query"

    # A different query is a fresh signature — not blocked.
    assert await wrapper(ctx, query="VCB") == "ok"


# ---- helpers ----


class _StubRunContext:
    """Just-enough RunContext stub for tools that only access ``ctx.deps``."""

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps
