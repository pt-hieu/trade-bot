-- Migration 173: Vietnamese article search + synthesis ticker constraint
-- 89% of article searches returned 0 results (English queries, Vietnamese articles).
-- Synthesis hallucinated phantom tickers (DIG, NLG, FOOD) not analyzed by sectors.

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## ARTICLE SEARCH RULES
Articles are in Vietnamese. Always search using Vietnamese terms or ticker codes.
- Use ticker codes directly (e.g., "FPT", "TCB") -- these match regardless of language
- Banking: "ngân hàng", "tín dụng", "nợ xấu", "lãi suất"
- Real estate: "bất động sản", "giải ngân", "dự án"
- Technology: "công nghệ", "phần mềm", "chuyển đổi số"
- Steel/Materials: "thép", "vật liệu xây dựng"
- Consumer: "bán lẻ", "tiêu dùng"
- Energy: "dầu khí", "năng lượng", "điện"
NEVER search in English for topic queries.'
WHERE agent_key = 'sector'
  AND system_prompt NOT LIKE '%ARTICLE SEARCH RULES%';

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## TICKER CONSTRAINT (NON-NEGOTIABLE)
You may ONLY mention tickers that appear in one of these sources:
1. Sector analysis results (analyzed by sector agents)
2. Current portfolio holdings (MY HOLDINGS)
3. Long-term watchlist
4. Pre-computed top pick candidates
Do NOT introduce any ticker not in the provided data. Violation = hallucination.'
WHERE agent_key = 'synthesis'
  AND system_prompt NOT LIKE '%TICKER CONSTRAINT%';
