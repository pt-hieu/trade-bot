"""Pin the per-analyst UsageLimitExceeded contract.

When a positions analyst (value/thesis/technical) exhausts its per-agent
`request_limit`, pydantic-ai raises `UsageLimitExceeded` out of `agent.run()`.
`_run_analyst()` must return an empty `AnalystReport(views=[])` so the ensemble
aggregator can observe a belief-coverage gap and raise a well-labelled error.
If a future refactor turns this into a propagating exception, the hard-fail in
`belief_coverage.py` loses its attribution to the specific analyst(s) that
failed — the root cause of the 2026-04-24 outage.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.mark.parametrize("analyst_type", ["value", "thesis", "technical"])
def test_usage_limit_exceeded_returns_empty_report(analyst_type):
    from agents import positions_ensemble
    from agents.positions_ensemble_models import AnalystReport

    class FakeAgent:
        async def run(self, *_args, **_kwargs):
            raise UsageLimitExceeded("request_limit=10 exceeded")

    fake_config = object()

    async def fake_creator():
        return FakeAgent(), fake_config

    creators = {
        "technical": "_create_technical_agent",
        "value": "_create_value_agent",
        "thesis": "_create_thesis_agent",
    }

    with (
        patch.object(positions_ensemble, creators[analyst_type], fake_creator),
        patch.object(
            positions_ensemble,
            "build_usage_limits",
            return_value=None,
        ),
    ):
        result = asyncio.run(
            positions_ensemble._run_analyst(
                analyst_type=analyst_type,
                scan_date=date(2026, 4, 24),
            )
        )

    assert isinstance(result, AnalystReport), (
        "UsageLimitExceeded must be caught and mapped to an empty AnalystReport — "
        "leaking the exception silently breaks belief-coverage attribution."
    )
    assert result.views == [], (
        "empty views list is the signal the aggregator uses to detect missing "
        "analysts; any non-empty value masks the gap."
    )
    assert "usage limit" in result.summary.lower(), (
        "summary must attribute the failure to the usage limit so post-mortems "
        "can distinguish this from timeouts / schema failures."
    )
