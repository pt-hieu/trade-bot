# Context Injection Reference

Detailed tables, formatter code examples, and research citations for the inject-vs-tool-call decision framework. See `agent-development` instructions for the decision framework and key constraints.

---

## What To Inject (Batch-Fetch in Phase 0)

These are currently fetched via tools but should be pre-loaded and injected:

| Data | Current Tool | Agents Using It | Action |
|------|-------------|-----------------|--------|
| Holdings + P/L | `tool_get_holdings` | 10 agents | Inject as portfolio context block |
| Cash balance | `tool_get_cash` | 3 agents | Inject as single line |
| Market regime + history | `tool_get_regime`, `tool_get_history` | Phase 2+ agents | Inject Phase 1 output |
| Technicals (portfolio tickers) | `tool_get_technicals` | 7 agents | Already batch-fetched; inject |
| Prior beliefs | `tool_get_my_beliefs` | 6 agents | Pre-load per-ticker, inject |
| Catalyst preview | `tool_get_catalyst_preview` | 4 agents | Fetch once, inject |
| Article list (summaries) | `tool_list_articles` | 4 agents | Inject summaries; keep `tool_read_article` for deep-dive |
| Flow + insider + RS (portfolio) | `tool_get_flow`, `tool_get_insider`, `tool_get_relative_strength` | 5 agents | Batch-fetch, inject as enrichment block |
| Company profiles (known tickers) | `tool_get_company_profile` | 3 agents | Pre-load for portfolio + sector tickers |

---

## What Stays As Tools

| Tool Category | Why |
|---------------|-----|
| `tool_read_article` | Agent selects which article to deep-dive based on reasoning |
| `tool_search_articles` / `tool_search_news` | Keyword-driven, agent chooses search terms |
| `tool_get_learnings` | Query-based retrieval, agent frames context |
| `register_alert` / `list_active_alerts` / `remove_alert` | Write operations |
| `tool_get_similar_days` / `tool_trading_rules` / `tool_winning_patterns` / `tool_losing_patterns` | Pattern matching with agent-chosen conditions |
| `tool_get_financial_comparison` / `tool_get_comps` | Agent picks peer set |
| `tool_read_research` | Selective deep-dive |

---

## Injected Context Format vs Tool Returns

### Injected Context → Compact Structured Format

Prose wastes tokens. Agents need to scan injected data quickly, not read narratives. Use abbreviated key-value blocks and mini-tables.

```
# BAD — prose (wastes ~3x tokens)
"FPT is currently trading at 92,400 VND with an RSI of 42.3, which suggests
the stock is approaching oversold territory. The MACD has formed a bullish
crossover. Support is at 88,500 VND and resistance at 96,200 VND."

# GOOD — compact structured (~80 tokens)
## FPT | 92,400 VND
RSI: 42.3 (near oversold) | MACD: bullish crossover
Support: 88,500 | Resistance: 96,200
Flow: foreign net +2.1B (3d streak) | RS: 1.12 (outperforming)
P/L: +4.2% unrealized | Entry: 88,700 | Stop: 85,000
```

**Formatting rules for injected blocks:**
- One ticker per block, ticker + price as header
- Pipe-delimited key-value pairs on themed lines (technical, flow, position)
- Numbers with units, deltas in parentheses: `ROE: 18.2% (+1.3pp YoY)`
- No articles, no full sentences, no filler words
- Boolean states as tags: `(oversold)`, `(bullish crossover)`, `(3d streak)`

### Tool Returns → Prose Stays Valid

Tools that remain (search, deep-dive, pattern matching) serve qualitative reasoning. Agent already has structured context; tool adds narrative depth.

```python
# tool_read_article → prose is correct
"Vietnam's central bank signaled a 50bp rate cut in Q2, citing slowing
export growth. Banking sector rallied 2.3% on the news. Analysts at SSI
expect VCB and TCB to benefit most from margin expansion."

# tool_get_learnings → prose is correct
"Pattern: breakout entries on banking stocks after rate cut signals have
71% win rate over 15 instances. Average hold: 5.2 days. Key risk: reversals
when USD/VND spikes above 25,500."
```

**Rule of thumb:** If data is consumed as *facts to reference* → structured. If data is consumed as *reasoning to integrate* → prose.

---

## Context Block Builder Pattern (PydanticAI)

Each data type gets a dedicated formatter returning compact text:

```python
def format_portfolio_block(holdings: list[dict], cash: int) -> str:
    """≤500 tokens. Holdings + cash as scannable block."""
    lines = [f"## PORTFOLIO | Cash: {cash:,.0f} VND"]
    for holding in holdings:
        ticker = holding["ticker"]
        pnl_pct = holding.get("unrealized_pnl_pct") or 0
        lines.append(f"{ticker} | {holding['quantity']} shares | P/L: {pnl_pct:+.1f}%")
    return "\n".join(lines)

def format_regime_block(regime: dict, macro: dict) -> str:
    """≤200 tokens. Market regime + macro as single block."""
    return (
        f"## MARKET REGIME: {regime['classification']}\n"
        f"VN-Index: {regime['vnindex_close']:,.0f} | RSI: {regime['rsi']:.1f}\n"
        f"VIX: {macro['vix']:.1f} | DXY: {macro['dxy']:.1f} | USD/VND: {macro['usd_vnd']:,.0f}"
    )
```

Use `RunContext[PipelineContext]` dependency injection. Build context blocks in Python, inject via `@agent.system_prompt`:

```python
@agent.system_prompt
async def inject_context(context: RunContext[PipelineContext]) -> str:
    deps = context.deps
    blocks = [
        format_portfolio_block(deps.holdings, deps.cash),
        format_regime_block(deps.regime, deps.macro),
        format_ticker_briefing(deps.technicals, ticker),
    ]
    return "\n\n".join(blocks)
```

---

## Token Budget Per Block

| Block | Target | Contains |
|-------|--------|----------|
| Portfolio (holdings + cash) | ≤500 tokens | All positions with P/L, cash balance |
| Market regime + macro | ≤200 tokens | Classification, VN-Index, VIX, DXY, USD/VND |
| Ticker briefing (per ticker) | ≤300 tokens | Technicals, flow, insider, RS, valuation |
| Upstream agent summary | ≤500 tokens | Condensed output from Phase N-1 agent |
| Beliefs (per ticker) | ≤100 tokens | Prior direction, probabilities, accuracy |
| Article summaries | ≤400 tokens | Headlines + 1-line summaries, no full text |
| **Total per agent** | **≤2500 tokens** | Leaves 4.5K for role + instructions within 7K budget |

---

## Research Sources

- [Anthropic: Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic: Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic: Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Lost in the Middle (TACL 2024)](https://aclanthology.org/2024.tacl-1.9/)
- [Context Length Alone Hurts (arXiv:2510.05381)](https://arxiv.org/html/2510.05381v1)
- [Context Rot (Chroma Research 2025)](https://www.trychroma.com/research/context-rot)
- [AgentDiet: Trajectory Reduction (ACL 2025)](https://arxiv.org/html/2509.23586v1)
- [MarketSenseAI 2.0](https://arxiv.org/html/2502.00415v1)
