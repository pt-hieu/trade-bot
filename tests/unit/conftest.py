"""tests/unit pytest config — re-exports shared fixtures from _fixtures/ packages."""

from tests.unit._fixtures.retro_compute import buy_recs, eod_prices  # noqa: F401
