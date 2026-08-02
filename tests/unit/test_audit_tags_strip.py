"""Audit provenance tags — vocabulary + render-boundary strip invariant.

Data-layer provenance tags (`[DERIVED_FROM_BELIEFS]`,
`[RECONCILED_FROM_BELIEFS]`, `[NO_BELIEF_NO_REC]`) must NOT leak into
the user-facing brief body. Pipeline emits them into
`daily_recommendations.rationale` / `.verdict` for audit purposes;
render-layer callers must strip them before emission.
"""

from __future__ import annotations

from pipeline.rendering.models import HoldingAction
from pipeline.rendering.my_holdings import render_my_holdings
from pipeline.rendering.what_to_do_today import render_what_to_do_today
from shared.rules.audit_tags import (
    AUDIT_TAGS,
    DERIVED_FROM_BELIEFS,
    NO_BELIEF_NO_REC,
    RECONCILED_FROM_BELIEFS,
    strip_audit_tags,
)


class TestVocabulary:
    def test_expected_tags_registered(self):
        assert DERIVED_FROM_BELIEFS in AUDIT_TAGS
        assert RECONCILED_FROM_BELIEFS in AUDIT_TAGS
        assert NO_BELIEF_NO_REC in AUDIT_TAGS

    def test_tags_are_uppercase_bracketed_tokens(self):
        for tag in AUDIT_TAGS:
            assert tag.startswith("[")
            assert tag.endswith("]")
            assert tag == tag.upper()


class TestStrip:
    def test_strips_leading_tag(self):
        cleaned = strip_audit_tags(f"{DERIVED_FROM_BELIEFS} FPT momentum intact")
        assert cleaned == "FPT momentum intact"

    def test_strips_embedded_tag(self):
        cleaned = strip_audit_tags(f"View: {RECONCILED_FROM_BELIEFS} BULLISH")
        assert RECONCILED_FROM_BELIEFS not in cleaned
        assert "View:" in cleaned
        assert "BULLISH" in cleaned

    def test_strips_multiple_tags(self):
        raw = f"{DERIVED_FROM_BELIEFS} part one. {RECONCILED_FROM_BELIEFS} part two."
        cleaned = strip_audit_tags(raw)
        for tag in AUDIT_TAGS:
            assert tag not in cleaned

    def test_none_returns_empty(self):
        assert strip_audit_tags(None) == ""

    def test_no_tag_untouched(self):
        assert strip_audit_tags("plain prose") == "plain prose"


class TestHoldingsRender:
    def test_rationale_tag_stripped_in_brief(self):
        action = HoldingAction(
            ticker="FPT",
            verb="HOLD",
            qty_pct=None,
            entry_price_vnd=85_000,
            current_price_vnd=76_000,
            pnl_pct=-10.6,
            stop_price_vnd=None,
            catastrophic_floor_vnd=70_000,
            breakeven_stop_vnd=None,
            trailing_stop_vnd=None,
            urgency="MEDIUM",
            rationale=f"{DERIVED_FROM_BELIEFS} thesis intact; volume dry",
            geo_badge=None,
        )

        output = render_my_holdings([action])

        for tag in AUDIT_TAGS:
            assert tag not in output
        assert "thesis intact" in output

    def test_what_to_do_today_rationale_tag_stripped(self):
        action = HoldingAction(
            ticker="TCB",
            verb="TRIM",
            qty_pct=30,
            entry_price_vnd=30_000,
            current_price_vnd=32_000,
            pnl_pct=6.7,
            stop_price_vnd=28_000,
            catastrophic_floor_vnd=None,
            breakeven_stop_vnd=None,
            trailing_stop_vnd=None,
            urgency="HIGH",
            rationale=f"{RECONCILED_FROM_BELIEFS} degraded aggregator",
            geo_badge=None,
        )

        output = render_what_to_do_today([action])
        for tag in AUDIT_TAGS:
            assert tag not in output
        assert "degraded aggregator" in output
