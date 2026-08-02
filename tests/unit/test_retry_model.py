"""RetryModel semantics: 2 retries with 2-8s jitter, fail-fast on cluster evidence.

Replaces the pre-2026-04-22 SingleRetryModel (one retry). The generous-retry
policy was chosen after the 2026-04-22 morning scan showed MiniMax fallback
is schema-broken for nested outputs — retrying the primary is more likely to
recover than rolling over to the fallback.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from pydantic_ai.models import Model


class _FlakyWrapped(Model):
    """Wrapped model that raises TimeoutError on its first N calls.

    When ``downstream_provider`` is set, it raises a ``HopTimeout`` carrying
    that serving-upstream slug instead of a plain ``TimeoutError`` — this is
    what RetryModel's fail-fast check keys on (never the model author).
    """

    def __init__(
        self,
        timeout_on_calls: int,
        model_name_str: str = "test/provider-a",
        downstream_provider: str | None = None,
    ):
        self._timeout_on_calls = timeout_on_calls
        self._model_name_str = model_name_str
        self._downstream_provider = downstream_provider
        self.call_count = 0

    async def request(self, messages, model_settings, model_request_parameters):
        self.call_count += 1
        if self.call_count <= self._timeout_on_calls:
            if self._downstream_provider is not None:
                from agents.model.wrappers import HopTimeout

                raise HopTimeout(
                    f"stub timeout on call {self.call_count}",
                    provider_slug="stub-author",
                    downstream_provider=self._downstream_provider,
                )
            raise TimeoutError(f"stub timeout on call {self.call_count}")
        return {"ok": True, "call": self.call_count}

    @property
    def model_name(self) -> str:  # type: ignore[override]
        return self._model_name_str

    @property
    def system(self) -> str:  # type: ignore[override]
        return "stub"


class _SchemaFailingWrapped(Model):
    """Wrapped model that raises a non-TimeoutError on every call.

    Used to prove RetryModel does NOT retry on schema/validation errors —
    only TimeoutError is retryable; everything else propagates immediately.
    """

    def __init__(self, exc: Exception, model_name_str: str = "test/provider-a"):
        self._exc = exc
        self._model_name_str = model_name_str
        self.call_count = 0

    async def request(self, messages, model_settings, model_request_parameters):
        self.call_count += 1
        raise self._exc

    @property
    def model_name(self) -> str:  # type: ignore[override]
        return self._model_name_str

    @property
    def system(self) -> str:  # type: ignore[override]
        return "stub"


@pytest.mark.asyncio
async def test_retry_model_retries_on_hang_and_succeeds_on_attempt_3():
    """TimeoutError twice → retries twice (attempts 2 and 3) → succeeds on 3rd call."""
    from agents.model import RetryModel
    from shared.session import reset_session

    reset_session()

    wrapped = _FlakyWrapped(timeout_on_calls=2, model_name_str="test/provider-ok")
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    retry = RetryModel(
        wrapped,
        sleeper=_fake_sleep,
        jitter_fn=lambda: 3.5,
    )

    emitted: list[dict[str, Any]] = []

    def _record(**kwargs):
        emitted.append(kwargs)

    with patch("agents.model.wrappers.emit_model_hop_retry_span", side_effect=_record):
        result = await retry.request(messages=[], model_settings={}, model_request_parameters={})

    assert result == {"ok": True, "call": 3}
    assert wrapped.call_count == 3
    assert sleeps == [3.5, 3.5]
    assert [e["attempt"] for e in emitted] == [2, 3]
    assert all(e["outcome"] == "retry" for e in emitted)


@pytest.mark.asyncio
async def test_retry_model_does_not_retry_on_schema_exception():
    """Non-TimeoutError propagates after the first attempt — no retry, no backoff."""
    from agents.model import RetryModel
    from shared.session import reset_session

    reset_session()

    wrapped = _SchemaFailingWrapped(
        exc=ValueError("schema validation failed"),
        model_name_str="test/provider-ok",
    )
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    retry = RetryModel(
        wrapped,
        sleeper=_fake_sleep,
        jitter_fn=lambda: 999.0,
    )

    with pytest.raises(ValueError, match="schema validation failed"):
        await retry.request(messages=[], model_settings={}, model_request_parameters={})

    assert wrapped.call_count == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_retry_model_jitter_respects_backoff_range():
    """Real jitter (no jitter_fn override) draws from backoff_range inclusive."""
    from agents.model import RetryModel
    from shared.session import reset_session

    reset_session()

    wrapped = _FlakyWrapped(timeout_on_calls=2, model_name_str="test/provider-ok")
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    retry = RetryModel(
        wrapped,
        backoff_range=(2.0, 8.0),
        sleeper=_fake_sleep,
    )

    with patch("agents.model.wrappers.emit_model_hop_retry_span"):
        await retry.request(messages=[], model_settings={}, model_request_parameters={})

    assert wrapped.call_count == 3
    assert len(sleeps) == 2
    for backoff in sleeps:
        assert 2.0 <= backoff <= 8.0


@pytest.mark.asyncio
async def test_retry_model_caps_at_max_retries_then_raises():
    """3 consecutive timeouts with max_retries=2 → 3 attempts total → TimeoutError."""
    from agents.model import RetryModel
    from shared.session import reset_session

    reset_session()

    wrapped = _FlakyWrapped(timeout_on_calls=10, model_name_str="test/provider-ok")
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    retry = RetryModel(
        wrapped,
        sleeper=_fake_sleep,
        jitter_fn=lambda: 2.0,
    )

    with (
        patch("agents.model.wrappers.emit_model_hop_retry_span"),
        pytest.raises(asyncio.TimeoutError),
    ):
        await retry.request(messages=[], model_settings={}, model_request_parameters={})

    # 1 initial + 2 retries = 3 attempts; 2 sleeps between them.
    assert wrapped.call_count == 3
    assert sleeps == [2.0, 2.0]


@pytest.mark.asyncio
async def test_retry_model_fails_fast_on_downstream_cluster_evidence():
    """When the caught HopTimeout's downstream UPSTREAM slug is in the
    session exclusion set, re-raise without retry — the cluster evidence
    means a retry on the same upstream is wasted."""
    from agents.model import RetryModel
    from shared.session import add_provider_exclusion, reset_session

    reset_session()

    wrapped = _FlakyWrapped(
        timeout_on_calls=5,
        model_name_str="moonshotai/kimi-k2.5",
        downstream_provider="siliconflow",
    )
    add_provider_exclusion("siliconflow")

    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    retry = RetryModel(
        wrapped,
        sleeper=_fake_sleep,
        jitter_fn=lambda: 999.0,
    )

    emitted: list[dict[str, Any]] = []

    def _record(**kwargs):
        emitted.append(kwargs)

    with (
        patch("agents.model.wrappers.emit_model_hop_retry_span", side_effect=_record),
        pytest.raises(TimeoutError),
    ):
        await retry.request(messages=[], model_settings={}, model_request_parameters={})

    assert wrapped.call_count == 1
    assert sleeps == []
    assert len(emitted) == 1
    assert emitted[0]["outcome"] == "fail_fast_cluster_evidence"
    reset_session()


@pytest.mark.asyncio
async def test_retry_model_does_not_fail_fast_on_author_slug():
    """2026-05-15 fleet kill-switch regression guard.

    With the model AUTHOR slug in the exclusion set but no downstream
    upstream identified (the common silent-hang shape — wall fires before
    any response byte), RetryModel must still retry. An author-keyed
    fail-fast took the whole single-author fleet offline the moment one
    cluster fired.
    """
    from agents.model import RetryModel
    from shared.session import add_provider_exclusion, reset_session

    reset_session()

    # Author slug is "moonshotai"; the plain TimeoutError carries no
    # downstream_provider, so fail-fast must NOT trigger.
    wrapped = _FlakyWrapped(timeout_on_calls=10, model_name_str="moonshotai/kimi-k2.5")
    add_provider_exclusion("moonshotai")

    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    retry = RetryModel(
        wrapped,
        sleeper=_fake_sleep,
        jitter_fn=lambda: 2.0,
    )

    with (
        patch("agents.model.wrappers.emit_model_hop_retry_span"),
        pytest.raises(asyncio.TimeoutError),
    ):
        await retry.request(messages=[], model_settings={}, model_request_parameters={})

    # Retried the full budget (1 initial + 2 retries) — did NOT fail-fast.
    assert wrapped.call_count == 3
    assert sleeps == [2.0, 2.0]
    reset_session()
