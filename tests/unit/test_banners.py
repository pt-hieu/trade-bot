"""Tests for the centralized banner helper.

Group 11 of 2026-04-19 pipeline review fixes.
"""

from __future__ import annotations

from pipeline.rendering.banners import (
    Banner,
    BannerPriority,
    critic_missing_banner,
    render_banners,
)


def test_empty_returns_empty_string():
    assert render_banners([]) == ""


def test_single_banner_renders_with_prefix():
    banner = Banner(BannerPriority.CRITICAL_DATA_GAP, "Critic missing")
    out = render_banners([banner])
    assert out.startswith("⚠ Critic missing")
    assert out.endswith("\n\n")


def test_priority_ordering_critical_first():
    info = Banner(BannerPriority.INFO, "Info note")
    streak = Banner(BannerPriority.STREAK_ALERT, "0-BUY streak day 5")
    critical = Banner(BannerPriority.CRITICAL_DATA_GAP, "Critic missing")
    out = render_banners([info, streak, critical])
    lines = out.strip().split("\n")
    assert lines[0].startswith("⚠ ")
    assert lines[1].startswith("📉 ")
    assert lines[2].startswith("ℹ ")


def test_deduplicates_by_text():
    duplicate = Banner(BannerPriority.STREAK_ALERT, "0-BUY streak day 5")
    out = render_banners([duplicate, duplicate])
    assert out.count("0-BUY streak day 5") == 1


def test_critic_missing_banner_has_critical_priority():
    banner = critic_missing_banner()
    assert banner.priority == BannerPriority.CRITICAL_DATA_GAP


def test_critic_plus_streak_both_render():
    banners = [
        critic_missing_banner(),
        Banner(BannerPriority.STREAK_ALERT, "0-BUY streak day 5"),
    ]
    out = render_banners(banners)
    assert "Critic could not verify" in out
    assert "0-BUY streak day 5" in out
    # Critical above streak
    critic_idx = out.find("Critic")
    streak_idx = out.find("0-BUY")
    assert critic_idx < streak_idx
