"""Stable catalyst_key composer (SWI-199).

Centralizes the catalyst-event → catalyst_key transform so Python and SQL
stay bit-identical. The previous inline ``event.lower().replace(" ", "_")[:60]``
truncated mid-word and silently broke joins on
``catalyst_news_signals.catalyst_key``.

Format: ``<slug>_<md5_8>`` where:
    * ``slug``  — lowercase event with non-alnum runs collapsed to ``_``,
                  trimmed of leading/trailing ``_``, capped at 32 chars.
    * ``md5_8`` — first 8 hex chars of MD5(event UTF-8 bytes).

MD5 is chosen so ``compose_catalyst_key`` matches Postgres' built-in
``md5(event)`` function bit-for-bit — no ``pgcrypto`` dependency, FK
recompose in migrations stays trivial.
"""

from __future__ import annotations

import hashlib
import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def compose_catalyst_key(event: str) -> str:
    """Return a stable catalyst_key for ``event``.

    Total length ≤ 41 chars (32 + ``_`` + 8). Fits the ``VARCHAR(64)`` column
    introduced by migration 334 with headroom.
    """
    if not event:
        # Defensive — agent emits non-empty event by schema, but fail-loud here.
        digest = hashlib.md5(b"").hexdigest()[:8]
        return f"empty_{digest}"
    slug = _SLUG_RE.sub("_", event.lower()).strip("_")[:32]
    digest = hashlib.md5(event.encode("utf-8")).hexdigest()[:8]
    if not slug:
        return f"event_{digest}"
    return f"{slug}_{digest}"
