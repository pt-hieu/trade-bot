"""Pre-commit hook: pre-loaded claim vs imperative tool directive.

Combines two layers of coherence enforcement:

1. **Lexical (legacy)** — when ``system_prompt`` advertises pre-loaded data
   ("pre-loaded", "pre-injected", "inline in", …) but later issues an
   unconditional imperative ``Call <tool>`` / ``Run <tool>``, fail. This
   blocks the original 2026-04-24 positions_thesis loop where the YAML's
   "Start from portfolio.get_thesis" contradicted the inject-first claim.

2. **Structured (registry)** — when an agent YAML declares an explicit
   ``injected_fields:`` list, every entry must resolve to a key in
   ``pipeline.context_block_registry.OUTPUT_KEY_REGISTRY``. This catches the
   2026-04-28 case the lexical check missed: a YAML claiming "thesis pillars
   are pre-injected" when no formatter ever rendered them, leaving the LLM
   with a permanently-true conditional escape hatch into ``call_tools``.

Free-text "pre-loaded" claims still get scanned lexically. They WARN (not
fail) when the structured ``injected_fields:`` list is absent — the agent may
genuinely rely on prose context. Authors who want stronger guarantees move
their claims into ``injected_fields:`` and earn the structured check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

_SCAN_PREFIX = "scripts/agents/configs/"
# "pre-loaded above" / "inline with" are supersets of "pre-loaded" / "inline in"
# — keep only the shortest substring of each family.
_PRELOADED_TOKENS = (
    "pre-loaded",
    "pre-injected",
    " preloaded",
    " injected data",
    "inline in",
    "visible inline",
)
_IMPERATIVE_VERBS = (
    "start from ",
    "batch-call ",
    "batch call ",
    "call ",
    "run ",
)
_CONDITIONAL_TOKENS = ("when ", "if ", "only when ", "unless ")


def _build_tool_name_pattern() -> re.Pattern[str]:
    """Derive the tool-name regex from the live ``ToolDomain`` enum so a new
    domain is picked up automatically. Fall back to a hard-coded list only if
    the registry module cannot be imported (e.g. when the hook runs in a
    minimal environment)."""
    project_root = Path(__file__).parent.parent.parent
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from agents.tools.broker.registry import (  # type: ignore[import-not-found]
            ToolDomain,
        )

        domains = "|".join(domain.value for domain in ToolDomain)
    except Exception:
        domains = (
            "portfolio|fundamental|technical|article|enrichment|belief|"
            "narrative|market|memory|company|statistic|alert"
        )
    return re.compile(rf"\b({domains})\.[a-z_]+\b")


_TOOL_NAME_PATTERN = _build_tool_name_pattern()


def _claims_preloaded(header: str) -> bool:
    lower = header.lower()
    return any(token in lower for token in _PRELOADED_TOKENS)


def _is_conditional(line: str) -> bool:
    stripped = line.lstrip(" -*\t").lower()
    return any(stripped.startswith(token) for token in _CONDITIONAL_TOKENS)


def _is_call_tools_exemplar(line: str) -> bool:
    """Tool-name inside a ``call_tools([{...}])`` exemplar is OK."""
    return '"name":' in line or "'name':" in line


def _find_violations(prompt: str) -> list[tuple[int, str, str]]:
    """Return ``(line_number, tool_name, snippet)`` lexical violations."""
    lines = prompt.splitlines()
    header = "\n".join(lines[:40])
    if not _claims_preloaded(header):
        return []
    violations: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines, start=1):
        if _is_call_tools_exemplar(line):
            continue
        lower = line.lower()
        if not any(verb in lower for verb in _IMPERATIVE_VERBS):
            continue
        match = _TOOL_NAME_PATTERN.search(line)
        if not match:
            continue
        if _is_conditional(line):
            continue
        violations.append((index, match.group(0), line.strip()))
    return violations


def _load_known_keys() -> set[str]:
    """Resolve the registry's known output keys, with a graceful fallback.

    The hook may run in a minimal environment without the full project on
    sys.path. When the registry import fails, the structured check is
    skipped silently and the lexical layer still runs.
    """
    try:
        from pipeline.context_block_registry import (  # type: ignore[import-not-found]
            known_output_keys,
        )

        return known_output_keys()
    except Exception:
        return set()


def _check_injected_fields(
    data: dict, known_keys: set[str], relative_path: str
) -> list[tuple[str, int, str, str]]:
    """Validate the optional ``injected_fields:`` list against the registry.

    YAML schema::

        injected_fields:
          - thesis.pillars
          - valuation.current

    Each entry must resolve to a key in ``OUTPUT_KEY_REGISTRY``. Unknown keys
    fail the hook with a structured error referencing the missing identifier.
    """
    raw = data.get("injected_fields")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [
            (
                relative_path,
                0,
                "",
                "injected_fields: must be a YAML list of dot-path strings",
            )
        ]
    if not known_keys:
        # Registry unavailable in this environment — silently skip structural
        # check rather than false-failing.
        return []
    failures: list[tuple[str, int, str, str]] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            failures.append(
                (
                    relative_path,
                    0,
                    "",
                    f"injected_fields entry must be a non-empty string, got {entry!r}",
                )
            )
            continue
        key = entry.strip()
        if key not in known_keys:
            failures.append(
                (
                    relative_path,
                    0,
                    key,
                    f"injected_fields entry '{key}' is not in OUTPUT_KEY_REGISTRY — "
                    "register a formatter for it in scripts/pipeline/context_block_registry.py "
                    "or remove the claim",
                )
            )
    return failures


def _check_yaml(
    path: Path, relative_path: str, known_keys: set[str]
) -> list[tuple[str, int, str, str]]:
    try:
        with path.open() as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        print(f"{relative_path}: YAML parse error: {error}", file=sys.stderr)
        return [(relative_path, 0, "", f"YAML parse error: {error}")]
    if not isinstance(data, dict):
        return []

    failures: list[tuple[str, int, str, str]] = []
    failures.extend(_check_injected_fields(data, known_keys, relative_path))

    prompt = data.get("system_prompt")
    if isinstance(prompt, str):
        failures.extend(
            (relative_path, line_number, tool_name, snippet)
            for line_number, tool_name, snippet in _find_violations(prompt)
        )
    return failures


def main(argv: list[str]) -> int:
    targets: list[Path] = []
    for raw in argv[1:]:
        if not raw.startswith(_SCAN_PREFIX):
            continue
        path = Path(raw)
        if path.suffix not in {".yaml", ".yml"}:
            continue
        if path.name.startswith("_"):
            continue  # skip fragment files
        if not path.is_file():
            continue
        targets.append(path)
    if not targets:
        return 0

    known_keys = _load_known_keys()
    all_violations: list[tuple[str, int, str, str]] = []
    for path in targets:
        all_violations.extend(_check_yaml(path, str(path), known_keys))

    if all_violations:
        print(
            "Injection-coherence violation. Either: (a) the YAML claims data is "
            "pre-loaded but issues an unconditional imperative tool directive "
            "(convert to a conditional or remove the preloaded claim), OR "
            "(b) the YAML's `injected_fields:` lists a key with no matching "
            "formatter in scripts/pipeline/context_block_registry.py.",
            file=sys.stderr,
        )
        for rel, line_number, tool_name, snippet in all_violations:
            location = f"{rel}:{line_number}" if line_number else rel
            tag = f"  tool={tool_name}" if tool_name else ""
            print(f"  {location}{tag}  -> {snippet}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
