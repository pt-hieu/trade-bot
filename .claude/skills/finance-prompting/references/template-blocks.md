# Finance Prompting — Template Blocks Reference

Full prompt template blocks for copy-paste into agent prompts. See `instructions.md` for blocks 1-3.

---

### 4. Bull/Bear Balance Requirement

```
## BULL/BEAR BALANCE
For every recommendation, the KEY RISK / risks field must be the strongest counter-argument:
- BULLISH recommendation → KEY RISK argues for caution (what could invalidate this)
- BEARISH/DEFENSIVE stance → KEY RISK names what opportunity you'd miss
Never present KEY RISK as a minor footnote. It must genuinely challenge the thesis.
This counterbalances systematic bullish bias documented in LLM financial analysis.
```

### 5. Abstinence Rule

```
## INSUFFICIENT DATA RULE
If the data needed to support a claim is missing, stale, zero-valued, or unverifiable:
  output: "INSUFFICIENT DATA — [what's missing, what would be needed]"
Do NOT infer, extrapolate, or generate plausible-sounding analysis from memory.
A blank / skipped analysis is better than a fabricated one.
Applies to: price comparisons, ratio calculations, pattern identifications, any factual claim.
```

### 6. Data Citation Requirement

```
## SOURCE CITATION
For every numerical claim, cite which tool or pre-computed field provided the value:
- Format: "RSI 42 [tool_get_technicals]" or "R:R 3.2 [pre_computed.trade_setup]"
- For derived values: show the formula — "R:R = (114-107)/(107-101) = 1.17 ❌"
- Mark any inferred/estimated values with [ESTIMATED]
If you cannot attribute a number to a data source, do NOT include it.
```

### 7. Chain-of-Verification (CoVe)

```
## VERIFICATION STEP
After generating your analysis:
1. Re-read each factual claim
2. For each claim: can you trace it to a specific provided data field?
3. Remove or flag any claim that failed verification with [UNVERIFIED]
4. If >30% of claims are UNVERIFIED: output "INSUFFICIENT DATA" for this ticker
```

### 8. Structured Output Schema (Pydantic)

```python
from pydantic import BaseModel, Field
from typing import Literal

class SignalOutput(BaseModel):
    ticker: str
    signal: Literal["BUY", "WATCH", "WAIT", "AVOID"]  # Constrained enum
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    thesis: str = Field(description="2-3 sentences, qualitative only")
    bull_case: str = Field(description="Strongest argument for the signal")
    bear_case: str = Field(description="Strongest counter-argument")
    data_sources_cited: list[str] = Field(description="Tool names or field paths used")
    conflicts_identified: list[str] = Field(description="Any contradictory signals found")
    conflict_resolution: str = Field(description="How conflicts were weighed")
```

### 9. Few-Shot Example Block

```xml
<good_example>
[Your best example of the exact output format you want]

<reasoning>
Good because: [specific reasons — data cited, format correct, conflict resolved]
</reasoning>
</good_example>

<bad_example>
[Common failure mode you want to prevent]

<reasoning>
Bad because: [what's wrong — vague, invented numbers, no conflict handling]
</reasoning>
</bad_example>
```

### 10. Objectivity + Anti-Bullish-Bias Rules

```
## OBJECTIVITY RULE
If data shows no clear setup: output WAIT or AVOID — never stretch marginal signals.
A brief with 0 picks is better than a brief with forced picks.
Systematic bullish bias: LLMs trained on financial text overweight upside.
Counter it by actively seeking the bear case before concluding.
SKIP / NO RECOMMENDATION is always a valid output.
```
