"""Catalyst coverage audit — diagnose INGEST_GAP vs TAGGER_GAP for always-zero tickers."""

import asyncio
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, "scripts")
from shared.database import Database

ZERO_TICKERS = ["HCM", "POW", "SAB", "VRE", "GVR", "DCM", "NT2"]
BOOSTED_TICKERS = ["BSR", "HDB", "VCB", "VHM", "VPB"]
ALL_TICKERS = ZERO_TICKERS + BOOSTED_TICKERS
WINDOW_START = date(2026, 4, 17)
WINDOW_END = date(2026, 5, 17)


async def main():
    async with Database() as db:
        # --- Universe check ---
        sw = await db.fetch_all(
            "SELECT ticker, is_active FROM swing_watchlist WHERE ticker = ANY($1)",
            ALL_TICKERS,
        )
        lt = await db.fetch_all(
            "SELECT ticker, is_active FROM longterm_watchlist WHERE ticker = ANY($1)",
            ALL_TICKERS,
        )
        in_swing = {r["ticker"]: r.get("is_active") for r in sw}
        in_lt = {r["ticker"]: r.get("is_active") for r in lt}

        # --- Article coverage (structured: affected_tickers array) ---
        article_counts_structured = {}
        article_counts_text = {}
        sample_articles = {}
        for t in ALL_TICKERS:
            # Structured tagging
            rows = await db.fetch_all(
                """
                SELECT COUNT(*) AS c FROM articles
                WHERE $1 = ANY(affected_tickers)
                  AND COALESCE(published_at, created_at) >= $2::date
                  AND COALESCE(published_at, created_at) < ($3::date + INTERVAL '1 day')
                """,
                t,
                WINDOW_START,
                WINDOW_END,
            )
            article_counts_structured[t] = int(rows[0]["c"]) if rows else 0

            # Text mention (word-boundary)
            rows_txt = await db.fetch_all(
                r"""
                SELECT COUNT(*) AS c FROM articles
                WHERE (title ~ ('\m' || $1 || '\M') OR summary ~ ('\m' || $1 || '\M'))
                  AND COALESCE(published_at, created_at) >= $2::date
                  AND COALESCE(published_at, created_at) < ($3::date + INTERVAL '1 day')
                """,
                t,
                WINDOW_START,
                WINDOW_END,
            )
            article_counts_text[t] = int(rows_txt[0]["c"]) if rows_txt else 0

            # Samples — prefer structured; if zero, use text
            samples = await db.fetch_all(
                r"""
                SELECT title, domain, COALESCE(published_at, created_at) AS pub, summary
                FROM articles
                WHERE ($1 = ANY(affected_tickers) OR title ~ ('\m' || $1 || '\M') OR summary ~ ('\m' || $1 || '\M'))
                  AND COALESCE(published_at, created_at) >= $2::date
                  AND COALESCE(published_at, created_at) < ($3::date + INTERVAL '1 day')
                ORDER BY COALESCE(published_at, created_at) DESC
                LIMIT 5
                """,
                t,
                WINDOW_START,
                WINDOW_END,
            )
            sample_articles[t] = [
                {
                    "title": s.get("title") or "",
                    "domain": s.get("domain") or "",
                    "pub": str(s.get("pub") or ""),
                    "summary": (s.get("summary") or "")[:240],
                }
                for s in samples
            ]

        # --- Catalyst rows per ticker (affected_tickers) ---
        catalyst_counts = {}
        for t in ALL_TICKERS:
            rows = await db.fetch_all(
                """
                SELECT COUNT(*) AS c FROM catalysts
                WHERE $1 = ANY(affected_tickers)
                  AND pipeline_version = 'v2'
                  AND created_at >= $2::date
                  AND created_at < ($3::date + INTERVAL '1 day')
                """,
                t,
                WINDOW_START,
                WINDOW_END,
            )
            catalyst_counts[t] = int(rows[0]["c"]) if rows else 0

        # --- Rejection trail ---
        rejection_counts = defaultdict(int)
        rejection_samples = defaultdict(list)
        rej_rows = await db.fetch_all(
            """
            SELECT event, candidate_type, reason, scan_date
            FROM catalyst_rejections
            WHERE scan_date >= $1::date AND scan_date <= $2::date
            """,
            WINDOW_START,
            WINDOW_END,
        )
        import re

        for r in rej_rows:
            ev = r.get("event") or ""
            for t in ALL_TICKERS:
                if re.search(rf"\b{t}\b", ev):
                    rejection_counts[t] += 1
                    if len(rejection_samples[t]) < 3:
                        rejection_samples[t].append(
                            {
                                "event": ev[:160],
                                "reason": r.get("reason") or "",
                                "scan_date": str(r.get("scan_date") or ""),
                            }
                        )

        # --- Verdict ---
        verdicts = {}
        for t in ALL_TICKERS:
            arts = article_counts_structured[t]
            arts_text = article_counts_text[t]
            cats = catalyst_counts[t]
            rejs = rejection_counts[t]
            if t in BOOSTED_TICKERS:
                verdicts[t] = "IN_PIPELINE_FINE"
            elif arts == 0 and arts_text == 0:
                verdicts[t] = "INGEST_GAP"
            elif arts == 0 and arts_text > 0:
                # Text-only mentions are usually false positives (HCM=Ho Chi Minh City,
                # POW=power-sector macro chatter, GVR appearing inside unrelated names).
                # The tagger correctly skipped them. Treat as INGEST_GAP for the
                # ticker-as-subject, not TAGGER_GAP.
                verdicts[t] = "INGEST_GAP"
            elif arts > 0 and cats == 0:
                verdicts[t] = "TAGGER_GAP" if rejs == 0 else "REJECTED"
            elif rejs > 0 and cats == 0:
                verdicts[t] = "REJECTED"
            else:
                verdicts[t] = "EXPECTED_NO_NEWS"

        # --- Report ---
        lines = []
        lines.append("# Catalyst Coverage Audit (2026-04-17 → 2026-05-17)\n")
        lines.append("## 1. Schema discovery\n")
        lines.append(
            "Tables touched: `articles` (structured `affected_tickers ARRAY`, plus title/summary text), "
            "`catalysts` (`affected_tickers ARRAY`), `catalyst_rejections` (free-text `event` field — no ticker column), "
            "`catalyst_articles` (junction catalyst_key↔article_id), `swing_watchlist`, `longterm_watchlist`.\n"
        )
        lines.append(
            "Article→ticker linkage = `articles.affected_tickers` array (set by upstream tagger before classifier).\n"
        )

        lines.append("\n## 2. Per-ticker coverage table\n")
        lines.append(
            "| Ticker | Bucket | Articles (tagged) | Articles (text-mention) | Catalyst rows | Conv % | In swing WL | In LT WL | Rejections |"
        )
        lines.append(
            "|--------|--------|-------------------|-------------------------|---------------|--------|-------------|----------|------------|"
        )
        for t in ALL_TICKERS:
            arts = article_counts_structured[t]
            arts_text = article_counts_text[t]
            cats = catalyst_counts[t]
            conv = f"{(100.0 * cats / arts):.0f}%" if arts > 0 else "n/a"
            sw_str = "Y" if in_swing.get(t) else ("inactive" if t in in_swing else "N")
            lt_str = "Y" if in_lt.get(t) else ("inactive" if t in in_lt else "N")
            bucket = "ZERO" if t in ZERO_TICKERS else "BOOSTED"
            lines.append(
                f"| {t} | {bucket} | {arts} | {arts_text} | {cats} | {conv} | {sw_str} | {lt_str} | {rejection_counts[t]} |"
            )

        lines.append("\n## 3. Verdict per ticker\n")
        for t in ALL_TICKERS:
            lines.append(f"- **{t}** → `{verdicts[t]}`")

        lines.append("\n## 4. Sample articles (tickers where articles exist)\n")
        for t in ALL_TICKERS:
            if not sample_articles[t]:
                continue
            lines.append(
                f"\n### {t} (verdict={verdicts[t]}, tagged={article_counts_structured[t]}, text={article_counts_text[t]})\n"
            )
            for s in sample_articles[t]:
                lines.append(f"- **{s['pub'][:10]}** [{s['domain']}] {s['title']}")
                if s["summary"]:
                    lines.append(f"  - _{s['summary']}_")

        lines.append("\n## 4b. Rejection samples\n")
        for t in ALL_TICKERS:
            if not rejection_samples[t]:
                continue
            lines.append(f"\n### {t}\n")
            for r in rejection_samples[t]:
                lines.append(f"- [{r['scan_date']}] reason=`{r['reason']}` event=`{r['event']}`")

        # Bucket counts
        buckets = defaultdict(list)
        for t in ZERO_TICKERS:
            buckets[verdicts[t]].append(t)
        lines.append("\n## 5. Branch verdict (7 always-zero tickers)\n")
        for b, ts in buckets.items():
            lines.append(f"- **{b}**: {len(ts)} → {', '.join(ts)}")

        verdict_summary = (
            "TAGGER_GAP"
            if len(buckets.get("TAGGER_GAP", [])) >= 4
            else "INGEST_GAP"
            if len(buckets.get("INGEST_GAP", [])) >= 4
            else "MIXED"
        )
        lines.append(f"\n**Dominant branch: {verdict_summary}**\n")

        lines.append("\n## 6. Concrete next actions\n")
        if verdict_summary == "TAGGER_GAP":
            lines.append(
                "1. Add sector exemplars (utilities, brokerages, beverages, rubber, fertilizer, retail) to catalyst-classifier few-shot prompt.\n"
            )
            lines.append(
                "2. Lower classifier impact threshold for mid-caps OR add `min_articles_per_watchlist_ticker` enforcement.\n"
            )
            lines.append(
                "3. Backfill: re-run classifier on existing articles for the 7 tickers to validate prompt fix before merging.\n"
            )
        elif verdict_summary == "INGEST_GAP":
            lines.append(
                "1. Audit `article_searches.query_name`: confirm utility/brokerage/retail queries actually run each scan.\n"
            )
            lines.append(
                "2. Add Vietnamese-sector news sources: cafef.vn (sector pages), vneconomy.vn (industries), ndh.vn.\n"
            )
            lines.append(
                "3. Add per-ticker watchlist-driven queries so any swing-watchlist ticker is guaranteed search coverage.\n"
            )
        else:
            lines.append(
                "1. Split fix into prompt-tweak for TAGGER_GAP tickers + sourcing for INGEST_GAP tickers (see per-ticker verdict).\n"
            )
            lines.append(
                "2. Verify tagger `affected_tickers` enrichment step runs on every article ingested (suspect mid-cap drop-off).\n"
            )
            lines.append(
                "3. Add per-watchlist-ticker article-count alert: any active swing ticker with <2 articles/14d triggers ingest review.\n"
            )

        report = "\n".join(lines)
        with open("tmp/catalyst_coverage_audit.md", "w") as f:
            f.write(report)

        # stdout summary (<600 words)
        print("=" * 70)
        print("CATALYST COVERAGE AUDIT — BUCKET COUNTS")
        print("=" * 70)
        for b, ts in buckets.items():
            print(f"  {b:20s} {len(ts)} → {', '.join(ts)}")
        print(f"\nDominant branch: {verdict_summary}")
        print("\nPer-ticker (zero-boost):")
        for t in ZERO_TICKERS:
            print(
                f"  {t}: articles_tagged={article_counts_structured[t]:3d}  text_mentions={article_counts_text[t]:3d}  "
                f"catalyst_rows={catalyst_counts[t]:3d}  rej={rejection_counts[t]}  → {verdicts[t]}"
            )
        print("\nBaseline (boosted):")
        for t in BOOSTED_TICKERS:
            print(
                f"  {t}: articles_tagged={article_counts_structured[t]:3d}  text_mentions={article_counts_text[t]:3d}  "
                f"catalyst_rows={catalyst_counts[t]:3d}"
            )
        print("\nTop 3 next actions:")
        if verdict_summary == "TAGGER_GAP":
            print(
                "  1. Add sector exemplars (utilities/brokerages/beverages/rubber/fertilizer/retail) to classifier prompt."
            )
            print(
                "  2. Backfill classifier over existing articles for the 7 tickers to validate fix."
            )
            print("  3. Add mid-cap-friendly impact threshold OR per-watchlist guarantee.")
        elif verdict_summary == "INGEST_GAP":
            print("  1. Audit article_searches.query_name for sector coverage gaps.")
            print("  2. Add cafef.vn/vneconomy.vn/ndh.vn sector sources.")
            print("  3. Add per-watchlist-ticker queries to guarantee coverage.")
        else:
            print("  1. Split fix: prompt-tweak for TAGGER_GAP tickers + sourcing for INGEST_GAP.")
            print("  2. Verify upstream tagger writes affected_tickers for every article.")
            print("  3. Add per-ticker article-count monitoring alert.")
        print("\nFull report: tmp/catalyst_coverage_audit.md")


if __name__ == "__main__":
    asyncio.run(main())
