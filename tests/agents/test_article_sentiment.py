"""Eval set for the LLM article-sentiment scorer (SWI-103).

Marked `live_llm` so it's skipped by default — run with
    `uv run pytest tests/agents/test_article_sentiment.py -m live_llm`
when validating the model. CI keeps it offline.

Pass criteria (per plan):
- ≥85% sign match (sentiment_score sign matches expected)
- confidence distribution is sane: not >50% abstain, not 100% high
"""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest

pytestmark = pytest.mark.live_llm

EVAL_CASES: list[dict] = [
    # Positive-polarity cuts (burden ↓ → +)
    {
        "title": "Quốc hội thông qua giảm thuế xăng từ 5/2026",
        "summary": "NA passes fuel tax cut.",
        "expected_sign": +1,
    },
    {
        "title": "Cắt giảm thủ tục hành chính cho doanh nghiệp",
        "summary": "Government cuts business administrative procedures.",
        "expected_sign": +1,
    },
    {
        "title": "Giảm lãi suất điều hành 0.25%",
        "summary": "SBV cuts policy rate by 25bps.",
        "expected_sign": +1,
    },
    {
        "title": "Giảm phí trước bạ ô tô sản xuất trong nước",
        "summary": "Registration fee cut for domestic-assembled cars extended.",
        "expected_sign": +1,
    },
    {
        "title": "Đề xuất bỏ điều kiện kinh doanh không cần thiết",
        "summary": "Deputy PM proposes scrapping unnecessary business conditions.",
        "expected_sign": +1,
    },
    # Migrated from intl test
    {
        "title": "Markets rally on dovish Fed signals",
        "summary": "Markets rally on dovish Fed signals.",
        "expected_sign": +1,
    },
    {
        "title": "Fed signals rate cut in September meeting",
        "summary": "Fed signals rate cut in September meeting.",
        "expected_sign": +1,
    },
    # Negative-polarity cuts (benefit ↓ → −)
    {
        "title": "Lợi nhuận Q1 giảm 30% so với cùng kỳ",
        "summary": "Q1 profit down 30% YoY.",
        "expected_sign": -1,
    },
    {
        "title": "Doanh thu sụt giảm mạnh do nhu cầu yếu",
        "summary": "Revenue drops sharply on weak demand.",
        "expected_sign": -1,
    },
    {
        "title": "GDP quý 1 thấp hơn dự báo",
        "summary": "Q1 GDP misses forecast.",
        "expected_sign": -1,
    },
    {
        "title": "Công ty cắt giảm 500 nhân sự",
        "summary": "Company lays off 500 employees.",
        "expected_sign": -1,
    },
    # Migrated
    {
        "title": "Recession fears grow as unemployment rises",
        "summary": "Recession fears grow as unemployment rises.",
        "expected_sign": -1,
    },
    # Pure positive
    {
        "title": "FPT báo lãi kỷ lục quý 1",
        "summary": "FPT reports record Q1 profit.",
        "expected_sign": +1,
    },
    {
        "title": "VNINDEX vượt mốc 1400 điểm",
        "summary": "VNINDEX breaks above 1400.",
        "expected_sign": +1,
    },
    # Pure negative
    {
        "title": "ECB hawkish stance signals tighten ahead",
        "summary": "ECB hawkish stance signals tighten ahead.",
        "expected_sign": -1,
    },
    {
        "title": "EU áp lệnh trừng phạt mới",
        "summary": "EU imposes new sanctions.",
        "expected_sign": -1,
    },
    # Abstain cases
    {
        "title": "Công ty A công bố báo cáo tài chính Q1",
        "summary": "Company A publishes Q1 financial statements.",
        "expected_sign": 0,
    },
    {
        "title": "Đại hội cổ đông thường niên 2026",
        "summary": "Annual general meeting 2026 held.",
        "expected_sign": 0,
    },
    {
        "title": "Doanh thu tăng nhưng biên lợi nhuận giảm",
        "summary": "Revenue up but margin down.",
        "expected_sign": 0,
    },
]


@pytest.mark.asyncio
async def test_article_sentiment_eval():
    from agents.article_sentiment import score_article_sentiment

    async def _one(case: dict) -> tuple[int, str]:
        result = await score_article_sentiment(
            {"title": case["title"], "summary": case["summary"], "url": "test"}
        )
        if result is None:
            return 0, "abstain"
        if result.confidence == "abstain":
            return 0, "abstain"
        sign = 1 if result.sentiment_score > 0.05 else (-1 if result.sentiment_score < -0.05 else 0)
        return sign, result.confidence

    results = await asyncio.gather(*(_one(c) for c in EVAL_CASES))
    sign_matches = sum(
        1
        for case, (got_sign, _) in zip(EVAL_CASES, results, strict=True)
        if got_sign == case["expected_sign"]
    )
    pass_rate = sign_matches / len(EVAL_CASES)
    confs = Counter(c for _, c in results)
    abstain_pct = confs.get("abstain", 0) / len(EVAL_CASES)
    high_pct = confs.get("high", 0) / len(EVAL_CASES)

    assert pass_rate >= 0.85, f"sign-match pass rate {pass_rate:.2f} below 0.85 floor: {results}"
    assert abstain_pct <= 0.5, f"abstain rate {abstain_pct:.2f} > 0.5 — scorer too cautious"
    assert high_pct < 1.0, "all-high confidence is suspicious — scorer not calibrating"
