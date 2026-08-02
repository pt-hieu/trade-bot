"""Boost-gate logic for the catalyst override.

Covers the LOW-confidence passthrough (APPROACHING/APPROACHING_RESOLUTION
lifecycle only, with corroboration minimum) and the regression guards for
the existing HIGH/MEDIUM path.

Mocks resolve_phase_status at the rule boundary so tests don't depend on
date arithmetic and phase-period parsing.
"""

from __future__ import annotations

from unittest.mock import patch

from shared.rules.catalyst_lifecycle import PhaseStatus
from shared.rules.catalyst_override import CatalystInput, get_catalyst_boosted_tickers


def _catalyst(
    *,
    confidence: str,
    has_phases: bool = True,
    article_count: int = 0,
    tickers: list[str] | None = None,
    impact: str = "POSITIVE",
) -> CatalystInput:
    """Build a CatalystInput. Actual phase content is irrelevant — the phase
    lifecycle is mocked separately via _patched_status()."""
    phases: dict | None = {"immediate_shock": {"dummy": True}} if has_phases else None
    return CatalystInput(
        catalyst_key="test_key",
        event="Test event",
        impact=impact,
        confidence=confidence,
        affected_tickers=tickers or ["VHM"],
        phases=phases,
        supporting_article_count=article_count,
    )


def _patched_status(lifecycle: str) -> PhaseStatus:
    return PhaseStatus(
        phase_name="immediate_shock",
        phase_info={"impact": "POSITIVE", "behavior": "rally"},
        days_active=1,
        lifecycle=lifecycle,  # type: ignore[arg-type]
    )


def test_high_with_approaching_resolution_included():
    with patch(
        "shared.rules.catalyst_override.resolve_phase_status",
        return_value=_patched_status("APPROACHING_RESOLUTION"),
    ):
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="HIGH")])
    assert "VHM" in boosted


def test_medium_with_approaching_included():
    with patch(
        "shared.rules.catalyst_override.resolve_phase_status",
        return_value=_patched_status("APPROACHING"),
    ):
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="MEDIUM")])
    assert "VHM" in boosted


def test_low_with_approaching_resolution_and_two_articles_included():
    """New path: LOW passes when lifecycle is APPROACHING_RESOLUTION and
    corroboration count >= _BOOST_LOW_MIN_ARTICLES (2)."""
    with patch(
        "shared.rules.catalyst_override.resolve_phase_status",
        return_value=_patched_status("APPROACHING_RESOLUTION"),
    ):
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="LOW", article_count=3)])
    assert "VHM" in boosted


def test_low_with_approaching_and_one_article_excluded():
    """Corroboration gate: single-source LOW rumors stay out."""
    with patch(
        "shared.rules.catalyst_override.resolve_phase_status",
        return_value=_patched_status("APPROACHING"),
    ):
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="LOW", article_count=1)])
    assert "VHM" not in boosted


def test_low_with_active_lifecycle_excluded_even_with_many_articles():
    """Lifecycle gate: LOW only passes in the APPROACHING windows.
    ACTIVE + LOW stays out regardless of corroboration — stale LOW signal."""
    with patch(
        "shared.rules.catalyst_override.resolve_phase_status",
        return_value=_patched_status("ACTIVE"),
    ):
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="LOW", article_count=10)])
    assert "VHM" not in boosted


def test_low_with_recently_expired_excluded():
    """RECENTLY_EXPIRED is in the HIGH/MEDIUM eligible set but NOT the LOW one."""
    with patch(
        "shared.rules.catalyst_override.resolve_phase_status",
        return_value=_patched_status("RECENTLY_EXPIRED"),
    ):
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="LOW", article_count=10)])
    assert "VHM" not in boosted


def test_high_with_recently_expired_included():
    """Regression guard: HIGH + RECENTLY_EXPIRED still passes (grace window)."""
    with patch(
        "shared.rules.catalyst_override.resolve_phase_status",
        return_value=_patched_status("RECENTLY_EXPIRED"),
    ):
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="HIGH")])
    assert "VHM" in boosted


def test_low_non_phased_excluded():
    """No-phases LOW has no lifecycle window to anchor the boost — skip."""
    boosted = get_catalyst_boosted_tickers(
        [_catalyst(confidence="LOW", has_phases=False, article_count=5)]
    )
    assert "VHM" not in boosted


def test_medium_non_phased_included():
    """No-phases MEDIUM still passes via the STATIC path."""
    boosted = get_catalyst_boosted_tickers([_catalyst(confidence="MEDIUM", has_phases=False)])
    assert "VHM" in boosted


def test_negative_impact_excluded():
    """Corroboration gate doesn't apply to non-positive catalysts."""
    with patch(
        "shared.rules.catalyst_override.resolve_phase_status",
        return_value=_patched_status("APPROACHING_RESOLUTION"),
    ):
        boosted = get_catalyst_boosted_tickers(
            [_catalyst(confidence="LOW", impact="NEGATIVE", article_count=5)]
        )
    assert "VHM" not in boosted


def test_unexpected_confidence_logs_and_skips():
    """Unknown confidence values fail loudly (warning) and are skipped."""
    with patch("shared.rules.catalyst_override.logger") as mock_logger:
        boosted = get_catalyst_boosted_tickers([_catalyst(confidence="UNKNOWN")])
    assert "VHM" not in boosted
    mock_logger.warning.assert_called_once()
