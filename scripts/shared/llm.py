#!/usr/bin/env python3
"""Minimal LLM wrapper using OpenAI SDK for Together AI."""

import json
import os
import time
from collections.abc import Callable

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI

from .config import LLM_BASE_URL, LLM_MODEL
from .env import is_dry_run
from .session import get_extra_body

_RETRYABLE_ERRORS = (InternalServerError, APIConnectionError, APITimeoutError)
_RETRY_DELAYS = [2, 5, 10]

# Prevents single-call hangs from exceeding script-level budgets. See 2026-04-13 catalyst-check timeout.
_HTTP_TIMEOUT_SECONDS = 60.0

# Lazy singleton — avoids creating a new HTTP session per call
_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            base_url=LLM_BASE_URL,
            api_key=os.environ["OPENROUTER_API_KEY"],
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
    return _openai_client


def _generate_stub_json(json_schema: dict) -> str:
    """Generate minimal valid JSON from Together AI structured output schema format."""
    inner = json_schema.get("json_schema", {}).get("schema", {})
    if not inner:
        return "{}"
    result: dict = {}
    props = inner.get("properties", {})
    for key in inner.get("required", []):
        t = props.get(key, {}).get("type", "string")
        if t == "array":
            result[key] = []
        elif t == "string":
            result[key] = ""
        elif t in ("integer", "number"):
            result[key] = 0
        elif t == "boolean":
            result[key] = False
        else:
            result[key] = {}
    return json.dumps(result)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    json_schema: dict | None = None,
    model: str | None = None,
    max_tokens: int = 10000,
) -> str:
    """One-shot LLM call via Together AI.

    Args:
        system_prompt: System message
        user_prompt: User message
        json_schema: Optional JSON schema for structured output
        model: Override model (defaults to LLM_MODEL)
        max_tokens: Max output tokens (default 10000; Together AI defaults to 2048 which truncates large JSON)

    Returns:
        Model response content as string
    """
    if is_dry_run():
        return _generate_stub_json(json_schema) if json_schema else "[DRY RUN] LLM call skipped"

    client = _get_openai_client()

    kwargs: dict = {
        "model": model or LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.6,
        "max_tokens": max_tokens,
    }

    if json_schema:
        kwargs["response_format"] = json_schema

    openrouter_extra = get_extra_body(agent_name="call_llm")
    if openrouter_extra:
        existing_extra = kwargs.get("extra_body")
        if isinstance(existing_extra, dict):
            kwargs["extra_body"] = {**existing_extra, **openrouter_extra}
        else:
            kwargs["extra_body"] = openrouter_extra

    for attempt in range(len(_RETRY_DELAYS)):
        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except _RETRYABLE_ERRORS as error:
            if attempt < len(_RETRY_DELAYS) - 1:
                delay = _RETRY_DELAYS[attempt]
                print(
                    f"  [LLM] Attempt {attempt + 1} failed ({type(error).__name__}), retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                raise

    return ""  # unreachable, satisfies type checker


def call_llm_with_json_parse(
    system_prompt: str,
    user_prompt: str,
    json_schema: dict,
    model: str | None = None,
    max_tokens: int = 10000,
    *,
    max_attempts: int = 1,
    backoff_seconds: float = 0.0,
    decode_fallback: Callable[[str], dict] | None = None,
    on_attempt_error: Callable[[int, Exception], None] | None = None,
) -> dict:
    """Call ``call_llm`` then parse JSON, with optional retry + decode fallback.

    ``max_attempts=1`` (default) preserves no-retry callers. Retries wrap the full
    call+parse step, so transport failures AND json decode failures both count.
    ``decode_fallback`` lets a caller rescue malformed JSON (e.g. multi-object
    responses) without implementing its own try/except around ``json.loads``.
    ``on_attempt_error`` fires on every failed attempt BEFORE a potential retry
    and is the hook for per-attempt logging.

    Raises the final exception after attempts exhausted; caller wraps for fallback.
    """
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = call_llm(system_prompt, user_prompt, json_schema, model, max_tokens)
            try:
                parsed = json.loads(response)
            except json.JSONDecodeError:
                if decode_fallback is None:
                    raise
                parsed = decode_fallback(response)
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"call_llm_with_json_parse expected dict, got {type(parsed).__name__}"
                )
            return parsed
        except Exception as error:
            last_error = error
            if on_attempt_error is not None:
                on_attempt_error(attempt, error)
            if attempt < max_attempts - 1 and backoff_seconds > 0:
                time.sleep(backoff_seconds)
    assert last_error is not None
    raise last_error
