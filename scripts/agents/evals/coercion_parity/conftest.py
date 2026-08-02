"""Shared fixtures for the coercion-parity test suite (SWI-206).

Adds the repo's ``scripts/`` dir to ``sys.path`` and exposes a
``capture_emits`` fixture that monkey-patches
``shared.observability_post_llm.emit_rule_outcome`` so tests can assert
the emit-presence contract without firing real Logfire events.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def capture_emits(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Monkey-patch every ``emit_rule_outcome`` import site in one shot.

    Pydantic validators import ``emit_rule_outcome`` at module-import
    time, so patching the source module alone misses the call. We patch
    the source AND every known re-import site used by the rule modules.
    """
    captured: list[dict[str, object]] = []

    def _fake(rule_id: str, outcome: str, **kwargs: object) -> None:
        captured.append({"rule_id": rule_id, "outcome": outcome, **kwargs})

    targets = [
        "shared.observability_post_llm.emit_rule_outcome",
        "shared.rules.catalyst_classifier.emit_rule_outcome",
        "shared.rules.critic_coercion.emit_rule_outcome",
        "shared.rules.retro_rule_classifier.emit_rule_outcome",
        "shared.rules.vnd_price_clamp.emit_rule_outcome",
        "agents.belief_models.emit_rule_outcome",
        "agents.watchlist_update.emit_rule_outcome",
    ]
    for target in targets:
        try:
            monkeypatch.setattr(target, _fake)
        except (AttributeError, ModuleNotFoundError):
            # Module not yet imported in this test — skip silently.
            continue
    return captured
