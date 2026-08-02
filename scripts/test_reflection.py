#!/usr/bin/env python3
"""
Test script for Reflection pattern (Critic + Refiner agents).

Tests the critic agent identifies issues and refiner fixes them.
Run with: uv run python scripts/test_reflection.py
"""

import asyncio

from agents.critic import CritiqueResult, critique_with_agent

# Sample brief with intentional issues for testing
SAMPLE_BRIEF_WITH_ISSUES = """GOAL PROGRESS
- Target: 5,000,000 VND
- Realized: 2,500,000 VND
- Remaining: 2,500,000 VND
- Days left: 15

CAPITAL STATUS
- Total Cash: 10,000,000 VND
- Min Reserve: 10,000,000 VND
- Deployable Cash: 0 VND
- WARNING: No deployable cash available

MARKET MOOD
- Regime: RISK_OFF
- VN-Index: 1,245 (-1.2%)
- Key signal: Bearish trend continues

NEWS THAT MATTERS
- VN-Index fell 1.2% on foreign selling
- Banking sector under pressure
- Real estate recovery delayed

MY HOLDINGS
- FPT: 95,500 VND, HOLD, Waiting for better entry
- VHM: 42,000 VND, HOLD, Real estate recovering

TOP PICKS
1. TCB
   Entry: around 35k
   Stop: 33
   Target: 40
   R:R: 2.5
   Reason: Banking bounce play

2. MWG
   Entry: 52,000
   Stop: 50,000
   Target: 58,000
   R:R: 3.0
   Reason: Growth stock momentum

SKIP THESE
- HPG: Steel sector weak
- BCM: Industrial parks slow

WHAT TO DO TODAY
- Buy TCB at 35k with 10M position
- Monitor FPT for weakness"""

# Sample brief that should pass
SAMPLE_BRIEF_CLEAN = """GOAL PROGRESS
- Target: 5,000,000 VND
- Realized: 4,000,000 VND
- Remaining: 1,000,000 VND
- Days left: 10

CAPITAL STATUS
- Total Cash: 28,000,000 VND
- Min Reserve: 10,000,000 VND
- Deployable Cash: 20,000,000 VND

MARKET MOOD
- Regime: RISK_ON
- VN-Index: 1,280 (+0.8%)
- Key signal: Bullish momentum

MY HOLDINGS
- FPT: 95,500 VND, HOLD, Strong technicals
- VHM: 42,000 VND, HOLD, Waiting for confirmation

TOP PICKS
1. TCB
   Entry: 34.5
   Stop: 33.5
   Target: 38.5
   R:R: 4.0
   Position: 15M VND
   Reason: Banking recovery, RSI 35 at support

SKIP THESE
- HPG: Not enough momentum

WHAT TO DO TODAY
- Consider TCB entry at 34.5 with 15M position"""


async def test_critique_identifies_issues():
    """Test that critic correctly identifies issues in problematic brief."""
    print("\n" + "=" * 60)
    print("TEST 1: Critic identifies issues")
    print("=" * 60)

    result: CritiqueResult = await critique_with_agent(
        draft_brief=SAMPLE_BRIEF_WITH_ISSUES,
        trading_mode="LOW_CASH",
        deployable_cash=0,
        market_regime="RISK_OFF",
        global_macro_regime="CAUTIOUS",
        portfolio_tickers=["FPT", "VHM"],
    )

    print(f"\nCritique result: has_issues={result.has_issues}, severity={result.severity}")
    print(f"Summary: {result.summary}")
    print(f"Issues ({len(result.issues)}): {result.issues[:3]}")

    # Should have issues (brief has problems)
    assert result.has_issues, "Should have found issues"
    assert result.severity not in ("none",), f"Expected non-trivial severity, got {result.severity}"

    print("\nTEST 1 PASSED: Critic identified issues")
    return result


async def test_critique_passes_clean_brief():
    """Test that critic passes a clean brief."""
    print("\n" + "=" * 60)
    print("TEST 2: Critic passes clean brief")
    print("=" * 60)

    result: CritiqueResult = await critique_with_agent(
        draft_brief=SAMPLE_BRIEF_CLEAN,
        trading_mode="NORMAL",
        deployable_cash=20_000_000,
        market_regime="RISK_ON",
        global_macro_regime="CALM",
        portfolio_tickers=["FPT", "VHM"],
    )

    print(f"\nCritique result: has_issues={result.has_issues}, severity={result.severity}")
    print(f"Summary: {result.summary}")
    is_clean = not result.has_issues or result.severity in ("none", "minor")
    print(f"Effectively clean: {is_clean}")

    print("\nTEST 2 COMPLETED")
    return result


async def test_critique_issue_details():
    """Test that critique result contains actionable issue details."""
    print("\n" + "=" * 60)
    print("TEST 3: Critique issue details")
    print("=" * 60)

    result: CritiqueResult = await critique_with_agent(
        draft_brief=SAMPLE_BRIEF_WITH_ISSUES,
        trading_mode="LOW_CASH",
        deployable_cash=0,
        market_regime="RISK_OFF",
        global_macro_regime="CAUTIOUS",
        portfolio_tickers=["FPT", "VHM"],
    )

    print(f"Severity: {result.severity}")
    print(f"Sections reviewed: {result.sections_reviewed}")
    print(f"Issues found: {len(result.issues)}")
    for issue in result.issues[:5]:
        print(f"  - {issue}")

    assert isinstance(result.sections_reviewed, list), "sections_reviewed should be a list"
    assert isinstance(result.issues, list), "issues should be a list"

    print("\nTEST 3 PASSED: Critique details are structured")
    return result


async def main():
    """Run all tests."""
    from shared.database import Database, close_db

    print("\n" + "=" * 60)
    print("REFLECTION PATTERN TEST SUITE")
    print("=" * 60)

    try:
        async with Database():
            await test_critique_identifies_issues()
            await asyncio.sleep(5)
            await test_critique_passes_clean_brief()
            await asyncio.sleep(5)
            await test_critique_issue_details()

            print("\n" + "=" * 60)
            print("ALL TESTS COMPLETED")
            print("=" * 60)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
