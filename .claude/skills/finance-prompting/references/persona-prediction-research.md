# Persona-Based LLM Prediction Systems — Research Notes

Research compiled 2026-03-21 for designing prediction-making agents in Swingy's multi-agent pipeline.

---

## 1. LLM Agents + Prediction Markets

### AIA Forecaster (Nov 2025) — State of the Art

**Architecture:** Three-layer pipeline:
1. Agentic search over high-quality news sources with iterative query refinement
2. Supervisor agent examines reasoning traces from individual forecasting agents, identifies disagreements, conducts targeted clarifying searches, then reconciles into unified forecast
3. Platt scaling post-hoc calibration pushes probabilities toward extremes (0 or 1)

**Prediction format:** Binary probability p in [0,1], scored via Brier score (p - o)^2.

**Results:** Brier score 0.1076 on ForecastBench — statistically indistinguishable from human superforecasters (0.1110). Ensembling 10 independent runs (simple average) was critical: single runs scored 0.1182 vs 0.1140 ensemble.

**Key insight:** The supervisor agent pattern — not just averaging, but having a dedicated agent examine disagreements and resolve them through targeted search — is directly applicable to our sector/positions ensembles.

Paper: https://arxiv.org/abs/2511.07678

### Fake Prediction Markets as Confidence Signals (Dec 2025)

**Architecture:** Multiple LLM instances generate predictions and assign confidence scores as implicit "bets." Confidence-weighted aggregation replaces simple averaging — agents with higher conviction get proportionally more influence. Uses Kelly criterion principles for optimal bet sizing under uncertainty.

**Results:** Across 5,400 predictions, incentive-based runs showed 81.5% vs 79.1% accuracy (p=.089, d=0.86) and significantly faster learning across rounds.

**Key insight:** Each analyst can "bet" conviction on their prediction. A technical analyst highly confident about a breakout pattern gets more weight than a fundamental analyst uncertain about earnings. More nuanced than equal-weight averaging.

Paper: https://arxiv.org/pdf/2512.05998

### KalshiBench — Epistemic Calibration (Dec 2025)

**Architecture:** 300 binary prediction market questions from Kalshi (CFTC-regulated), filtered to resolve after model training cutoffs.

**Key finding:** ALL models showed systematic overconfidence, ECE ranging 0.120–0.395. Extended reasoning paradoxically degraded calibration (GPT-5.2-XHigh had worst ECE=0.395 despite comparable accuracy). Only one of five models beat base-rate prediction.

**Key insight:** Post-hoc calibration (Platt scaling or temperature scaling) is mandatory, not optional. LLMs consistently assign higher probabilities than warranted.

Paper: https://arxiv.org/html/2512.16030v1

---

## 2. Multi-Agent Debate/Prediction Ensemble Systems

### Wisdom of the Silicon Crowd (Science Advances, 2024)

**Architecture:** 12 diverse LLMs (7B to ~1.6T parameters, proprietary + open-source, from 6 countries) each prompted identically as a "superforecaster with a strong track record." Each model queried 3x independently. Aggregation: simple median across all models per question.

**Prompt:** Instructed to employ chain-of-thought reasoning while considering base rates, comparison classes, and competing evidence.

**Results:** Ensemble of 12 LLMs was statistically indistinguishable from a crowd of 925 human forecasters. When GPT-4 and Claude 2 received the human crowd median, accuracy improved 17% and 28% respectively. Simple average of human+machine forecasts beat model updating.

**Key insight:** Diversity of perspective matters more than individual model quality. Having genuinely different analytical lenses (technical, fundamental, macro, news) mirrors the diversity that makes crowds wise.

Paper: https://arxiv.org/abs/2402.19379

### TradingAgents Framework (Dec 2024) — Most Directly Relevant

**Architecture (7 roles mirroring a real trading firm):**
1. **Fundamental Analyst** — evaluates financial statements, earnings, insider transactions
2. **Sentiment Analyst** — social media data, sentiment scores, insider sentiment
3. **News Analyst** — articles, macroeconomic indicators, company announcements
4. **Technical Analyst** — 60+ indicators (MACD, RSI, Bollinger Bands)
5. **Bullish Researcher** — advocates for opportunities after reviewing all analyst reports
6. **Bearish Researcher** — identifies risks and downside concerns
7. **Trader Agent** — reviews analyst reports + researcher debate conclusions, makes buy/sell/hold

Plus **Risk Management Team** (aggressive/neutral/conservative perspectives) and **Fund Manager** for final approval.

**Debate mechanism:** Bullish and Bearish researchers engage in n-round natural language debate. A facilitator agent reviews debate history, selects prevailing perspective, records structured outcome. Risk Management similarly debates from three risk profiles.

**Prediction format:** Structured reports with key metrics, insights, and recommendations — buy/sell/hold with rationale.

**Results:** 23.21%+ cumulative return on AAPL/GOOGL/AMZN backtests (Jan-Mar 2024), Sharpe ratios of 5.60+.

**Config:** Uses LangGraph. Adjustable: `llm_provider`, `deep_think_llm`, `quick_think_llm`, `max_debate_rounds`.

Paper: https://arxiv.org/abs/2412.20138 | Code: https://github.com/TauricResearch/TradingAgents

### Multi-Agent Debate Performance (ICLR 2025)

**Key finding:** Simple majority voting already achieves most performance gains of multi-agent debate (MAD), particularly when agents are homogeneous. The value of debate emerges when agents have genuinely different information or analytical frameworks — which is exactly our setup with specialized analyst personas.

Source: https://d2jud02ci9yv69.cloudfront.net/2025-04-28-mad-159/blog/mad/

---

## 3. Superforecasting Techniques for LLMs

### AI-Augmented Predictions (MIT/LSE, 2024)

**Prompt structure based on Tetlock's 10 Commandments:**
1. Triage problems by tractability
2. Break intractable problems into tractable sub-problems
3. Balance inside view (specific case analysis) vs outside view (reference class/base rates)
4. Ground initial estimates in base rates, then adjust
5. Calibrate confidence levels explicitly
6. Identify causal forces and weight them

**Prediction format:** Binary events: probability 0–100 to 2 decimal places. Continuous outcomes: point estimate + uncertainty interval.

**Results:** LLM assistant improved human forecasting accuracy by 23–43%.

Paper: https://arxiv.org/abs/2402.07862

### Prompt Engineering for Forecasting (Jun 2025)

**Techniques tested:**
- **Superforecaster persona prompt** — "you are a seasoned superforecaster"
- **Scratchpad prompt** — explicit chain-of-thought decomposition workspace
- **Base rate anchoring** — force model to state prior probability before adjusting

**Key finding:** Specific prompt structure matters significantly but inconsistently across models. Most robust approach combines persona framing + explicit decomposition steps + base rate anchoring.

Paper: https://arxiv.org/pdf/2506.01578

### ForecastBench Trajectory (Current)

**Current standings:** GPT-4.5 achieves Brier 0.101, superforecasters 0.081 (25% gap). LLM performance improves ~0.016 Brier points per year. Linear extrapolation: LLM-superforecaster parity around November 2026.

Source: https://www.forecastbench.org/ | https://forecastingresearch.substack.com/p/ai-llm-forecasting-model-forecastbench-benchmark

---

## 4. Financial Prediction with LLM Agents

### LLM Agent Market Simulation (Apr 2025) — Persona Adherence Study

**Persona definitions via system prompts:**
- **Value Investor:** "focuses on fundamental analysis, tries to buy undervalued assets"
- **Momentum Trader:** "follows price trends and volume, believes trend is your friend"
- **Market Maker:** "provides liquidity by capturing bid-ask spread"

**Structured prediction output (Pydantic-validated JSON):**
```
valuation_reasoning: str  # numerical analysis
valuation: float          # estimated intrinsic value
price_target_reasoning: str
price_target: float       # predicted next-round price
```

**Critical finding:** LLMs demonstrate consistent strategy adherence — they reliably follow persona instructions regardless of profit implications. They "do not inherently optimize for profit maximization but rather for following instructions accurately." Persona-based prediction is viable: agents WILL think from their assigned analytical lens.

**Market dynamics:** Price discovery works, but agents correct undervaluation more effectively than they pop bubbles. Asymmetric convergence.

Paper: https://arxiv.org/html/2504.10789v1

### ElliottAgents (Jun 2025) — Multi-Agent Technical Analysis

**7 agents in sequential pipeline:** Coordinator → Data Engineer → Elliott Wave Analyst → Backtester → Technical Analysis Expert → Investment Advisor → Reports Writer.

**Prediction format:** Buy/sell/hold + entry price + target price + stop-loss + timeframe.

**RAG integration:** Knowledge graph-based RAG provides external context to reduce hallucinations in Elliott Wave pattern interpretation.

Paper: https://arxiv.org/html/2506.16813v1

---

## 5. Prediction Tracking and Calibration

### Calibration Game (Aug 2025) — Zero-Parameter Improvement

**Architecture:** Prompt-based calibration framework where LLMs play rounds of a confidence game. Each round: answer question, state confidence (50–99%), receive feedback on alignment between stated confidence and actual correctness.

**Feedback loop:** Three phases:
1. Pre-game baseline
2. Game rounds with aggregate performance summaries (current score, mean confidence, calibration status)
3. Post-game re-evaluation with history

Model observes whether it's overconfident/underconfident and self-adjusts — no weight updates needed.

**Confidence bins:** {50, 60, 70, 80, 90, 99} with exponential scoring (steeper penalties for wrong high-confidence answers).

**Results:** Brier score reductions of 1.97%–13.60% across models.

Paper: https://arxiv.org/html/2508.14390v1

### Platt Scaling for LLM Probabilities

**Technique:** Fit logistic regression `p_calibrated = 1/(1 + exp(A*f(x) + B))` on held-out data where f(x) is raw LLM probability output. Pushes probabilities toward extremes, correcting systematic underconfidence-in-extremes / overconfidence-in-middle.

**AIA Forecaster result:** Platt coefficient of sqrt(3) ~ 1.73 was optimal, improving Brier from 0.1140 to 0.1076.

**Implementation:** Accumulate (prediction, outcome) pairs over time. Periodically refit A and B. Apply transformation to all new predictions.

### Inverse Softmax Trick for Verbalized Probabilities (Oct 2024)

**Problem:** LLMs output verbalized probabilities (e.g., "75%") that are poorly calibrated. Directly applying temperature scaling is mathematically wrong.

**Solution:** Convert verbalized probabilities to estimated logits via inverse softmax (log p_i + c), apply temperature scaling to logits, re-normalize. Optimal temperature typically 0.6–1.7.

**Results:** ECE improvements of 1–8 percentage points. Claude-v3 achieved 1.0% ECE on IMDB.

Paper: https://arxiv.org/html/2410.06707v1

---

## Design Principles Extracted

| Principle | Source | Implication for Swingy |
|-----------|--------|------------------------|
| Personas reliably adhered to | Can LLMs Trade? | Technical/fundamental/news split will work |
| Supervisor > simple average | AIA Forecaster | Aggregator should examine disagreements, not just merge |
| Overconfidence is universal | KalshiBench | Must apply Platt scaling to all probability outputs |
| Calibration via prompt works | Calibration Game | Feed each agent its own accuracy history |
| Conviction-weighting wins | Going All-In | Let agents "bet" confidence, weight accordingly |
| Diversity is the multiplier | Silicon Crowd | Different lenses >> same lens repeated |
| Bull/bear debate catches blindspots | TradingAgents | Add dialectical step for high-stakes picks |
| Base rate anchoring improves forecasts | AI-Augmented Predictions | Force agents to state prior before adjusting |
| Ensemble multiple runs helps | AIA Forecaster | Even same-agent benefits from averaging 5–10 samples |
| Extended reasoning can hurt calibration | KalshiBench | More thinking ≠ better calibrated probabilities |
