# Company Research Playbook

Interactive workflow for populating `company_profiles` DB table with structured business knowledge.

## Critical Rules

1. **Canonical macro factors ONLY.** The `factor` field in `macro_sensitivities` MUST be one of exactly 21 keys:
   - Commodities: `oil_price`, `steel_price`, `iron_ore`, `copper`, `rubber`
   - Monetary: `interest_rate`, `credit_growth`
   - FX: `usd_vnd`, `dxy`
   - Investment: `fdi`, `public_investment`
   - Trade partners: `china_demand`, `us_demand`, `japan_demand`
   - Regulatory: `land_law`, `banking_regulation`, `npl_rules`, `securities_regulation`
   - Technology: `ai_disruption`
   - Sentiment: `vix`, `global_risk`

   Free-text factor names BREAK GIN index queries in `resolve_tickers_by_macro_factor()`.

2. **Enum fields are strict.** No synonyms, no lowercase.
   - `direction`: `POSITIVE` | `NEGATIVE` | `MIXED`
   - `magnitude`: `HIGH` | `MEDIUM` | `LOW`
   - `moat`: `WIDE` | `NARROW` | `NONE`
   - `pricing_power`: `HIGH` | `MEDIUM` | `LOW`

3. **Percentages are integers 0-100.**
   - `sum(revenue_segments[].pct_revenue)` ≈ 100
   - `export_split.domestic_pct + sum(exports[].pct_revenue)` ≈ 100
   - `pct_cost` values don't need to sum to 100

4. **Never invent numbers.** Use user estimates or flag for review. Do not hallucinate percentages from training data.

5. **source = "research"** for skill-generated profiles. Do NOT include `sector_id` — auto-resolved from `stocks` table.

6. **Verify ticker exists** via `get_company_knowledge` MCP tool before starting research.

---

## Step 1: Check Existing Profile

Call `get_company_knowledge` MCP tool with the ticker.

| Result | Action |
|--------|--------|
| Profile exists | Show current profile → ask "Update specific fields, or full re-research?" |
| No profile | Proceed to Step 2 |
| Error (invalid ticker) | Stop — ticker not in `stocks` table |

---

## Step 2: Gather User Input

Accept any level of detail. User may provide:
- Business description
- Revenue segments with approximate %
- Key input costs and sourcing
- Export vs domestic split
- Known macro sensitivities
- Competitive advantages

After ingesting, identify gaps across the 7 schema fields:

| # | Field | Required? |
|---|-------|-----------|
| 1 | `business_summary` | Yes |
| 2 | `revenue_segments` | Yes |
| 3 | `supply_chain` | Yes |
| 4 | `export_split` | Yes |
| 5 | `macro_sensitivities` | Yes (minimum 1 entry) |
| 6 | `regulatory_exposure` | Optional |
| 7 | `competitive_position` | Optional but recommended |

---

## Step 3: Web Research (Fill Gaps Only)

Do NOT re-research what the user provided with confidence. Target missing fields.

### Search Strategy (3-5 queries per ticker)

| Query Template | Purpose |
|---------------|---------|
| `"{TICKER}" annual report revenue breakdown` | Revenue segments |
| `"{TICKER}" supply chain raw materials imports` | Supply chain inputs |
| `"{TICKER}" export markets domestic revenue` | Export split |
| `"{TICKER}" market share competitors Vietnam` | Competitive position |
| `"{TICKER}" Vietnam stock company overview` | Business summary |

### Source Priority
1. Annual reports / investor relations
2. Vietnamese financial sites (cafef.vn, vietstock.vn)
3. Broker research (SSI, HSC, VNDirect)
4. English coverage (Bloomberg, Reuters)

### Supplementary MCP Data
- `get_financials` — revenue/margin data for grounding segment estimates
- `compare_financials` — sector peers for competitive position context

---

## Step 4: Cross-Check User Claims

If user provided specific numbers, compare against research:

| Scenario | Action |
|----------|--------|
| Match (within ~5pp) | Accept user's number |
| Mismatch (>5pp) | Present both sources, let user decide |
| No research data found | Use user's estimate, flag confidence |

**Never silently override user claims.** Always surface discrepancies.

---

## Step 5: Structure the Profile

Build the exact JSONB schema:

```json
{
    "business_summary": "1-2 sentences describing core business",
    "revenue_segments": [
        {"name": "Segment Name", "pct_revenue": 60, "description": "Brief description"}
    ],
    "supply_chain": [
        {"input": "Iron Ore", "source_countries": ["Australia", "Brazil"], "pct_cost": 40}
    ],
    "export_split": {
        "domestic_pct": 85,
        "exports": [
            {"market": "Southeast Asia", "pct_revenue": 10},
            {"market": "US", "pct_revenue": 5}
        ]
    },
    "macro_sensitivities": [
        {
            "factor": "steel_price",
            "direction": "POSITIVE",
            "magnitude": "HIGH",
            "explanation": "Core product — steel price directly drives revenue and margins"
        }
    ],
    "regulatory_exposure": [
        {
            "policy": "Anti-dumping duties",
            "impact": "POSITIVE",
            "description": "Protects domestic market from cheap Chinese imports"
        }
    ],
    "competitive_position": {
        "market_share": "~35% domestic crude steel",
        "moat": "WIDE",
        "pricing_power": "MEDIUM",
        "description": "Largest integrated steel producer with Dung Quat complex"
    }
}
```

### Validation Checklist
- [ ] All `factor` values from 21 canonical keys
- [ ] All enum values match exact allowed values
- [ ] `pct_revenue` sums to ~100 in `revenue_segments`
- [ ] `domestic_pct + export pcts` sums to ~100
- [ ] `business_summary` is 1-2 sentences
- [ ] No `sector_id` field

---

## Step 6: User Review

Present the structured profile as JSON. Flag:
- Low-confidence fields (estimated from partial data)
- Fields where user input conflicted with research
- Any empty or placeholder values

Iterate until user approves.

---

## Step 7: Upsert to Database

Execute via inline script:

```bash
uv run python -c "
import sys; sys.path.insert(0, 'scripts')
import json
from shared.neon.company_profiles import upsert_company_profile_sync
profile = json.loads('''PROFILE_JSON_HERE''')
upsert_company_profile_sync('TICKER', profile, source='research')
print('Done: TICKER profile upserted')
"
```

After upsert, verify by calling `get_company_knowledge` MCP tool.

---

## Step 8: Batch Continuation

After completing a ticker: "Next ticker, or done?"

If user provides a list upfront, work through sequentially — each ticker gets Steps 1-7.

---

## Update Mode

When existing profile detected (Step 1):
1. Show current profile
2. Ask which fields to update
3. Research only changed fields
4. Merge: keep unchanged fields, replace updated ones
5. Upsert (version auto-increments via ON CONFLICT)

---

## Macro Sensitivity Guidelines

### Direction Logic

| Scenario | Direction |
|----------|-----------|
| Rising factor HELPS company | `POSITIVE` |
| Rising factor HURTS company | `NEGATIVE` |
| Effect depends on conditions | `MIXED` |

### Magnitude Logic

| Magnitude | Guideline |
|-----------|-----------|
| `HIGH` | >10% revenue/margin impact from moderate factor movement |
| `MEDIUM` | 5-10% impact, or indirect but significant |
| `LOW` | <5% impact, or very indirect linkage |

### Common Vietnamese Stock Mappings (starting points — always verify)

| Sector | Typical Factors |
|--------|----------------|
| Steel (HPG, NKG, HSG) | `steel_price` POS HIGH, `iron_ore` NEG HIGH, `china_demand` POS MED |
| Banks (TCB, VCB, MBB) | `interest_rate` MIXED HIGH, `credit_growth` POS HIGH, `npl_rules` NEG MED |
| Real estate (VHM, NLG, KDH) | `interest_rate` NEG HIGH, `land_law` MIXED HIGH |
| Tech/IT (FPT) | `us_demand` POS MED, `japan_demand` POS MED, `usd_vnd` POS MED |
| Oil & gas (GAS, PLX, PVD) | `oil_price` POS HIGH |
| Exporters | `usd_vnd` POS MED (weaker VND helps) |

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/shared/neon/company_profiles.py` | `upsert_company_profile()`, `get_company_profile()` |
| `scripts/shared/macro_factors.py` | Canonical 21 factor keys + keyword index |
| `scripts/shared/rules/catalyst_override/geolabel.py` | Uses profiles for article→ticker tagging |
| `scripts/pipeline/context_blocks_ticker.py` | Injects macro_sensitivities into agent context |
| `scripts/agents/tools/company_profiles.py` | Agent tool prose format |

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `trading-context` | How profile feeds into trading analysis |
| `database` | Schema changes needed |
| `data-layer` | Data tier rules for `shared.neon` module |
| `mcp-server` | MCP tool updates |
| `pipeline-workflows` | How the catalyst-override rules use profiles |
