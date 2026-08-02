"""Pre-commit hook: agent-yaml ``call_tools([...])`` example args must match
each broker tool's parameter schema.

Catches the defect class behind the 2026-04-29 ``sector_enrichment.yaml``
incident: ``enrichment.get_block_trades`` is parameterless (signature
``async def get_block_trades() -> str``) but the YAML exemplar passed
``args={"tickers": tickers}`` — model retried with ``args={}`` after the
schema rejection and tripped the empty-args breaker.

Validation rules:
- Each ``{"name": X, "args": {...}}`` exemplar across every agent yaml must
  satisfy the JSON Schema declared for ``X`` in the live tool registry.
- Required keys must be present in ``args``.
- Unknown keys (not in the tool's ``properties``) are flagged as drift —
  they are silently stripped at runtime by ``validate_call`` but leak the
  wrong example into LLM context.
- Args whose values are bareword identifiers (``tickers``, ``today``) are
  treated as templated placeholders and skipped for type-checking — only
  presence/absence is enforced. Concrete literals (strings, numbers,
  booleans, lists) are type-checked against the property schema.

Args dict is parsed with a relaxed JSON loader: bare identifiers are
quoted before ``json.loads`` so the same exemplar string the LLM reads
parses without modification.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SCAN_PREFIX = "scripts/agents/configs/"
_CALL_ENTRY_RE = re.compile(
    r"""\{\s*["']name["']\s*:\s*["']([^"']+)["']\s*,\s*["']args["']\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})\s*\}""",
    re.DOTALL,
)
_LITERAL_KEYWORDS = {"true", "false", "null"}
# Tokenizer for the args payload. Order matters: strings first so we never
# attempt to bareword-rewrite identifiers nested inside quoted text.
_TOKEN_RE = re.compile(
    r"""
    (?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
    | (?P<ellipsis>\[\s*\.\.\.\s*\])
    | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)


def _load_tool_catalog() -> dict[str, dict[str, object]]:
    project_root = Path(__file__).parent.parent.parent
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import agents.tools.broker  # noqa: F401  # side-effect import populates registry
    from agents.tools.broker.registry import TOOL_CATALOG  # type: ignore[import-not-found]

    return {name: dict(td.parameters) for name, td in TOOL_CATALOG.items()}


def _normalize_args(args_text: str) -> str:
    """Token-walk the args payload and produce a JSON-loadable string.

    - Quoted strings pass through unchanged (single quotes → double quotes).
    - Bareword identifiers (placeholders like ``tickers``) → sentinel string.
    - ``[...]`` placeholders → ``["__placeholder__:list"]``.
    - JSON keywords (true/false/null) pass through untouched.
    """
    output: list[str] = []
    for match in _TOKEN_RE.finditer(args_text):
        kind = match.lastgroup
        token = match.group(0)
        if kind == "str":
            if token.startswith("'"):
                inner = token[1:-1].replace('"', '\\"')
                output.append(f'"{inner}"')
            else:
                output.append(token)
        elif kind == "ellipsis":
            output.append('["__placeholder__:list"]')
        elif kind == "word":
            if token in _LITERAL_KEYWORDS:
                output.append(token)
            else:
                output.append(f'"__placeholder__:{token}"')
        else:
            output.append(token)
    return "".join(output)


def _parse_args(args_text: str) -> dict[str, object] | None:
    candidate = args_text.strip()
    normalized = _normalize_args(candidate)
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _is_placeholder(value: object) -> bool:
    if isinstance(value, str) and value.startswith("__placeholder__:"):
        return True
    return isinstance(value, list) and value == ["__placeholder__:list"]


def _type_matches(value: object, schema: dict[str, object]) -> bool:
    expected = schema.get("type")
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _validate_call_entry(
    tool_name: str,
    args: dict[str, object],
    parameters: dict[str, object],
) -> list[str]:
    properties_raw = parameters.get("properties", {})
    properties: dict[str, object] = properties_raw if isinstance(properties_raw, dict) else {}
    required_raw = parameters.get("required", [])
    required: list[str] = list(required_raw) if isinstance(required_raw, list) else []
    errors: list[str] = []

    for required_key in required:
        if required_key not in args:
            errors.append(f"missing required arg `{required_key}`")

    for key, value in args.items():
        if key not in properties:
            errors.append(f"unknown arg `{key}` (not in tool schema)")
            continue
        prop_schema = properties[key]
        if not isinstance(prop_schema, dict):
            continue
        if _is_placeholder(value):
            continue
        # Placeholder lists like ``["__placeholder__:list"]`` count as arrays
        # for type checking; ``_is_placeholder`` short-circuits above before
        # we get here, so this only applies to concrete literals.
        if not _type_matches(value, prop_schema):
            errors.append(
                f"arg `{key}` type mismatch: expected {prop_schema.get('type')!r}, "
                f"got {type(value).__name__}"
            )
        # Enum check (string Literal types).
        enum_values = prop_schema.get("enum")
        if (
            isinstance(enum_values, list)
            and isinstance(value, (str, int, bool))
            and value not in enum_values
        ):
            errors.append(f"arg `{key}` value {value!r} not in allowed enum {enum_values!r}")

    if not properties and args:
        errors.append(
            f"tool `{tool_name}` is parameterless but exemplar passed args "
            f"{sorted(args.keys())!r} — use `args: {{}}`"
        )

    return errors


def _scan_file(
    path: Path,
    catalog: dict[str, dict[str, object]],
) -> list[tuple[str, int, str, list[str]]]:
    text = path.read_text()
    rel = str(path)
    violations: list[tuple[str, int, str, list[str]]] = []
    for match in _CALL_ENTRY_RE.finditer(text):
        tool_name = match.group(1)
        args_text = match.group(2)
        line_number = text.count("\n", 0, match.start()) + 1
        if tool_name not in catalog:
            violations.append(
                (rel, line_number, tool_name, [f"unknown tool `{tool_name}` (not in registry)"])
            )
            continue
        args = _parse_args(args_text)
        if args is None:
            violations.append(
                (rel, line_number, tool_name, [f"could not parse args text: {args_text!r}"])
            )
            continue
        errors = _validate_call_entry(tool_name, args, catalog[tool_name])
        if errors:
            violations.append((rel, line_number, tool_name, errors))
    return violations


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

    catalog = _load_tool_catalog()
    if not catalog:
        return 0

    all_violations: list[tuple[str, int, str, list[str]]] = []
    for path in targets:
        all_violations.extend(_scan_file(path, catalog))

    if not all_violations:
        return 0

    print(
        "Agent yaml `call_tools([...])` exemplar args must match each tool's "
        "parameter schema. The LLM copies the example verbatim — drift here "
        "produces ValidationError → empty-args breaker → tool loop "
        "(2026-04-29 sector_enrichment incident).",
        file=sys.stderr,
    )
    for rel, line_number, tool_name, errors in all_violations:
        for error in errors:
            print(f"  {rel}:{line_number}  tool={tool_name}  -> {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
