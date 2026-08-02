"""SWI-201: catalyst news spike dedup tests."""

from __future__ import annotations

from shared.rules.catalyst_news import build_signals


def _articles(titles: list[str]) -> list[dict]:
    return [{"title": title} for title in titles]


def test_unique_count_collapses_recycled_headlines() -> None:
    titles = [
        "Trump threatens Hormuz blockade",
        "Trump-threatens-Hormuz-blockade!",
        "TRUMP threatens hormuz blockade.",
        "Trump threatens Hormuz blockade",
    ]
    signals = build_signals(
        matches={"trump_hormuz_xx": [0, 1, 2, 3]},
        articles=_articles(titles),
        catalysts=[{"catalyst_key": "trump_hormuz_xx", "event": "Hormuz blockade"}],
        baselines={"trump_hormuz_xx": 0.0},
    )
    assert len(signals) == 1
    signal = signals[0]
    assert signal["article_count"] == 4
    # All four titles normalize to the same string.
    assert signal["unique_article_count"] == 1


def test_unique_count_distinct_titles() -> None:
    titles = [
        "Headline A",
        "Headline B",
        "Headline C",
    ]
    signals = build_signals(
        matches={"k1": [0, 1, 2]},
        articles=_articles(titles),
        catalysts=[{"catalyst_key": "k1", "event": "x"}],
        baselines={"k1": 0.0},
    )
    assert signals[0]["unique_article_count"] == 3


def test_spike_uses_unique_count() -> None:
    """Spike threshold computed against unique_article_count, not article_count."""
    titles = ["same headline"] * 10
    signals = build_signals(
        matches={"k1": list(range(10))},
        articles=_articles(titles),
        catalysts=[{"catalyst_key": "k1", "event": "x"}],
        baselines={"k1": 5.0},  # avg 5/day baseline
    )
    # 10 raw vs 1 unique — should NOT spike under 2x baseline=10 threshold on unique.
    assert signals[0]["unique_article_count"] == 1
    assert signals[0]["is_spike"] is False
