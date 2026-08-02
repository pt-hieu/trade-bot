"""SWI-16: lazy memoized geo factor-map validator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from shared.rules.catalyst_override import geolabel


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def setup_function(_):
    geolabel._reset_geo_factor_map_validation_for_tests()


def test_emits_warning_for_geopolitical_row_without_factors():
    rows = [
        {
            "catalyst_type": "geopolitical",
            "catalyst_key": "k1",
            "event": "e1",
            "catalyst_factors": None,
        },
        {
            "catalyst_type": "geopolitical",
            "catalyst_key": "k2",
            "event": "e2",
            "catalyst_factors": ["oil_price"],
        },
        {"catalyst_type": "policy", "catalyst_key": "p1", "event": "e3", "catalyst_factors": None},
    ]
    with (
        patch("shared.neon.catalysts.get_active_catalysts_db", new=AsyncMock(return_value=rows)),
        patch.object(geolabel, "log_warn") as mock_warn,
    ):
        asyncio.run(geolabel._validate_geo_factor_map_once())
    assert mock_warn.call_count == 1
    args, kwargs = mock_warn.call_args
    assert args[0] == "geo_factor_map_missing"
    assert kwargs["catalyst_key"] == "k1"


def test_second_call_is_noop():
    rows = [
        {
            "catalyst_type": "geopolitical",
            "catalyst_key": "k1",
            "event": "e1",
            "catalyst_factors": None,
        },
    ]
    with (
        patch(
            "shared.neon.catalysts.get_active_catalysts_db", new=AsyncMock(return_value=rows)
        ) as mock_get,
        patch.object(geolabel, "log_warn"),
    ):
        asyncio.run(geolabel._validate_geo_factor_map_once())
        asyncio.run(geolabel._validate_geo_factor_map_once())
    assert mock_get.call_count == 1


def test_db_failure_does_not_raise():
    geolabel._reset_geo_factor_map_validation_for_tests()
    with patch(
        "shared.neon.catalysts.get_active_catalysts_db",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        # Must not raise.
        asyncio.run(geolabel._validate_geo_factor_map_once())


def test_no_geopolitical_rows_no_warn():
    rows = [
        {"catalyst_type": "policy", "catalyst_key": "p1", "event": "e", "catalyst_factors": None}
    ]
    with (
        patch("shared.neon.catalysts.get_active_catalysts_db", new=AsyncMock(return_value=rows)),
        patch.object(geolabel, "log_warn") as mock_warn,
    ):
        asyncio.run(geolabel._validate_geo_factor_map_once())
    assert not mock_warn.called
