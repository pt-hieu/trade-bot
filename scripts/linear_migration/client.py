"""Shared Linear GraphQL client for migration + export + write-back scripts.

Thin wrapper around httpx that handles:
    - ``LINEAR_API_KEY`` authentication
    - 429 / 5xx exponential backoff (up to ``MAX_RETRIES``)
    - constant per-call pacing so bulk loops do not trip the Linear rate
      limit during a re-run of pass 1 (~1000 calls in one burst)
    - GraphQL ``errors`` surfacing as :class:`GraphqlError`

``httpx.Client`` must be closed explicitly; use ``with LinearClient(...)``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import cast

import httpx

LINEAR_ENDPOINT = "https://api.linear.app/graphql"
RATE_LIMIT_DELAY_S = 0.12
MAX_RETRIES = 4

LABELS_JSON_PATH = Path(__file__).resolve().parent / "labels.json"


class GraphqlError(RuntimeError):
    """Linear GraphQL errors surfaced verbatim for operator triage."""


class LinearClient:
    """Authenticated Linear GraphQL client with retry + pacing."""

    def __init__(self, api_key: str) -> None:
        self._client = httpx.Client(
            base_url=LINEAR_ENDPOINT,
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            timeout=30.0,
        )

    def __enter__(self) -> LinearClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def query(self, document: str, variables: dict[str, object] | None = None) -> dict[str, object]:
        payload = {"query": document, "variables": variables or {}}
        for attempt in range(MAX_RETRIES):
            response = self._client.post("", json=payload)
            if response.status_code == 429 or response.status_code >= 500:
                wait = RATE_LIMIT_DELAY_S * (2**attempt)
                time.sleep(wait)
                continue
            if response.status_code >= 400:
                raise GraphqlError(
                    f"HTTP {response.status_code} from Linear: {response.text[:1200]}"
                )
            data = response.json()
            if data.get("errors"):
                raise GraphqlError(json.dumps(data["errors"], indent=2))
            time.sleep(RATE_LIMIT_DELAY_S)
            return cast(dict[str, object], data.get("data") or {})
        raise GraphqlError(f"exhausted retries for payload: {document[:80]}")


def require_api_key() -> str:
    """Return ``LINEAR_API_KEY`` or raise with an operator-friendly message.

    Loads ``.env`` (or ``.env.local`` without ``SWINGY_ENV=production``) first
    so the caller does not have to export the key manually on every run.
    """
    try:
        from scripts.shared.env import load_env  # type: ignore[import-not-found]

        load_env()
    except ImportError:
        try:
            from shared.env import load_env as _load_env  # type: ignore[import-not-found]

            _load_env()
        except ImportError:
            pass
    api_key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not api_key:
        raise GraphqlError(
            "LINEAR_API_KEY is not set; add it to .env (SWINGY_ENV=production) and retry"
        )
    return api_key


def load_labels_json() -> dict[str, object]:
    """Return the raw labels.json map. Callers cast nested sections as needed."""
    return cast(dict[str, object], json.loads(LABELS_JSON_PATH.read_text()))


def load_team_id() -> str:
    """Return the Swingy team UUID from labels.json."""
    raw = load_labels_json()
    return cast(dict[str, str], raw["team"])["id"]


_STATE_IDS_QUERY = "query($teamId: String!) { team(id: $teamId) { states { nodes { id name } } } }"


def state_ids_by_name(client: LinearClient, team_id: str) -> dict[str, str]:
    """Return ``{state_name: state_id}`` for the given Linear team.

    Single source of truth for state lookups. Re-used by the post-commit hook
    (``link_commit_to_linear.py``), the write-back orchestrator
    (``process_review_findings.py``), and the time-axis reconciler
    (``linear_reconciler.py``).
    """
    data = client.query(_STATE_IDS_QUERY, {"teamId": team_id})
    team = cast(dict[str, object], data.get("team") or {})
    states = cast(dict[str, object], team.get("states") or {})
    nodes = cast(list[dict[str, object]], states.get("nodes") or [])
    return {cast(str, n["name"]): cast(str, n["id"]) for n in nodes}
