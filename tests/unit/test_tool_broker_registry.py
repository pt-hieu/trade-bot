"""Unit tests for tool broker — registry."""

import json

from tests.unit._fixtures.tool_broker import _run_coro


class TestToolDomain:
    """Test ToolDomain enum validation."""

    def test_all_domains_present(self):
        from agents.tools.broker.registry import ToolDomain

        assert len(ToolDomain) == 12
        expected = {
            "alert",
            "article",
            "belief",
            "company",
            "enrichment",
            "fundamental",
            "market",
            "memory",
            "narrative",
            "portfolio",
            "statistic",
            "technical",
        }
        assert {d.value for d in ToolDomain} == expected

    def test_domain_is_str_enum(self):
        from agents.tools.broker.registry import ToolDomain

        assert isinstance(ToolDomain.FUNDAMENTAL, str)
        assert ToolDomain.FUNDAMENTAL == "fundamental"


class TestToolRegistry:
    """Test tool registration and catalog."""

    def test_all_45_tools_registered(self):
        from agents.tools.broker.registry import TOOL_CATALOG

        # 44 original tools + fundamental.get_full_analysis composite (2026-04-12)
        assert len(TOOL_CATALOG) == 45

    def test_domain_map_populated(self):
        from agents.tools.broker.registry import DOMAIN_MAP, ToolDomain

        # Every domain should have at least 1 tool
        for domain in ToolDomain:
            assert len(DOMAIN_MAP[domain]) >= 1, f"Domain {domain.value} has no tools"

    def test_tool_names_follow_convention(self):
        from agents.tools.broker.registry import TOOL_CATALOG

        for name in TOOL_CATALOG:
            parts = name.split(".")
            assert len(parts) == 2, f"Tool {name} doesn't follow domain.verb_noun pattern"
            domain_part, action_part = parts
            assert domain_part, f"Tool {name} has empty domain"
            assert action_part, f"Tool {name} has empty action"

    def test_tool_def_has_required_fields(self):
        from agents.tools.broker.registry import TOOL_CATALOG

        for name, tool_def in TOOL_CATALOG.items():
            assert tool_def.name == name
            assert tool_def.domain is not None
            assert tool_def.description
            assert tool_def.parameters is not None
            assert tool_def.implementation is not None

    def test_get_tool_found(self):
        from agents.tools.broker.registry import get_tool

        tool = get_tool("fundamental.get_valuation")
        assert tool is not None
        assert tool.name == "fundamental.get_valuation"

    def test_get_tool_not_found(self):
        from agents.tools.broker.registry import get_tool

        assert get_tool("nonexistent.tool") is None

    def test_get_tools_by_domain(self):
        from agents.tools.broker.registry import ToolDomain, get_tools_by_domain

        tools = get_tools_by_domain(ToolDomain.ALERT)
        assert len(tools) == 4
        assert all(t.domain == ToolDomain.ALERT for t in tools)

    def test_format_tool_listing(self):
        from agents.tools.broker.registry import ToolDomain, format_tool_listing

        listing = format_tool_listing([ToolDomain.TECHNICAL])
        assert "technical.get_technicals" in listing
        assert "technical.calculate_trade_setup" in listing
        assert "fundamental" not in listing

    def test_format_tool_schemas(self):
        from agents.tools.broker.registry import format_tool_schemas

        result = json.loads(format_tool_schemas(["technical.get_technicals", "nonexistent.tool"]))
        assert "technical.get_technicals" in result
        assert "parameters" in result["technical.get_technicals"]
        assert "error" in result["nonexistent.tool"]


class TestContextDriftRegression:
    """T07: guard against bare tool names re-entering context_blocks / yaml configs.

    Bare names like `search` / `get_learnings` train the model to drop the
    domain prefix; they should only appear as fully-qualified `domain.verb`
    references (e.g. `article.search`, `portfolio.get_learnings`) OR inside
    `call_tools([...])` syntax examples.
    """

    def test_no_bare_tool_names_in_context_blocks_or_configs(self):
        import re
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        search_paths = [
            repo_root / "scripts" / "pipeline",
            repo_root / "scripts" / "agents" / "configs",
        ]
        target_files: list[Path] = []
        for path in search_paths:
            target_files.extend(path.glob("context_blocks*.py"))
            target_files.extend(path.glob("*.yaml"))

        # Qualified prefixes that should always appear before these tokens.
        qualified_prefix_pattern = re.compile(
            r"(?:article|portfolio|narrative|enrichment|fundamental|technical|"
            r"market|statistic|belief|memory|alert|company)\."
        )
        bare_token_pattern = re.compile(
            r"\b(search_articles|get_learnings|get_active_narratives|"
            r"position_scale|read_article|get_holdings|get_catalyst_preview|"
            r"get_relative_strength|get_belief_accuracy|get_rotation|"
            r"get_sector_data|get_ticker_data)\b"
        )

        offenses: list[tuple[str, int, str]] = []
        for file_path in target_files:
            is_python = file_path.suffix == ".py"
            for line_num, line in enumerate(file_path.read_text().splitlines(), start=1):
                for match in bare_token_pattern.finditer(line):
                    # Extract a small window around the match to check for a
                    # fully-qualified prefix ending in ".".
                    start = max(0, match.start() - 20)
                    window = line[start : match.end()]
                    if qualified_prefix_pattern.search(window):
                        continue
                    if "call_tools" in line:
                        continue
                    # In Python files only flag matches inside string literals —
                    # plain identifier sites (imports, function calls) don't
                    # reach the model. Heuristic: odd number of quote chars
                    # before the match position means we're inside a string.
                    if is_python:
                        prefix = line[: match.start()]
                        quote_count = prefix.count('"') + prefix.count("'")
                        if quote_count % 2 == 0:
                            continue
                    offenses.append((str(file_path.relative_to(repo_root)), line_num, line.strip()))

        assert not offenses, (
            "Bare tool-name references found (T07 drift scrub regression):\n"
            + "\n".join(f"  {f}:{n}: {t}" for f, n, t in offenses)
        )


class TestSharedToolCache:
    """P1b: cross-agent `_tool_cache` sharing within a pipeline run.

    Post-SWI-180: AgentDeps owns `tool_cache`; brokers no longer wrap context.
    These tests verify that `cached_tool_call` operates on whatever dict is
    handed in (so two AgentDeps instances pre-seeded with the same dict still
    share state).
    """

    def test_shared_dict_visible_across_consumers(self):
        shared: dict = {"k": "preseeded"}
        a = {"_tool_cache": shared}
        b = {"_tool_cache": shared}
        a["_tool_cache"]["new_key"] = "written-by-a"
        assert b["_tool_cache"]["new_key"] == "written-by-a"

    def test_cached_tool_call_hits_on_second_invocation(self):
        """cached_tool_call returns the stored value without invoking factory on hit."""
        from agents.tools.broker.helpers import cached_tool_call

        shared: dict = {}
        call_count = 0

        async def _coro():
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        first = _run_coro(cached_tool_call(shared, "k", _coro))
        assert first == "result-1"
        assert call_count == 1

        second = _run_coro(cached_tool_call(shared, "k", _coro))
        assert second == "result-1"
        assert call_count == 1
