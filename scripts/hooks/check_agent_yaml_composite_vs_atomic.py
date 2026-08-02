"""Pre-commit hook: agent-yaml tool-surface contract.

Blocks three config-drift failure classes at the YAML boundary:

1. **Composite + atomic coexistence (2026-04-24).** An agent YAML that
   imperatively tells the LLM to `call_tools` the composite (e.g.
   `fundamental.get_full_analysis`) AND the atomic tools it supersedes
   (e.g. `fundamental.get_valuation_history`,
   `fundamental.get_earnings_quality`). The model oscillates and burns
   through `request_limit` in a rapid-fire tool loop.

2. **Atomic tool without batch exemplar (2026-04-25).** Any atomic tool
   referenced in an imperative line MUST appear inside a `call_tools([...])`
   exemplar in the same file. Otherwise GLM-5 oscillates between atomic
   and composite call paths. Same class as `e0d35a4d` positions_value
   fix; `sector_enrichment.yaml` was the 2026-04-24 recurrence.

3. **Tool-using agent without bounded request_limit (2026-04-25).** Any
   config that imperatively references any broker tool MUST set
   `request_limit: N` with `N ≤ 15`. The default 30 is too loose for
   tool-using agents and invites `UsageLimitExceeded` → empty belief →
   silent coverage gap.

Composite↔atomic relationship is sourced from `register_domain_tool(...,
supersedes=(...))` in the tool registry — no stale table to maintain.

Imperative directive = any line with the atomic tool name AND one of:
  `batch-call`, `call`, `start from`, `prefer`, `run`, `use` (case-insensitive).
Bare references inside a `call_tools([...])` exemplar are skipped.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCAN_PREFIX = "scripts/agents/configs/"
_IMPERATIVE_TOKENS = (
    "batch-call",
    "call ",
    "start from",
    "prefer ",
    "run ",
    "use ",
)
_REQUEST_LIMIT_MAX = 15
_REQUEST_LIMIT_RE = re.compile(r"^request_limit\s*:\s*(\d+)\s*$", re.MULTILINE)
_CALL_TOOLS_NAME_RE = re.compile(r"""["']name["']\s*:\s*["']([^"']+)["']""")


def _load_tool_catalog() -> tuple[dict[str, tuple[str, ...]], set[str]]:
    """Return (supersedes_map, all_tool_names) from the live tool registry."""
    project_root = Path(__file__).parent.parent.parent
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    # Importing the broker package runs its `__init__.py`, which side-effect-
    # imports every domain module via `from . import domains as _domains`.
    # After that, TOOL_CATALOG in the registry submodule is fully populated.
    import agents.tools.broker  # noqa: F401  # side-effect import
    from agents.tools.broker.registry import TOOL_CATALOG  # type: ignore[import-not-found]

    supersedes_map = {
        tool.name: tool.supersedes for tool in TOOL_CATALOG.values() if tool.supersedes
    }
    all_names = {tool.name for tool in TOOL_CATALOG.values()}
    return supersedes_map, all_names


def _tool_name_present(line_lower: str, tool_name_lower: str) -> bool:
    """True when `tool_name` appears in `line` as a standalone identifier.

    Requires a non-identifier boundary on both sides so `get_valuation` does
    not falsely match inside `get_valuation_history`.
    """
    start = 0
    name_len = len(tool_name_lower)
    while True:
        idx = line_lower.find(tool_name_lower, start)
        if idx < 0:
            return False
        before = line_lower[idx - 1] if idx > 0 else ""
        after_pos = idx + name_len
        after = line_lower[after_pos] if after_pos < len(line_lower) else ""
        if not (before.isalnum() or before == "_") and not (
            after.isalnum() or after == "_" or after == "."
        ):
            return True
        start = idx + 1


def _is_imperative_directive(line_lower: str, tool_name_lower: str) -> bool:
    """True when `line` imperatively tells the LLM to use `tool_name`."""
    if not _tool_name_present(line_lower, tool_name_lower):
        return False
    # Inline exemplar inside a `call_tools([{"name": ...}])` block is allowed.
    if '"name":' in line_lower or "'name':" in line_lower:
        return False
    return any(token in line_lower for token in _IMPERATIVE_TOKENS)


def _extract_call_tools_names(text: str) -> set[str]:
    """Return the set of tool names mentioned inside `call_tools([...])` exemplars."""
    return set(_CALL_TOOLS_NAME_RE.findall(text))


def _extract_request_limit(text: str) -> int | None:
    """Return the top-level `request_limit:` integer from the YAML, if present."""
    match = _REQUEST_LIMIT_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _check_composite_vs_atomic(
    relative_path: str,
    lines: list[str],
    supersedes_map: dict[str, tuple[str, ...]],
) -> list[tuple[str, int, str, str, str]]:
    """Return (path, line, composite, atomic, snippet) violations."""
    composite_lowers = {composite: composite.lower() for composite in supersedes_map}
    atomic_to_composite: dict[str, str] = {
        atomic: composite for composite, atomics in supersedes_map.items() for atomic in atomics
    }
    atomic_lowers = {atomic: atomic.lower() for atomic in atomic_to_composite}

    composite_seen: set[str] = set()
    atomic_hits: list[tuple[int, str, str]] = []

    for line_number, line in enumerate(lines, start=1):
        line_lower = line.lower()
        for composite, composite_lower in composite_lowers.items():
            if _is_imperative_directive(line_lower, composite_lower):
                composite_seen.add(composite)
        for atomic, atomic_lower in atomic_lowers.items():
            if _is_imperative_directive(line_lower, atomic_lower):
                atomic_hits.append((line_number, atomic, line.strip()))

    return [
        (relative_path, line_number, atomic_to_composite[atomic], atomic, text)
        for line_number, atomic, text in atomic_hits
        if atomic_to_composite[atomic] in composite_seen
    ]


def _collect_imperative_tool_refs(
    lines: list[str],
    all_tool_names: set[str],
) -> list[tuple[int, str, str]]:
    """Return (line_number, tool_name, snippet) for every imperative tool mention."""
    tool_lowers = {tool: tool.lower() for tool in all_tool_names}
    hits: list[tuple[int, str, str]] = []
    for line_number, line in enumerate(lines, start=1):
        line_lower = line.lower()
        for tool, tool_lower in tool_lowers.items():
            if _is_imperative_directive(line_lower, tool_lower):
                hits.append((line_number, tool, line.strip()))
    return hits


def _check_batch_exemplar(
    relative_path: str,
    text: str,
    imperative_refs: list[tuple[int, str, str]],
) -> list[tuple[str, int, str, str]]:
    """Return (path, line, tool, snippet) for imperative refs missing a batch exemplar."""
    exemplar_names = _extract_call_tools_names(text)
    return [
        (relative_path, line_number, tool, snippet)
        for line_number, tool, snippet in imperative_refs
        if tool not in exemplar_names
    ]


def _check_request_limit(
    relative_path: str,
    text: str,
    has_tool_refs: bool,
) -> tuple[str, int | None, str] | None:
    """Return (path, limit_or_none, reason) when the request_limit contract fails."""
    if not has_tool_refs:
        return None
    limit = _extract_request_limit(text)
    if limit is None:
        return (relative_path, None, "missing `request_limit:` (default 30 is too loose)")
    if limit > _REQUEST_LIMIT_MAX:
        return (relative_path, limit, f"request_limit={limit} > max {_REQUEST_LIMIT_MAX}")
    return None


def main(argv: list[str]) -> int:
    targets: list[Path] = []
    for raw in argv[1:]:
        if not raw.startswith(_SCAN_PREFIX):
            continue
        path = Path(raw)
        if path.suffix not in {".yaml", ".yml"}:
            continue
        if not path.is_file():
            continue
        targets.append(path)
    if not targets:
        return 0

    supersedes_map, all_tool_names = _load_tool_catalog()
    if not all_tool_names:
        return 0

    composite_violations: list[tuple[str, int, str, str, str]] = []
    exemplar_violations: list[tuple[str, int, str, str]] = []
    request_limit_violations: list[tuple[str, int | None, str]] = []

    for path in targets:
        text = path.read_text()
        lines = text.splitlines()
        relative = str(path)

        if supersedes_map:
            composite_violations.extend(_check_composite_vs_atomic(relative, lines, supersedes_map))

        imperative_refs = _collect_imperative_tool_refs(lines, all_tool_names)
        exemplar_violations.extend(_check_batch_exemplar(relative, text, imperative_refs))

        limit_violation = _check_request_limit(relative, text, bool(imperative_refs))
        if limit_violation is not None:
            request_limit_violations.append(limit_violation)

    if not (composite_violations or exemplar_violations or request_limit_violations):
        return 0

    if composite_violations:
        print(
            "Composite + atomic tool directives coexist in the same YAML. "
            "This provokes LLM tool-call loops (see 2026-04-24 daily-scan "
            "failure). Rewrite the atomic directives to read from the "
            "composite's returned sections instead.",
            file=sys.stderr,
        )
        for rel, line_number, composite, atomic, snippet in composite_violations:
            print(
                f"  {rel}:{line_number}  composite={composite}  atomic={atomic}  -> {snippet}",
                file=sys.stderr,
            )

    if exemplar_violations:
        print(
            "Atomic tool imperatively invoked without a `call_tools([...])` "
            "batch exemplar in the same file. Add a batch block that lists "
            "the tool by name, or remove the imperative directive.",
            file=sys.stderr,
        )
        for rel, line_number, tool, snippet in exemplar_violations:
            print(
                f"  {rel}:{line_number}  tool={tool}  -> {snippet}",
                file=sys.stderr,
            )

    if request_limit_violations:
        print(
            "Tool-using agent YAML must set `request_limit: N` with "
            f"N <= {_REQUEST_LIMIT_MAX}. The default 30 is too loose and "
            "invites UsageLimitExceeded + silent coverage gaps.",
            file=sys.stderr,
        )
        for rel, _limit, reason in request_limit_violations:
            print(f"  {rel}  {reason}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
