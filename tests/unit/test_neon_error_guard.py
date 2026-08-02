"""Tests for shared.neon._error_guard.narrow_db_error."""

from __future__ import annotations

import asyncpg
import pytest

from shared.neon._error_guard import narrow_db_error


def test_swallows_postgres_connection_error(caplog):
    exc = asyncpg.PostgresConnectionError("connection lost")
    with caplog.at_level("WARNING"):
        narrow_db_error(exc, context="test_writer")
    assert any("test_writer" in r.getMessage() for r in caplog.records)


def test_swallows_timeout_error(caplog):
    exc = TimeoutError("query exceeded deadline")
    with caplog.at_level("WARNING"):
        narrow_db_error(exc, context="test_writer")
    assert any("test_writer" in r.getMessage() for r in caplog.records)


def test_reraises_runtime_error():
    exc = RuntimeError("EVAL_PERSISTENCE_GAP")
    with pytest.raises(RuntimeError, match="EVAL_PERSISTENCE_GAP"):
        narrow_db_error(exc, context="test_writer")


def test_reraises_key_error():
    exc = KeyError("ticker")
    with pytest.raises(KeyError):
        narrow_db_error(exc, context="test_writer")


def test_reraises_value_error():
    exc = ValueError("invalid enum")
    with pytest.raises(ValueError, match="invalid enum"):
        narrow_db_error(exc, context="test_writer")
