"""Regression: silent-hang alert populates dynamic provider exclusion.

Fix 3 (2026-04-22): when a provider-class hang cluster fires (>=3 distinct
agents) with at least two hits on a single upstream backend, that backend
slug is added to the session's dynamic exclusion set. OpenRouter routing
then avoids it for the rest of the session — recovery is mid-run, not
next-day.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_session_state():
    """Each test starts with a clean session + exclusion state."""
    from shared import session

    session.reset_session()
    yield
    session.reset_session()


@pytest.fixture
def _inited_session():
    from shared import session

    with (
        patch.dict(os.environ, {"LOGFIRE_ENVIRONMENT": "test"}),
        patch("shared.config.get_scan_date", return_value="2026-04-22"),
    ):
        session.init_session("test_pipeline")
    yield
    session.reset_session()


def test_add_provider_exclusion_is_idempotent():
    from shared.session import add_provider_exclusion, get_dynamic_provider_excludes

    add_provider_exclusion("siliconflow")
    add_provider_exclusion("siliconflow")
    add_provider_exclusion("SILICONFLOW")  # case-normalized
    assert get_dynamic_provider_excludes() == frozenset({"siliconflow"})


def test_get_extra_body_merges_static_and_dynamic(_inited_session):
    from shared.session import add_provider_exclusion, get_extra_body

    add_provider_exclusion("chutes")
    extra = get_extra_body(agent_name="market_level")
    assert extra is not None
    provider = extra["provider"]
    assert "siliconflow" in provider["ignore"]
    assert "chutes" in provider["ignore"]
    # Sorted for deterministic output
    assert provider["ignore"] == sorted(provider["ignore"])
    assert provider["allow_fallbacks"] is True


def test_reset_session_clears_dynamic_excludes(_inited_session):
    from shared import session
    from shared.session import add_provider_exclusion, get_dynamic_provider_excludes

    add_provider_exclusion("chutes")
    assert get_dynamic_provider_excludes() == frozenset({"chutes"})
    session.reset_session()
    assert get_dynamic_provider_excludes() == frozenset()


def test_alert_excludes_providers_that_hung_twice():
    """Provider must be implicated twice+ before exclusion kicks in."""
    from shared.alerts.silent_hang_alert import maybe_emit_silent_hang_alert
    from shared.session import get_dynamic_provider_excludes

    # 3 distinct agents hung, provider 'siliconflow' shows up twice
    maybe_emit_silent_hang_alert(
        scan_date="2026-04-22",
        phase="morning",
        hang_count=3,
        hang_agents=["sector_technical", "sector_enrichment", "sector_aggregator"],
        suspected_providers=["siliconflow", "siliconflow", "chutes"],
    )
    # chutes shows only once → not excluded; siliconflow twice → excluded
    excluded = get_dynamic_provider_excludes()
    assert "siliconflow" in excluded
    assert "chutes" not in excluded


def test_alert_below_threshold_does_not_exclude():
    from shared.alerts.silent_hang_alert import maybe_emit_silent_hang_alert
    from shared.session import get_dynamic_provider_excludes

    maybe_emit_silent_hang_alert(
        scan_date="2026-04-22",
        phase="morning",
        hang_count=2,  # below default threshold of 3
        hang_agents=["a", "b"],
        suspected_providers=["siliconflow", "siliconflow"],
    )
    assert get_dynamic_provider_excludes() == frozenset()


def test_alert_without_providers_still_fires_but_no_exclusion():
    from shared.alerts.silent_hang_alert import maybe_emit_silent_hang_alert
    from shared.session import get_dynamic_provider_excludes

    maybe_emit_silent_hang_alert(
        scan_date="2026-04-22",
        phase="morning",
        hang_count=3,
        hang_agents=["a", "b", "c"],
        suspected_providers=None,
    )
    assert get_dynamic_provider_excludes() == frozenset()
