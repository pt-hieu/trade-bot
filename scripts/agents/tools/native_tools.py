"""Native PydanticAI tool registration — replaces the broker meta-tool layer.

The broker registry's `TOOL_CATALOG` is the source of truth for tool
definitions. This module wires each `ToolDef` into a `pydantic_ai.Tool`
with two key constraints:

1. The original parameter signature (modulo `_ctx`) is preserved on the
   wrapper so pydantic-ai schema-generates the JSON Schema agents see — per
   Stage 0 verification, this is what makes the `Literal[...]` enums and
   the `Annotated[list[str], Len(min_length=1)]` constraint reach the model
   boundary, where they were previously hidden inside `call_tools`'s opaque
   `args: dict`.
2. `_wrap_with_policy` adds three concerns around the tool body:
   - `broker_tool` Logfire span (preserves the existing
     `scripts/collect_review_data.py:443-551` `broker_tool_usage` pivot);
   - per-run `iteration_count` + `BrokerLoopBreaker(kind="iteration_limit")`
     past `NATIVE_TOOL_INVOCATION_LIMIT`;
   - `error_signature` retry breaker on repeated `(tool, error_type)` pairs.

There is no autofill in this module — the model is expected to emit valid
args, and pydantic-ai's `retries=2` covers self-correction. Per Stage 0
finding A (empty-list bypass), the `Annotated[list[str], Len(min_length=1)]`
sweep makes empty-list emissions a schema rejection equivalent to a
missing key.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import ValidationError
from pydantic_ai import RunContext, Tool
from pydantic_ai.exceptions import ModelRetry, UnexpectedModelBehavior
from pydantic_ai.tools import ToolDefinition

from shared.observability import span as logfire_span

from .agent_deps import AgentDeps, deps_to_ctx_dict
from .broker._errors import unknown_tool_error
from .broker.error_hints import classify_validation_error
from .broker.registry import TOOL_CATALOG, ToolDef, get_tool

__all__ = [
    "AgentDeps",
    "BrokerLoopBreaker",
    "ERROR_SIGNATURE_RETRY_LIMIT",
    "NATIVE_TOOL_INVOCATION_LIMIT",
    "TOTAL_TOOL_BUDGET",
    "build_native_tools",
    "make_prepare_tools",
    "render_catalog",
    "unlock_tool",
]

logger = logging.getLogger(__name__)


# Renamed from CALL_TOOLS_ITERATION_LIMIT (10). Recalibrated to 25 because
# native registration removes the prose-batch-of-N pattern; each tool call is
# a single invocation, so the bound now counts tool calls rather than batches.
# 25 ≈ 3× the healthy hot-set ceiling (sector_enrichment averaged ~8 calls/run
# pre-cutover) and well below the per-agent `request_limit` of 30.
NATIVE_TOOL_INVOCATION_LIMIT = 25

# Per-(tool, error_type) retry budget. After this many identical-class
# failures the wrapper raises `BrokerLoopBreaker` so the loop short-circuits
# before the agent's `request_limit` is exhausted.
ERROR_SIGNATURE_RETRY_LIMIT = 2

# SWI-86: max identical (tool, args) calls in one run before the wrapper
# short-circuits. The global NATIVE_TOOL_INVOCATION_LIMIT already prevents
# runaway loops; this is a budget-efficiency guard — repeating the same query
# returns the same result, so burning the invocation budget on duplicates is
# wasted work, not a crash risk.
DUPLICATE_CALL_LIMIT = 3

# Hard cap on total visible tool surface (allowed_tools + unlocked + unlock_tool).
# Per agent-development skill: agents thrash above ~15 visible tools.
TOTAL_TOOL_BUDGET = 15


BreakerKind = Literal[
    "iteration_limit",
    "error_signature",
    "unlock_overuse",
    "duplicate_query",
]


class BrokerLoopBreaker(UnexpectedModelBehavior):
    """Raised when an agent loop is unrecoverable by pydantic-ai's retry path.

    breaker_kind values:
      - iteration_limit: per-run tool-call count exceeded `NATIVE_TOOL_INVOCATION_LIMIT`.
      - error_signature: same `(tool, error_type)` failed past
        `ERROR_SIGNATURE_RETRY_LIMIT`. Bad-args signature is deterministic —
        a third attempt is guaranteed to fail the same way.
      - unlock_overuse: agent called `unlock_tool` past its budget; the visible
        surface is already exhausted of useful candidates.
    """

    def __init__(self, message: str, breaker_kind: BreakerKind) -> None:
        super().__init__(message)
        self.breaker_kind: BreakerKind = breaker_kind


def _bump_error_signature(deps: AgentDeps, tool_name: str, error_type: str, hint: str) -> None:
    counts = deps.error_signature_counts
    key = f"{tool_name}::{error_type}"
    counts[key] = (counts.get(key) or 0) + 1
    if counts[key] >= ERROR_SIGNATURE_RETRY_LIMIT:
        with logfire_span(
            "error_signature_breaker",
            tool_name=tool_name,
            error_type=error_type,
            failure_count=counts[key],
        ):
            raise BrokerLoopBreaker(
                f"Tool {tool_name} failed with {error_type} {counts[key]} times "
                f"in a row. {hint} Stop calling this tool and produce the final "
                "structured output from the data already in your context.",
                breaker_kind="error_signature",
            )


def _build_wrapper_signature(impl_sig: inspect.Signature) -> inspect.Signature:
    """Clone the implementation's signature, drop `_ctx`, prepend `ctx: RunContext`.

    Pydantic-ai inspects the wrapper's signature to build the JSON Schema the
    model sees. The original `_ctx` parameter is internal-only and is removed;
    `ctx: RunContext[AgentDeps]` is added as the first positional parameter so
    `Tool(takes_ctx=True)` recognises the wrapper.
    """
    public_params = [p for name, p in impl_sig.parameters.items() if name != "_ctx"]
    ctx_param = inspect.Parameter(
        "ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=RunContext[AgentDeps]
    )
    return inspect.Signature(parameters=[ctx_param, *public_params], return_annotation=str)


def _wrap_with_policy(tool_def: ToolDef) -> Callable[..., Awaitable[str]]:
    """Wrap a `ToolDef` as a native pydantic-ai tool callable with policy
    middleware: iteration breaker, broker_tool span, error_signature breaker.
    """
    name = tool_def.name
    impl = tool_def.implementation  # already validate_call-wrapped via register_domain_tool
    needs_ctx = tool_def.accepts_context

    async def wrapper(ctx: RunContext[AgentDeps], **kwargs: object) -> str:
        deps = ctx.deps
        deps.iteration_count += 1
        if deps.iteration_count > NATIVE_TOOL_INVOCATION_LIMIT:
            with logfire_span(
                "tool_iteration_breaker",
                iteration_count=deps.iteration_count,
                limit=NATIVE_TOOL_INVOCATION_LIMIT,
            ):
                raise BrokerLoopBreaker(
                    f"Tool invocation limit exceeded "
                    f"({deps.iteration_count} calls, limit {NATIVE_TOOL_INVOCATION_LIMIT}). "
                    "The pre-injected context plus earlier tool results contain enough "
                    "data to produce the final structured output. Generate it now.",
                    breaker_kind="iteration_limit",
                )

        # SWI-86: per-query dedup (budget efficiency, not crash-prevention).
        # Identical args → identical result; after DUPLICATE_CALL_LIMIT repeats
        # short-circuit so the agent stops re-spending its budget on the same
        # query. Signature is computed on the model-facing args only (`_ctx` is
        # injected below, after this check).
        call_signature = f"{name}::{json.dumps(kwargs, sort_keys=True, default=str)}"
        deps.duplicate_call_counts[call_signature] = (
            deps.duplicate_call_counts.get(call_signature) or 0
        ) + 1
        if deps.duplicate_call_counts[call_signature] > DUPLICATE_CALL_LIMIT:
            with logfire_span(
                "duplicate_query_breaker",
                tool_name=name,
                repeat_count=deps.duplicate_call_counts[call_signature],
            ):
                raise BrokerLoopBreaker(
                    f"Tool {name} called with identical arguments "
                    f"{deps.duplicate_call_counts[call_signature]} times. Repeating the "
                    "same query returns the same result — use the data already in your "
                    "context to produce the final structured output now.",
                    breaker_kind="duplicate_query",
                )

        with logfire_span(
            "broker_tool",
            tool_name=name,
            attempt_index=0,
            error=False,
            error_type="",
        ) as current_span:
            if needs_ctx:
                kwargs = {**kwargs, "_ctx": deps_to_ctx_dict(deps)}

            try:
                result = await impl(**kwargs)
                if isinstance(result, str):
                    return result
                return json.dumps(result, ensure_ascii=False)
            except ValidationError as validation_error:
                classified = classify_validation_error(
                    name,
                    validation_error,
                    tickers_in_scope=deps.tickers_in_scope or None,
                )
                logger.warning("Tool %s validation_error: %s", name, validation_error)
                current_span.set_attribute("error", True)
                current_span.set_attribute("error_type", classified["error_type"])
                _bump_error_signature(deps, name, classified["error_type"], classified["hint"])
                # ModelRetry surfaces the classified hint to the LLM and lets
                # pydantic-ai's retry path re-prompt with the hint visible.
                raise ModelRetry(json.dumps(classified)) from validation_error
            except Exception as exc:
                logger.warning("Tool %s failed: %s", name, exc)
                current_span.set_attribute("error", True)
                current_span.set_attribute("error_type", "exception")
                raise ModelRetry(json.dumps({"error": f"Tool {name} failed: {exc}"})) from exc

    # Override the wrapper's signature AND __annotations__ so pydantic-ai's
    # schema generator (which reads type_hints) sees the original tool's
    # parameter shape (incl. Literals + Annotated lists). Both are needed:
    # __signature__ drives parameter ordering / required-vs-optional; the
    # annotations dict drives type extraction inside _function_schema.
    impl_sig = inspect.signature(impl)
    wrapper.__signature__ = _build_wrapper_signature(impl_sig)  # type: ignore[attr-defined]
    wrapper.__annotations__ = {
        "ctx": RunContext[AgentDeps],
        **{
            pname: p.annotation
            for pname, p in impl_sig.parameters.items()
            if pname != "_ctx" and p.annotation is not inspect.Parameter.empty
        },
        "return": str,
    }
    wrapper.__name__ = name.replace(".", "_")
    wrapper.__doc__ = tool_def.description
    return wrapper


@functools.cache
def build_native_tools() -> tuple[Tool[AgentDeps], ...]:
    """Build a `pydantic_ai.Tool` per registered `ToolDef` in the broker
    catalog, applying `_wrap_with_policy` middleware to each. Cached: the
    catalog is module-level immutable, so wrappers + JSON schemas are built
    once per process (called by every `create_agent`).
    """
    if not TOOL_CATALOG:
        raise RuntimeError(
            "TOOL_CATALOG is empty. Import scripts.agents.tools.broker.domains.* "
            "before calling build_native_tools()."
        )
    return tuple(
        Tool(
            _wrap_with_policy(tool_def),
            name=tool_def.name,
            description=tool_def.description,
            takes_ctx=True,
        )
        for tool_def in TOOL_CATALOG.values()
    )


async def unlock_tool(ctx: RunContext[AgentDeps], tool_name: str | None = None) -> str:
    """Admit a non-allowlisted tool into your active surface for the rest of
    this run. Argument-tolerant: pass `tool_name=None` to receive a coaching
    JSON listing the locked tools and an example. Idempotent: re-unlocking a
    tool returns early without bumping the budget.
    """
    deps = ctx.deps
    if tool_name is None or not tool_name.strip():
        return json.dumps(
            {
                "error": "specify tool_name",
                "hint": (
                    "Call unlock_tool(tool_name='<domain.verb>') to make a "
                    "non-allowlisted tool callable for the rest of this run."
                ),
                "example": 'unlock_tool(tool_name="enrichment.get_flow")',
            }
        )

    name = tool_name.strip()
    if name in deps.unlocked:
        return json.dumps({"status": "already_unlocked", "tool_name": name})

    tool_def = get_tool(name)
    if tool_def is None:
        return json.dumps(unknown_tool_error(name))

    # State-mutating tools are reachable only via a YAML allowlist, never via unlock.
    # Untrusted text (news headlines, article bodies) reaches these prompts verbatim,
    # so an unlockable write tool would let a crafted headline register or cancel alerts.
    if tool_def.mutates:
        return json.dumps(
            {
                "error": "tool_writes_state",
                "tool_name": name,
                "hint": (
                    f"{name} writes state, so it cannot be unlocked at run time. "
                    "Add it to this agent's allowed_tools in YAML if it genuinely "
                    "needs it. Read-only tools unlock normally."
                ),
            }
        )

    deps.unlocked.add(name)
    return json.dumps({"status": "unlocked", "tool_name": name})


@functools.cache
def make_prepare_tools(
    allowed: frozenset[str],
) -> Callable[
    [RunContext[AgentDeps], list[ToolDefinition]],
    Awaitable[list[ToolDefinition]],
]:
    """Build a `prepare_tools` callback admitting `allowed | unlocked | {unlock_tool}`.

    `UNLOCK_BUDGET = max(1, TOTAL_TOOL_BUDGET - len(allowed))` — keeps the
    total visible surface ≤ `TOTAL_TOOL_BUDGET` (15) at all times.
    """
    unlock_budget = max(1, TOTAL_TOOL_BUDGET - len(allowed))

    async def prepare(
        ctx: RunContext[AgentDeps], tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        deps = ctx.deps
        if len(deps.unlocked) > unlock_budget:
            raise BrokerLoopBreaker(
                f"unlock_tool budget exceeded "
                f"({len(deps.unlocked)} > {unlock_budget}). Use the tools you've "
                "already unlocked, or proceed with your allowed_tools and the "
                "pre-injected context.",
                breaker_kind="unlock_overuse",
            )
        # Second gate: even if `unlocked` were populated some other way, a mutating
        # tool only ever becomes visible through the static allowlist.
        unlocked_readonly = {
            n for n in deps.unlocked if not (getattr(get_tool(n), "mutates", False))
        }
        admitted = allowed | unlocked_readonly | {"unlock_tool"}
        return [td for td in tool_defs if getattr(td, "name", "") in admitted]

    return prepare


@functools.cache
def render_catalog(allowed: frozenset[str]) -> str:
    """Render the tool-catalog block prepended to an agent's system prompt.

    For each allowed tool, lists `name(*req_param, ?opt_param)` with the
    one-line description. Marks `*` for required and `?` for optional. The
    `unlock_tool` helper is always documented at the bottom because every
    agent has it admitted by `make_prepare_tools`. Cached on `frozenset`
    key — same allowlist renders the same string.
    """
    lines = ["## Tools available"]
    if not allowed:
        lines.append(
            "No tools are allowed by default. Call "
            '`unlock_tool(tool_name="<domain.verb>")` to admit a broker tool '
            f"for this run (budget: {TOTAL_TOOL_BUDGET} unlocks)."
        )
    else:
        for name in sorted(allowed):
            tool_def = TOOL_CATALOG.get(name)
            if tool_def is None:
                continue
            params_obj = (
                (tool_def.parameters.get("properties") or {})
                if isinstance(tool_def.parameters, dict)
                else {}
            )
            required_obj = (
                (tool_def.parameters.get("required") or [])
                if isinstance(tool_def.parameters, dict)
                else []
            )
            required_set = set(required_obj) if isinstance(required_obj, list) else set()
            param_strs: list[str] = []
            if isinstance(params_obj, dict):
                for pname in params_obj:
                    marker = "*" if pname in required_set else "?"
                    param_strs.append(f"{marker}{pname}")
            sig = ", ".join(param_strs)
            desc = tool_def.description.strip().split("\n", 1)[0].split(". ", 1)[0][:120]
            hint = f" → {tool_def.returns_hint}" if tool_def.returns_hint else ""
            lines.append(f"- {name}({sig}) — {desc}{hint}")
    lines.append(
        '\n`unlock_tool(tool_name="<name>")` — admit a non-listed tool. '
        "Idempotent. Argument-tolerant (call with no args to see a coaching hint)."
    )
    return "\n".join(lines)
