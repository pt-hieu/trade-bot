"""Singleton invariant for the agents/model package (SWI-212 FIX 6).

After splitting ``agents/model.py`` into a package
(``wrappers.py`` + ``resolvers.py``) the ``_provider_cache`` dict
must remain a single object so cached ``httpx.AsyncClient`` instances
are not duplicated per timeout tier.

Without this test, an accidental ``_provider_cache: dict[…] = {}``
re-binding inside any submodule would silently leak ~60 connections per
agent run — the kind of drift that wouldn't fail any other test until
the OS exhausted file descriptors.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_provider_cache_is_single_object():
    from agents import model
    from agents.model import resolvers

    assert model._provider_cache is resolvers._provider_cache, (
        "agents.model._provider_cache must be the same dict object as "
        "agents.model.resolvers._provider_cache. A re-binding broke the "
        "singleton invariant — cached httpx clients will leak."
    )


def test_resolvers_does_not_rebind_provider_cache():
    """Guard against `_provider_cache = {}` inside any future submodule.

    Walks every submodule of agents.model and asserts that any module that
    exposes a ``_provider_cache`` attribute is referencing the same object.
    """
    import importlib
    import pkgutil

    from agents import model

    canonical = model._provider_cache
    package_path = Path(model.__file__).parent  # type: ignore[arg-type]
    for module_info in pkgutil.iter_modules([str(package_path)]):
        submodule = importlib.import_module(f"agents.model.{module_info.name}")
        if hasattr(submodule, "_provider_cache"):
            assert submodule._provider_cache is canonical, (
                f"agents.model.{module_info.name}._provider_cache is a different "
                "dict object — singleton invariant broken."
            )
