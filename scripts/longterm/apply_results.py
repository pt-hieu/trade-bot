"""Apply LLM results and screen VN30 candidates for long-term review."""

import asyncio
from datetime import date

from shared.api.fundamentals import get_financial_ratios_batch
from shared.api.prices import get_prices
from shared.longterm_calculations import (
    adjust_conviction,
    apply_entry_zone_adjustment,
    screen_candidates,
)
from shared.moat import classify_overall_moat, score_moat_from_ratings
from shared.neon.longterm import (
    add_longterm_stock,
    deactivate_longterm_stock,
    mark_longterm_reviewed,
    update_longterm_conviction,
    update_longterm_entry_zone,
    upsert_company_research,
    upsert_moat_assessment,
)
from shared.thesis_tracker import record_thesis_update, upsert_thesis

# VN30 universe for candidate screening
VN30_TICKERS = [
    "ACB",
    "BCM",
    "BID",
    "BVH",
    "CTG",
    "FPT",
    "GAS",
    "GVR",
    "HDB",
    "HPG",
    "MBB",
    "MSN",
    "MWG",
    "NLG",
    "PLX",
    "POW",
    "SAB",
    "SHB",
    "SSB",
    "SSI",
    "STB",
    "TCB",
    "TPB",
    "VCB",
    "VHM",
    "VIB",
    "VIC",
    "VJC",
    "VNM",
    "VPB",
]

VN30_SECTOR_MAP = {
    "ACB": "banking",
    "BCM": "real_estate",
    "BID": "banking",
    "BVH": "consumer",  # no insurance sector in DB; Bao Viet is diversified financial
    "CTG": "banking",
    "FPT": "technology",
    "GAS": "state_owned",
    "GVR": "state_owned",
    "HDB": "banking",
    "HPG": "infrastructure",
    "MBB": "banking",
    "MSN": "consumer",
    "MWG": "consumer",
    "NLG": "real_estate",
    "PLX": "state_owned",
    "POW": "state_owned",
    "SAB": "consumer",
    "SHB": "banking",
    "SSB": "banking",
    "SSI": "securities",
    "STB": "banking",
    "TCB": "banking",
    "TPB": "banking",
    "VCB": "banking",
    "VHM": "real_estate",
    "VIB": "banking",
    "VIC": "consumer",
    "VJC": "consumer",
    "VNM": "consumer",
    "VPB": "banking",
}


async def screen_vn30_candidates(existing_tickers: set[str]) -> list[dict]:
    """Fetch VN30 ratios and screen for potential additions."""
    candidate_tickers = [t for t in VN30_TICKERS if t not in existing_tickers]
    if not candidate_tickers:
        return []

    ratios_batch = await get_financial_ratios_batch(candidate_tickers)
    candidates = screen_candidates(ratios_batch, existing_tickers, VN30_SECTOR_MAP)

    if candidates:
        tickers = [c["ticker"] for c in candidates]
        api_prices = await get_prices(tickers)
        for c in candidates:
            entry = api_prices.get(c["ticker"])
            c["current_price"] = int(round(entry["close"] * 1000)) if entry else None

    return candidates


async def _apply_stock_review(stock_res, deterministic: dict[str, dict]) -> dict:
    """Apply a single stock's LLM review to DB. Returns per-stock changes."""
    changes: dict[str, list] = {
        "entry_adjusted": [],
        "conviction_adjusted": [],
    }
    ticker = stock_res.ticker.upper()

    sections = {
        "overview": stock_res.overview,
        "moat": stock_res.moat,
        "growth": stock_res.growth,
        "risks": stock_res.risks,
        "valuation": stock_res.valuation,
        "thesis": stock_res.thesis,
    }
    await upsert_company_research(ticker, sections, auto_generated=True)

    if stock_res.moat_assessment:
        moat_dict = stock_res.moat_assessment.model_dump(exclude={"moat_evidence"})
        moat_dict["moat_score"] = score_moat_from_ratings(moat_dict)
        moat_dict["overall_moat"] = classify_overall_moat(moat_dict["moat_score"])
        moat_dict["assessed_at"] = str(date.today())
        await upsert_moat_assessment(ticker, moat_dict)

    if stock_res.thesis_pillars:
        pillars = [p.model_dump() for p in stock_res.thesis_pillars]
        kill_criteria = (
            [k.model_dump() for k in stock_res.kill_criteria] if stock_res.kill_criteria else []
        )
        await upsert_thesis(ticker, pillars, kill_criteria)
        await record_thesis_update(
            ticker,
            source="monthly_review",
            pillar_changes=pillars,
            kill_criteria_changes=kill_criteria,
        )

    det = deterministic.get(ticker, {})

    adj_pct = stock_res.entry_zone_adjustment_pct
    if adj_pct != 0 and det.get("entry_zone_vnd"):
        new_entry = apply_entry_zone_adjustment(det["entry_zone_vnd"], adj_pct)
        await update_longterm_entry_zone(ticker, new_entry, "llm")
        changes["entry_adjusted"].append(
            f"{ticker} {adj_pct:+.1f}% ({stock_res.entry_zone_reason[:50]})"
        )

    conv_adj = stock_res.conviction_adjustment
    if conv_adj != 0 and det.get("conviction"):
        new_conviction = adjust_conviction(det["conviction"], conv_adj)
        det_score = det.get("score") or 30
        await update_longterm_conviction(ticker, new_conviction, det_score, "llm")
        changes["conviction_adjusted"].append(
            f"{ticker} {det['conviction']}->{new_conviction} ({stock_res.conviction_reason[:50]})"
        )

    await mark_longterm_reviewed(ticker)
    return changes


async def apply_llm_results(llm_result, deterministic: dict[str, dict]) -> dict:
    """Apply LLM review results to DB. Returns summary of changes made."""
    changes = {
        "research_updated": [],
        "entry_adjusted": [],
        "conviction_adjusted": [],
        "added": [],
        "deactivated": [],
    }

    # Process existing stock reviews concurrently
    review_tasks = [_apply_stock_review(sr, deterministic) for sr in llm_result.stocks]
    review_results = await asyncio.gather(*review_tasks)

    for stock_res, per_stock in zip(llm_result.stocks, review_results, strict=False):
        changes["research_updated"].append(stock_res.ticker.upper())
        changes["entry_adjusted"].extend(per_stock["entry_adjusted"])
        changes["conviction_adjusted"].extend(per_stock["conviction_adjusted"])

    # Process additions
    for addition in llm_result.additions:
        ticker = addition.ticker.upper()
        success = await add_longterm_stock(
            ticker=ticker,
            sector=addition.sector,
            entry_zone_vnd=addition.suggested_entry_zone_vnd,
            conviction=addition.suggested_conviction,
            tier=addition.suggested_tier,
            entry_zone_method="llm",
            conviction_method="llm",
        )
        if success:
            await upsert_company_research(
                ticker,
                {"thesis": addition.thesis},
                auto_generated=True,
            )
            changes["added"].append(f"{ticker} ({addition.sector})")

    # Process removals
    for removal in llm_result.removals:
        ticker = removal.ticker.upper()
        await deactivate_longterm_stock(ticker)
        changes["deactivated"].append(f"{ticker}: {removal.reason[:80]}")

    return changes
