"""SWI-199: catalyst_key composer parity tests.

Pinned (event → expected_key) pairs derived from the Python composer; the
SQL recompose in migration 334 must yield identical strings for the same
inputs. Run the corresponding SQL `SELECT trim(both '_' from substr(...))`
against any Postgres instance to verify.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from shared.rules.catalyst_key import compose_catalyst_key


def _expected(event: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", event.lower()).strip("_")[:32]
    digest = hashlib.md5(event.encode("utf-8")).hexdigest()[:8]
    if not slug:
        return f"event_{digest}"
    return f"{slug}_{digest}"


@pytest.mark.parametrize(
    "event",
    [
        "Trump threatens Hormuz blockade",
        "  Trump+,fires Fed!  ",
        "UAE quits OPEC over oil supply dispute",
        "IMF cuts global GDP outlook for 2026",
        "Idemitsu commissions 4M-barrel refinery upgrade",
        "Decree 142 on AML",
        "!!!",
        "Thủ tướng đề xuất tăng phụ cấp",
        "Long Son petrochemical complex suspends operations",
        "Federal Reserve holds at 4.5% — Powell hints at cut",
    ],
)
def test_compose_catalyst_key_matches_sql_recompose(event: str) -> None:
    key = compose_catalyst_key(event)
    assert key == _expected(event)
    # Composer guarantees: total length ≤ 41, ends in 8 hex chars after '_'.
    assert len(key) <= 41
    assert re.fullmatch(r".+_[0-9a-f]{8}", key)


def test_compose_catalyst_key_empty_event() -> None:
    assert compose_catalyst_key("") == "empty_d41d8cd9"


def test_compose_catalyst_key_caps_slug_at_32() -> None:
    long = "a" * 100
    key = compose_catalyst_key(long)
    # Slug capped at 32 + '_' + 8-char digest = 41
    assert len(key) == 41
    assert key.startswith("a" * 32 + "_")
