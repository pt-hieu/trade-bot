"""Top-of-brief banner helper.

Producers (critic-missing guard, streak alert, future health banners) push
``Banner(priority, text)`` records into a per-render list. The renderer
sorts by priority, deduplicates, and emits a single block at the top of
``morning-brief.md`` so multiple banners can coexist with a stable
ordering contract.

This is the single emit-point for all banners — no producer should write
banner Markdown directly into the brief body.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class BannerPriority(IntEnum):
    """Sort key. Lower values render first (most urgent on top)."""

    CRITICAL_DATA_GAP = 10  # critic missing, eval persistence gap
    STREAK_ALERT = 20  # 0-BUY streaks, drawdown streaks
    CAUTION = 30  # regime CAUTIOUS, low cash
    INFO = 40  # neutral notices


@dataclass(frozen=True)
class Banner:
    priority: BannerPriority
    text: str

    def render(self) -> str:
        prefix = {
            BannerPriority.CRITICAL_DATA_GAP: "⚠ ",
            BannerPriority.STREAK_ALERT: "📉 ",
            BannerPriority.CAUTION: "⚡ ",
            BannerPriority.INFO: "ℹ ",
        }[self.priority]
        return f"{prefix}{self.text}"


def render_banners(banners: list[Banner]) -> str:
    """Return a single Markdown block for the top of the brief.

    Sorts by priority (CRITICAL_DATA_GAP first), deduplicates by text,
    and returns an empty string when no banners are present so the brief
    body is never preceded by a stray newline.
    """
    if not banners:
        return ""
    seen: set[str] = set()
    ordered: list[Banner] = []
    for banner in sorted(banners, key=lambda b: (int(b.priority), b.text)):
        if banner.text in seen:
            continue
        seen.add(banner.text)
        ordered.append(banner)
    lines = [b.render() for b in ordered]
    return "\n".join(lines) + "\n\n"


def streak_alert_banner(streak_alert: dict) -> Banner:
    """Banner emitted on the morning after a 0-BUY streak ≥3 days.

    Reads the persisted blob from `daily_records.streak_alert_json`
    (written by retro). Text mentions length + gate profile so the
    operator immediately knows where to look.
    """
    length = streak_alert.get("length") or 0
    profile = streak_alert.get("gate_profile") or "unknown"
    text = f"{length}-day 0-BUY streak ({profile}). Verify entry gates aren't compounding."
    return Banner(priority=BannerPriority.STREAK_ALERT, text=text)


def critic_missing_banner() -> Banner:
    """Banner emitted when synthesis_picks ran but critic.final_result is None.

    The critic agent is `disable_fallback: true`; a silent provider hang
    leaves it without an output. Holdings actions still derive from the
    synthesizer's view, but readers must know the second-opinion check
    is missing today.
    """
    return Banner(
        priority=BannerPriority.CRITICAL_DATA_GAP,
        text=("Critic could not verify today's brief — treat holdings actions with extra caution."),
    )
