"""Telegram alert for silent-provider-hang clustering (MON-2026-04-19-008).

A single silent hang is expected noise (provider flake, ~1/day). Three or
more silent hangs in one pipeline run signals a provider-class problem
(e.g. Kimi K2.5 under concurrent asyncio.gather) that needs human
attention before the next phase fires.

Keeps the alert path small: one Telegram message, threshold-gated, opt-in
via `TELEGRAM_BOT_TOKEN`.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Sequence

logger = logging.getLogger(__name__)

SILENT_HANG_ALERT_THRESHOLD = 3

# A provider has to hang at least this many distinct agents before it's
# added to the session exclusion set. One agent looping on one provider
# is an agent-specific flake (schema quirk, etc.); two different agents
# on the same provider is a provider-class degradation that OpenRouter
# should route around.
PROVIDER_EXCLUSION_MIN_HANGS = 2


def maybe_emit_silent_hang_alert(
    *,
    scan_date: str,
    phase: str,
    hang_count: int,
    hang_agents: Sequence[str],
    suspected_providers: Sequence[str] | None = None,
    threshold: int = SILENT_HANG_ALERT_THRESHOLD,
) -> bool:
    """Fire a Telegram alert when `hang_count >= threshold`.

    Also attempts to populate the session-scoped provider exclusion set
    so OpenRouter routes away from the degraded backend for the rest of
    the run (recovery happens mid-session instead of waiting on the next
    daily scan). Exclusion is conditional on at least two distinct
    agents hanging on the same provider slug.

    Returns True when a Telegram alert was sent, False otherwise.
    """
    if hang_count < threshold:
        return False

    # Populate the session-scoped provider exclusion set BEFORE the Telegram
    # attempt — the routing adjustment is valuable even if Telegram config
    # is missing or the send fails.
    unique_agents = sorted(set(hang_agents))
    excluded = _populate_provider_exclusions(hang_agents, suspected_providers)

    if not excluded:
        # Reached on EVERY threshold-crossing alert today: a hop timeout
        # fires before OpenRouter reports the serving upstream, so
        # `downstream_provider` is structurally None on every timeout path
        # (SWI-370) and there is never a slug safe to add — the model
        # author is deliberately NOT excluded (it would be a fleet-wide
        # kill switch when every agent shares one author; 2026-05-15
        # incident). Make that gap observable instead of silent: recovery
        # for the hop-timeout class relies on RetryModel retries +
        # FallbackModel rollover + OpenRouter re-routing, NOT on the
        # dynamic exclusion set.
        logger.warning(
            "SILENT_HANG_NO_EXCLUDABLE_UPSTREAM hang_count=%d phase=%s agents=%s "
            "— no downstream upstream identified; author slug intentionally not "
            "excluded; recovery relies on retry + fallback rollover.",
            hang_count,
            phase,
            unique_agents,
        )

    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        logger.warning(
            "SILENT_HANG_ALERT_SUPPRESSED hang_count=%d phase=%s (Telegram env missing)",
            hang_count,
            phase,
        )
        return False

    try:
        from shared.telegram import send_telegram_error
    except ImportError:
        logger.warning("SILENT_HANG_ALERT_UNAVAILABLE shared.telegram import failed")
        return False

    exclusion_line = (
        f" Excluded providers for rest of session: {', '.join(excluded)}." if excluded else ""
    )
    message = (
        f"[PIPELINE HEALTH] Silent provider hangs: {hang_count} agents in "
        f"{phase} on {scan_date}. "
        f"Affected: {', '.join(unique_agents)}.{exclusion_line} "
        f"Threshold={threshold}; MON-2026-04-19-008 class. Review Logfire "
        f"`silent_provider_hang` spans for first-byte timing."
    )
    try:
        send_telegram_error(message)
    except Exception as exc:  # network / bot errors should not break pipeline exit
        logger.warning("SILENT_HANG_ALERT_SEND_FAILED %s", exc)
        return False
    return True


def _populate_provider_exclusions(
    hang_agents: Sequence[str],
    suspected_providers: Sequence[str] | None,
) -> list[str]:
    """Add suspected OpenRouter serving-upstream slugs to the session exclusion set.

    `suspected_providers` carries downstream upstream slugs only (e.g.
    `together`, `siliconflow`) — the producer (`emit_silent_provider_hang_span`)
    drops the model-author slug so an exclusion can never take the whole
    fleet offline (2026-05-15 incident). The list is therefore frequently
    empty: silent first-byte hangs arrive before OpenRouter reports which
    upstream served, so there is nothing to exclude.

    Rule: an upstream enters the exclusion set only when it hung at least
    two distinct agents — one-off hangs are noise. Returns the sorted list
    of slugs that were added (for alert-message inclusion).
    """
    if not suspected_providers:
        return []
    counts = Counter(slug.lower() for slug in suspected_providers if isinstance(slug, str) and slug)
    recurring = sorted({slug for slug, n in counts.items() if n >= PROVIDER_EXCLUSION_MIN_HANGS})
    if not recurring:
        return []
    try:
        from shared.session import add_provider_exclusion
    except ImportError:
        logger.warning("PROVIDER_EXCLUSION_UNAVAILABLE shared.session import failed")
        return []
    for slug in recurring:
        add_provider_exclusion(slug)
    if len(set(hang_agents)) < SILENT_HANG_ALERT_THRESHOLD:
        logger.info(
            "PROVIDER_EXCLUSION_LOW_CONFIDENCE distinct_agents=%d (<%d) providers=%s",
            len(set(hang_agents)),
            SILENT_HANG_ALERT_THRESHOLD,
            recurring,
        )
    return recurring
