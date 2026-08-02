"""Tool broker registry — ToolDef, ToolDomain enum, catalog construction."""

import inspect
import json
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Literal, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ConfigDict, StringConstraints, validate_call

from ._errors import unknown_tool_error

logger = logging.getLogger(__name__)

ToolImpl = Callable[..., Coroutine[object, object, str]]


NonBlankToolName = Annotated[
    str,
    StringConstraints(min_length=1, strip_whitespace=True),
]


class CallEntry(BaseModel):
    """One entry in a ``call_tools`` batch.

    ``name`` carries ``min_length=1`` + ``strip_whitespace=True`` so the
    emitted JSON Schema rejects ``{"name":"","args":{}}`` at the pydantic-ai
    validation boundary — the 2026-04-24 broker audit showed 87% of
    ``broker_tool`` spans were noise from empty-name entries that the prior
    ``Required[str]`` TypedDict contract silently accepted.
    """

    model_config = ConfigDict(extra="forbid")
    name: NonBlankToolName
    args: dict


_PYTHON_TO_JSON_SCHEMA: dict[type, dict[str, str]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
}


class ToolDomain(str, Enum):
    """Valid tool domains. Used as enum in search_tools for LLM validation."""

    ALERT = "alert"
    ARTICLE = "article"
    BELIEF = "belief"
    COMPANY = "company"
    ENRICHMENT = "enrichment"
    FUNDAMENTAL = "fundamental"
    MARKET = "market"
    MEMORY = "memory"
    NARRATIVE = "narrative"
    PORTFOLIO = "portfolio"
    STATISTIC = "statistic"
    TECHNICAL = "technical"


@dataclass(frozen=True)
class ToolDef:
    """A tool definition in the broker registry."""

    name: str
    domain: ToolDomain
    description: str
    parameters: dict[str, object]
    implementation: ToolImpl
    context_keys: tuple[str, ...] = ()
    accepts_tickers: bool = False
    accepts_context: bool = False
    # Short (≤50 chars) hint describing the tool's return shape in LLM-friendly
    # terms (e.g., "dict[ticker → {rsi, macd, levels}]", "prose summary").
    # Rendered inline in the compact preamble listing after the description so
    # agents see the shape without a get_tool_schemas() round-trip. Empty
    # string means no hint is emitted.
    returns_hint: str = ""
    # Names of atomic tools this composite tool supersedes. Read by
    # `scripts/hooks/check_agent_yaml_composite_vs_atomic.py` to flag YAMLs
    # that issue imperative directives for both the composite and any of its
    # atomic components in the same prompt. Empty tuple = not a composite.
    supersedes: tuple[str, ...] = ()
    # True when the tool writes state (DB rows, outbound dispatch). Mutating tools
    # are reachable ONLY through a YAML `allowed_tools` entry — `unlock_tool` refuses
    # to admit them, so untrusted text in a prompt cannot talk an agent into a write.
    mutates: bool = False


TOOL_CATALOG: dict[str, ToolDef] = {}
DOMAIN_MAP: dict[ToolDomain, list[str]] = {domain: [] for domain in ToolDomain}


def _build_parameters_schema(
    func: ToolImpl, exclude_keys: frozenset[str] | None = None
) -> dict[str, object]:
    """Build JSON Schema from function signature, excluding internal params."""
    exclude = exclude_keys or frozenset({"_ctx"})
    sig = inspect.signature(func)
    properties: dict[str, object] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in exclude:
            continue

        annotation = param.annotation
        prop: dict[str, object] = _resolve_type_schema(annotation)

        is_optional = hasattr(annotation, "__args__") and type(None) in getattr(
            annotation, "__args__", ()
        )
        if not is_optional and param.default is inspect.Parameter.empty:
            required.append(param_name)

        properties[param_name] = prop

    schema: dict[str, object] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _resolve_type_schema(annotation: object) -> dict[str, object]:
    """Map a Python type annotation to a JSON Schema dict.

    Handles: primitives, list[X] (with recursion for nested types),
    Union[X, None], Literal[...], and TypedDict classes.
    """
    if annotation in _PYTHON_TO_JSON_SCHEMA:
        return dict(_PYTHON_TO_JSON_SCHEMA[annotation])  # type: ignore[arg-type]

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Literal:
        values = list(args)
        if all(isinstance(v, str) for v in values):
            return {"type": "string", "enum": values}
        if all(isinstance(v, bool) for v in values):
            return {"type": "boolean", "enum": values}
        if all(isinstance(v, int) for v in values):
            return {"type": "integer", "enum": values}
        return {"type": "string", "enum": [str(v) for v in values]}

    if origin is list:
        item_annotation = args[0] if args else str
        return {"type": "array", "items": _resolve_type_schema(item_annotation)}

    non_none = [a for a in args if a is not type(None)] if args else []
    if non_none:
        return _resolve_type_schema(non_none[0])

    # TypedDict detection — class with __required_keys__/__optional_keys__
    if hasattr(annotation, "__required_keys__") and hasattr(annotation, "__optional_keys__"):
        hints = get_type_hints(annotation)  # type: ignore[arg-type]
        properties: dict[str, object] = {
            key: _resolve_type_schema(hint) for key, hint in hints.items()
        }
        schema: dict[str, object] = {"type": "object", "properties": properties}
        # __required_keys__ is a frozenset — sort so JSON Schema output is
        # deterministic across process restarts (PYTHONHASHSEED randomization).
        required = sorted(getattr(annotation, "__required_keys__", ()))
        if required:
            schema["required"] = required
        return schema

    return {"type": "string"}


def _has_ctx_param(func: ToolImpl) -> bool:
    """Check if function signature has a _ctx parameter."""
    return "_ctx" in inspect.signature(func).parameters


def register_domain_tool(
    name: str,
    domain: ToolDomain,
    implementation: ToolImpl,
    *,
    context_keys: tuple[str, ...] = (),
    accepts_tickers: bool = False,
    description: str | None = None,
    parameters: dict[str, object] | None = None,
    returns_hint: str = "",
    supersedes: tuple[str, ...] = (),
    mutates: bool = False,
) -> None:
    """Register a tool in the global catalog.

    `supersedes` names atomic tools a composite tool replaces. Used by
    the composite-vs-atomic pre-commit hook to flag YAMLs that still issue
    imperative directives for the atomic forms when a composite exists.
    """
    tool_description = description or (implementation.__doc__ or "").strip()
    if not tool_description:
        tool_description = f"Tool {name}"

    # Build the parameter schema from the RAW implementation so inspection
    # sees the original signature before any validate_call wrapping.
    tool_parameters = parameters or _build_parameters_schema(implementation)
    needs_context = bool(context_keys) or _has_ctx_param(implementation)

    # Wrap the implementation in `pydantic.validate_call` so every broker
    # tool gets runtime validation of its kwargs. Python `Literal[...]`
    # type hints are type-hints-only at runtime; without this wrapper,
    # `portfolio.get_learnings` could be called with a free-text query that
    # silently failed at the SQL layer. Class-level fix covers every tool
    # with a Literal / TypedDict / nested constraint in its signature.
    validated_impl: ToolImpl = validate_call(
        implementation, config={"arbitrary_types_allowed": True}
    )  # type: ignore[assignment]

    tool_def = ToolDef(
        name=name,
        domain=domain,
        description=tool_description,
        parameters=tool_parameters,
        implementation=validated_impl,
        context_keys=context_keys,
        accepts_tickers=accepts_tickers,
        accepts_context=needs_context,
        returns_hint=returns_hint,
        supersedes=supersedes,
        mutates=mutates,
    )

    if name in TOOL_CATALOG:
        logger.warning("Duplicate tool registration: %s (overwriting)", name)
        DOMAIN_MAP[domain] = [n for n in DOMAIN_MAP[domain] if n != name]

    TOOL_CATALOG[name] = tool_def
    DOMAIN_MAP[domain].append(name)


def get_tools_by_domain(domain: ToolDomain) -> list[ToolDef]:
    """Get all tools in a domain."""
    return [TOOL_CATALOG[name] for name in DOMAIN_MAP.get(domain, []) if name in TOOL_CATALOG]


def get_tool(name: str) -> ToolDef | None:
    """Get a tool by its full dotted name."""
    return TOOL_CATALOG.get(name)


def _compact_description(description: str, max_chars: int = 100) -> str:
    """Trim description to first sentence / line, hard-capped at max_chars."""
    first_line = description.strip().split("\n", 1)[0]
    first_sentence = first_line.split(". ", 1)[0]
    if len(first_sentence) > max_chars:
        return first_sentence[: max_chars - 1].rstrip() + "…"
    return first_sentence


def format_tool_listing(
    domains: list[ToolDomain] | None = None,
    *,
    compact: bool = False,
) -> str:
    """Format tool catalog for LLM consumption.

    compact=True trims descriptions to first sentence for use in the prompt
    preamble (space-sensitive). compact=False returns full descriptions for
    search_tools responses where the LLM is actively looking for detail.
    """
    target_domains = domains or list(ToolDomain)
    lines: list[str] = []

    for domain in target_domains:
        tools = get_tools_by_domain(domain)
        if not tools:
            continue
        lines.append(f"\n## {domain.value}")
        for tool in tools:
            params = tool.parameters.get("properties", {})
            param_names = ", ".join(params.keys()) if isinstance(params, dict) else ""
            description = _compact_description(tool.description) if compact else tool.description
            hint_suffix = f" → {tool.returns_hint}" if compact and tool.returns_hint else ""
            lines.append(f"- {tool.name}({param_names}) — {description}{hint_suffix}")

    return "\n".join(lines)


def format_tool_schemas(names: list[str]) -> str:
    """Format JSON schemas for requested tools."""
    results: dict[str, object] = {}
    for name in names:
        tool = get_tool(name)
        if tool:
            results[name] = {
                "description": tool.description,
                "parameters": tool.parameters,
                "returns": tool.returns_hint or None,
            }
        else:
            results[name] = unknown_tool_error(name)
    return json.dumps(results, indent=2)
