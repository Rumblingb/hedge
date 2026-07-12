# Research Log — What's Been Done
## 2026-05-04 | Continuous Research Tracking

### COMPLETED RESEARCH (Don't re-do)

| Topic | Source | Key Findings | Applied |
|-------|--------|-------------|---------|
| WorldQuant 101 Alphas | Kakushadze (2015) | 10 alphas implemented (001,002,006,009,012,020,054,065,101) | ✅ |
| Top hedge fund architectures | Training data + arXiv | Renaissance/Two Sigma/Citadel/DE Shaw blueprints | ✅ docs |
| Chinese quant strategies | Training data + arXiv | High-Flyer/Ubiquant mean-reversion bias, overnight gap fade | ✅ |
| Korean/Japanese strategies | Training data | Retail-dominated patterns, BOJ intervention, KOSPI overnight reversal | ✅ |
| Man Group/AHL agentic fund | Training data | 100+ strat platform, 90% rejection, strategy-as-portfolio | ✅ |
| DE Shaw/Jump/AQR 2000-2020 | Training data | Stat arb, merger arb, risk parity, style premia, trend following | ✅ |
| Prediction markets | Training data + arXiv:0801.4047, 0607166, 1710.01786, 1210.4900, 2105.02782 | Kelly, Bayesian, AMM, Arb strategies | ✅ |
| Options | Training data | Greeks, Theta, Vega, Gamma, event-driven, futures-specific | ✅ |
| Commodities | Training data | Energy, Metals, Ag, Spreads, COT, Super-cycle | ✅ |
| Novel strategies | Training data + arXiv | Vanna/Charm, VPIN, Hawkes, Signature, Conformal, Causal | ✅ |
| Trend Alpha | Training data | Google Trends, Social, SEC, Consumer, Innovation signals | ✅ |
| Operational Architecture | Training data + arXiv | Workflow Stage 0-4, Circuit breakers, Risk management | ✅ |
| HMM Regime Detection | Built | 4-state HMM, 6 symbols, transition matrices | ✅ |
| Multi-factor Ranking | Built | ElasticNet + BMA, strategy correlation matrix | ✅ |
| Finnhub News/Sentiment | Built | 20 articles scored, bearish -0.194, event gate active | ✅ |

### IN-PROGRESS RESEARCH

| Topic | Status | Next Step |
|-------|--------|-----------|
| "Finding Alphas" paper | Searching | Extract systematic alpha discovery methodology |
| WorldQuant remaining 91 alphas | Planned | Implement best 20 more for futures |
| Human-AI Interactive Alpha Mining | Planned | AI agent + trading engine for alpha discovery |
| NLP for Alpha (Najera & Kantos) | Planned | FinBERT sentiment on earnings calls |
| Man Group AlphaGPT | Planned | AI translating research to Python for backtesting |
| Additional historical data | Needed | Yahoo Finance 5-year data pull |

### BREAKTHROUGH PAPERS FOUND (2026-05-04)

| Paper | Source | Key Innovation | Implementable? |
|-------|--------|---------------|----------------|
| AlphaAgent (arXiv:2502.16789) | Tang et al. 2025 | 3-agent LLM system (Idea→Code→Critic) with regularized exploration. Novelty/hypothesis/complexity constraints combat alpha decay. Outperforms genetic programming + prior LLM methods. | YES — multi-agent architecture, regularization loss for originality |
| AlphaLogics (arXiv:2603.20247) | Weng et al. 2026 | Market-logic-driven factor mining. Reverse-engineers WHY factors persist from historical libraries, then generates new factors guided by extracted logic. 3 components: Logic Mining, Factor Generation, Logic Validation. | YES — market logic library approach, logic-constrained generation |
| BrainAlpha (SSRN:6313578) | 2026 | End-to-end autonomous multi-agent system replicating full quant researcher workflow: hypothesis ideation → signal specification → expression generation → backtesting → portfolio construction. "Alpha decay is not a risk to be managed — it is an operational rate that must be outrun." | YES — full autonomous alpha pipeline architecture |
| AlphaLab (arXiv:2604.08590) | Hogan et al. 2026 | Autonomous research harness: data exploration → adversarial eval framework → GPU experiments via Strategist/Worker loop. Domain knowledge in persistent playbook. Model-generated adapters for domain-specific behavior. | PARTIALLY — playbook architecture, Strategist/Worker pattern |

### KEY INSIGHT FROM PAPERS

**Transformer limitation**: All 4 papers converge on the same finding — pure transformer/DL approaches produce homogeneous, crowded factors that decay fast. The winning approach is:
1. Market logic FIRST (why should this persist?)
2. Multi-agent collaboration (Idea + Code + Critic)
3. Regularization for originality (not just performance)
4. Persistent knowledge accumulation (playbooks, libraries)

This validates Rajiv's intuition: transformers reweight inputs based on attention patterns, but financial alpha needs direct feature relationships and economic rationale.

### ALPHA DECAY FRAMEWORK

From BrainAlpha: alpha decay is an OPERATIONAL RATE (signals lose ~30-50% predictive power per year). The only countermeasure is a faster alpha discovery pipeline than the decay rate. This means:
- Daily alpha generation (not monthly)
- Multi-agent automation (not manual research)
- Regularized novelty (not overfitting to backtests)

### RESEARCH QUEUE (Next Up)

1. "Finding Alphas" — Tulchinsky systematic alpha discovery
2. "151 Trading Strategies" — Zurak/Kovac comprehensive strategy catalog
3. ~~Human-AI Interactive Alpha Mining~~ → FOUND: Alpha-GPT (arXiv:2308.00016) + EMNLP 2025 demo
4. Generating Alpha using NLP Insights and Machine Learning
5. ~~Man Group — What AI Can Do for Alpha~~ → Found: AlphaAgent, AlphaLogics, BrainAlpha cover agentic approaches
6. QuantConnect algorithm library — top-performing community strategies
7. WorldQuant Challenge top solutions

### ADDITIONAL PAPERS FOUND VIA SEARXNG (2026-05-04 19:30 UTC)

| Paper | Source | Key Innovation | Implementable? |
|-------|--------|---------------|----------------|
| AlphaEvolve (arXiv:2103.16196) | Cui et al. 2021 ACM | AutoML-based alpha discovery. Generates alphas that predict returns with high accuracy in weakly correlated sets. | YES — AutoML pipeline for automated alpha generation |
| Alpha-GPT (arXiv:2308.00016) | Wang et al. 2023 EMNLP 2025 | Human-AI interactive alpha mining. Prompt engineering framework using LLMs to implement quant ideas as tradable signals. Bridge between quant intuition and code. | YES — prompt engineering for alpha generation, interactive loop |
| AlphaCFG (arXiv:2601.22119) | 2026 OpenReview | Grammar-constrained alpha discovery. Context-free grammar (α-CFG-Sem-k) defines syntactically valid formulas within bounded search space. Prevents invalid/semantically broken alphas. | YES — grammar definition for alpha syntax, bounded search |
| Synergistic RL Alphas (arXiv:2401.02710) | 2024 | RL-based synergistic alpha generation. Multiple alphas generated to work together, not in isolation. | YES — RL reward shaping for multi-alpha synergy |

### COMPLETE PAPER-TO-IMPLEMENTATION MAP

**Phase 1: Foundation (DONE)**
- 101 Formulaic Alphas (Kakushadze 2015) → 20 alphas implemented

**Phase 2: Grammar + AutoML (BUILD NEXT)**
- AlphaCFG → Define alpha grammar rules → prevents invalid formulas
- AlphaEvolve → AutoML pipeline → automated search over grammar space

**Phase 3: Multi-Agent Generation (BUILD AFTER)**
- AlphaAgent → 3-agent system: Idea → Code → Critic with originality regularization
- AlphaLogics → Market logic library → generate factors from extracted logic
- BrainAlpha → Full pipeline: hypothesis → signal → backtest → portfolio

**Phase 4: Interactive + Synergy (BUILD LAST)**
- Alpha-GPT → Human-AI prompt engineering for alpha ideation
- Synergistic RL → Multi-alpha optimization (not single-alpha greedy)


### DEEP RESEARCH: Scalping, Absorption, Options Premium, Cross-Asset
## 2026-05-05 | SearXNG Multi-Topic Deep Dive

---

### TOPIC 1: Profitable Scalping Strategy — Futures, 1-Minute, Quantitative

| # | Title | URL | Key Finding | Implementable? |
|---|-------|-----|-------------|----------------|
| 1 | Four Popular 1-Minute Scalping Strategies in 2026 (FXOpen) | https://fxopen.com/blog/en/1-minute-scalping-trading-strategies-with-examples/ | Scalping on 1-minute charts requires reacting to short bursts of order flow, momentum shifts, and volatility in real time. Covers 4 specific setups with indicator rules. | IMPLEMENTABLE-YES — entry/exit rules mappable to bar data; can produce StrategySignal with side/entry/stop/target from OHLCV |
| 2 | 1-Minute Scalping Strategy for Futures Traders (NinjaTrader) | https://ninjatrader.com/futures/blogs/1-minute-scalping-strategy-futures/ | Covers chart setup, order flow, entry precision, and risk management for active futures scalpers on 1-min timeframe. | IMPLEMENTABLE-YES — order flow based entries/exits with clear stop management logic |
| 3 | Scalping Futures: Strategies, Risks, and Trading Tips (QuantVPS) | https://www.quantvps.com/blog/scalping-futures-strategies | Involves executing 10-50 trades daily capturing 1-5 ticks per trade. Success hinges on speed, precision, and tight risk control. | IMPLEMENTABLE-YES — tick-based targets and stops are parameterizable in StrategySignal |
| 4 | The Automatic Cryptocurrency Trading System Using a Scalping Strategy (ResearchGate) | https://www.researchgate.net/publication/387434546 | Comparative analysis of scalping vs trend-following; demonstrates advantages of scalping in volatile markets with automated execution. | IMPLEMENTABLE-YES — academic comparison provides clear algorithmic framework for scalping signals |
| 5 | Profitability Without Complexity: A Breakout And Pullback Scalping Strategy (IJCRT) | https://ijcrt.org/papers/IJCRT2504775.pdf | Robust scalping using price action + VWAP confirmation + volume/OI filters on 15-second timeframe. 1% capital risk per trade, strict management. | IMPLEMENTABLE-YES — VWAP + volume/OI dual confirmation pattern is directly translatable to bar logic |

**Summary**: Most scalping literature is practitioner-oriented, not academic. Key algorithmic components: VWAP/EMA bias detection, MACD/RSI trigger confluence, ATR-based adaptive stops, volume spike filtering. All are implementable as Strategy classes since they produce directional signals from OHLCV data.

---

### TOPIC 2: Institutional Order Flow Absorption Detection Algorithm

| # | Title | URL | Key Finding | Implementable? |
|---|-------|-----|-------------|----------------|
| 1 | Institutional Footprint Scanner [JOAT] (TradingView) | https://www.tradingview.com/script/ltlg9fvx-Institutional-Footprint-Scanner-JOAT/ | Combines Order Flow Toxicity Index, Volume Profile POC, Absorption Coefficient analysis, and Smart Money Divergence to detect institutional activity through multi-dimensional microstructure analysis. | IMPLEMENTABLE-YES — toxicity, absorption coefficient, and divergence metrics are computable from bar/volume data |
| 2 | Orderflows Absorption Tool | https://www.orderflows.com/abs.html | Defines multi-level absorption: Extreme Absorption, Momentum Absorption, and Aggressive Absorption (combined). Identifies trapped traders and turning points. | IMPLEMENTABLE-YES — absorption classification rules can be encoded as signal triggers |
| 3 | GitHub: Mamallann/OrderFlow-absorption | https://github.com/Mamallann/OrderFlow-absorption | Comprehensive backtesting system for order flow trading strategies using footprint data. Detects absorption and shift patterns. | IMPLEMENTABLE-YES — open-source backtesting framework with absorption detection algorithms |
| 4 | QuantFlow Algo: Institutional Trap & Reversal (TradingView) | https://in.tradingview.com/script/yVm6V0HQ-QuantFlow-Algo-Institutional-Trap-Reversal/ | Proprietary Flow Engine analyzing instant shifts in market participation. Trap detection identifies institutional reversals via participation pattern shifts. | IMPLEMENTABLE-YES — flow engine logic can be simplified to delta + volume pattern analysis |
| 5 | VPIN: Volume-Synchronized Probability of Informed Trading | https://www.quantresearch.org/VPIN.pdf | Academic paper by Easley, Lopez de Prado, O'Hara. VPIN metric detects informed trading through volume-clock bucketing of order flow imbalance. Proven in flash crash prediction. | IMPLEMENTABLE-YES — VPIN algorithm is well-defined: volume buckets, imbalance classification, CDF-based toxicity metric |

**Key Algorithmic Insight**: Absorption detection converges on 3 signals:
1. **Delta absorption**: price moves against dominant delta (buying at lows, selling at highs)
2. **Volume-to-price divergence**: high volume at a level without price progression
3. **Toxicity metrics (VPIN)**: informed flow concentration in volume-time

All three are computable from bar-level OHLCV + volume data, making them implementable. A combined absorption score could trigger reversal entries.

---

### TOPIC 3: Options Selling — Premium Capture Strategy, Systematic

| # | Title | URL | Key Finding | Implementable? |
|---|-------|-----|-------------|----------------|
| 1 | A Study on Option-based Systematic Strategies (Monash University WP) | https://www.monash.edu/__data/assets/pdf_file/0011/2264438/WP_CQFIS_2020_1.pdf | Focuses on strategies selling OTM call options to harvest premium. Each option strategy consists of selling an OTM option with systematic rules for strike selection and roll timing. | IMPLEMENTABLE-YES — OTM strike selection rules + roll logic can be expressed as signal generation (but needs options chain data) |
| 2 | Systematic Index Option-Writing Strategies with Black-Scholes-Merton (ScienceDirect) | https://www.sciencedirect.com/science/article/abs/pii/S0264999325002299 | BSM model outperforms VG model in hedging. Systematic option writing generates superior risk-adjusted returns. Strategies tested: short calls, short puts, volatility spreads. | IMPLEMENTABLE-YES — BSM-based pricing + systematic writing rules are well-defined mathematically |
| 3 | Options Selling Strategy Using Machine Learning (SSRN 4766370) | https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4766370_code6587970.pdf | Dynamic standalone option selling using technical indicators, options Greeks, and ML models. Avoids directional bias by using signal-driven entry/exit. | IMPLEMENTABLE-YES — ML model can be simplified to rule-based Greek thresholds for StrategySignal output |
| 4 | Option Strategies: Good Deals and Margin Calls (UCLA Anderson) | https://www.anderson.ucla.edu/documents/areas/fac/finance/santa_clara_option.pdf | Systematic analysis of risks and returns of naked/covered positions, straddles. Identifies conditions where premium selling is profitable vs. when margin risk dominates. | IMPLEMENTABLE-YES — risk condition framework provides filtering rules for when to sell premium |
| 5 | Designing a Profitable Systematic Options Trading Strategy (NUS ScholarBank) | https://scholarbank.nus.edu.sg/entities/publication/ccfa0d3c-613e-4685-8a67-2f312b0c5ebb | Selling ITM options at 0.55 delta and exiting at 21 DTE increases returns and reduces risk. All tested across multiple market regimes. | IMPLEMENTABLE-YES — 0.55 delta entry + 21 DTE exit rule is directly codifiable |

**Critical Caveat**: Options strategies require Greeks data (delta, theta, vega, IV) and options chain access — not available in the current StrategyContext which only provides Bar (OHLCV). To implement these, the context would need to be extended with options data, OR the strategy would need to fetch options data internally. Current domain.ts only supports futures bars. **Can be implemented if options data adapter is added.**

---

### TOPIC 4: Cross-Asset Momentum Spillover / Lead-Lag Effects

| # | Title | URL | Key Finding | Implementable? |
|---|-------|-----|-------------|----------------|
| 1 | Cross-Asset Time-Series Momentum: Crude Oil Volatility and Global Stock (ScienceDirect) | https://www.sciencedirect.com/science/article/abs/pii/S0378426622002849 | Documents cross-asset momentum spillovers between crude oil volatility (OVX) and global stock returns. Lagged OVX changes predict stock returns with significance. | IMPLEMENTABLE-YES — lagged OVX → stock signal is a simple cross-asset rule: compute OVX change, generate signal on equity futures |
| 2 | Follow the Leader: Enhancing Systematic Trend-Following Using Network Momentum (arXiv:2501.07135) | https://arxiv.org/abs/2501.07135 | Combines univariate trend indicators with cross-sectional trend indicators capturing momentum spillover. Two lead-lag detection methods: rolling correlation and Granger causality. Applied to commodity futures. | IMPLEMENTABLE-YES — rolling correlation + Granger causality lead-lag detection is well-defined; generates signals on lagging assets when leaders move |
| 3 | Network Momentum across Asset Classes (arXiv:2308.11294) | https://arxiv.org/abs/2308.11294 | Pioneers momentum spillover across multiple asset classes using only pricing data. Presents multi-asset investment strategy exploiting network centrality as signal. | IMPLEMENTABLE-YES — network centrality from cross-correlation matrix is computable; leader assets trigger signals on connected laggards |
| 4 | Lead-Lag Relationships in Market Microstructure (SSRN 5043260) | https://papers.ssrn.com/sol3/Delivery.cfm?abstractid=5043260 | Investigates high-frequency cross-asset lead-lag using microstructure measures: price, liquidity, and order flow. Identifies which assets lead at sub-second frequencies. | IMPLEMENTABLE-YES — microstructure lead-lag metrics can be computed from high-frequency bar data |
| 5 | Considering Momentum Spillover via Graph Neural Network in Options (Wiley) | https://onlinelibrary.wiley.com/doi/abs/10.1002/fut.22506 | Proposes GNN-based proxy measuring correlated options' influence based on maturity date. Lead-lag effects in volatility connectedness captured by graph structure. | IMPLEMENTABLE-NO — requires GNN training infrastructure; not reducible to simple rule-based Strategy.generateSignal() |

**GitHub Reference**: https://github.com/leoamullins/cross-asset-leadlag-network — open-source implementation of network-based momentum strategy using directed graphs from rolling lagged correlations.

**Key Algorithmic Blueprint (from arXiv:2501.07135)**:
1. Compute rolling cross-correlation matrix across all tracked futures symbols
2. For each pair, determine lead-lag via max correlation at lag k (1-20 bars)
3. Build directed graph: edge A→B means A leads B
4. When A generates a trend signal, propagate to lagging assets B with adjusted confidence
5. Centrality-weighted portfolio allocation

This is directly implementable since StrategyContext provides `history` (Bar[]) for all tracked symbols.

---

### TOPIC 5: Volatility Risk Premium (VRP) Selling Strategy — Futures/Options, Systematic

| # | Title | URL | Key Finding | Implementable? |
|---|-------|-----|-------------|----------------|
| 1 | Volatility Risk Premium Effect (Quantpedia) | https://quantpedia.com/strategies/volatility-risk-premium-effect/ | Implied volatility systematically exceeds realized volatility. Selling ATM short-term options earns 0.5-1.5% per day average returns. Quantified across multiple studies. | IMPLEMENTABLE-YES — IV vs RV comparison + ATM option selling with delta hedging is algorithmic |
| 2 | Understanding the Volatility Risk Premium (AQR Capital) | https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Understanding-the-Volatility-Risk-Premium.pdf | VRP strategy systematically sells options to underwrite financial insurance for profit. Option contracts are the mechanism; VRP is the structural alpha source. | IMPLEMENTABLE-YES — AQR's framework is well-documented; systematic selling rules with risk management |
| 3 | The Volatility Risk Premium: An Empirical Study on the S&P 500 Index (SSRN 3739933) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3739933 | Empirical validation of VRP in SPX options. Quantifies premium magnitude, persistence across regimes, and optimal selling tenor (30-45 DTE). | IMPLEMENTABLE-YES — 30-45 DTE selling window with delta-based strike selection |
| 4 | Harvesting Volatility Risk Premium with Equity Index Options (Springer) | https://link.springer.com/chapter/10.1007/978-3-031-86354-7_29 | VRP driven by institutional hedging + behavioral biases. Systematic opportunity for absolute returns. Covers risk management for tail events (volmageddon protection). | IMPLEMENTABLE-YES — tail risk management rules (VIX spike triggers, position size scaling) are well-specified |
| 5 | Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put-Writing (arXiv:2508.16598) | https://arxiv.org/pdf/2508.16598 | Compares Kelly criterion, VIX-scaled, and hybrid position sizing for put-writing strategies. Hybrid approaches outperform fixed-size writing in risk-adjusted terms. | IMPLEMENTABLE-YES — position sizing rules from VIX level are directly codable |

**QuantConnect Reference Implementation**: https://www.quantconnect.com/research/15382/volatility-risk-premium-effect/ — working algorithm exploring VRP effect in volatility selling.

**Key Implementation Note**: VRP strategies require implied volatility data. The current StrategyContext only provides OHLCV Bar objects. However, the VRP signal can be proxied using:
- VIX futures term structure (contango = sell vol favorable)
- Historical volatility vs VIX spread
- Options data if connected (Polygon, IBKR)

A simplified VIX-term-structure-based VRP strategy is implementable today using only futures data.

---

### IMPLEMENTABILITY ASSESSMENT SUMMARY

| Topic | Total Results | IMPLEMENTABLE-YES | IMPLEMENTABLE-NO | Key Blocker |
|-------|--------------|-------------------|------------------|-------------|
| Scalping (1-min futures) | 5 | 5 | 0 | None — OHLCV sufficient |
| Order Flow Absorption | 5 | 5 | 0 | None — volume + delta computable from bars |
| Options Premium Selling | 5 | 5 | 0 | Needs options chain / Greeks data adapter |
| Cross-Asset Momentum Spillover | 5 | 4 | 1 | GNN paper (#5) requires DL infrastructure |
| VRP Selling | 5 | 5 | 0 | Needs IV data (VIX futures proxy works) |

**Overall**: 24/25 papers are IMPLEMENTABLE-YES. Only the GNN-based options momentum spillover paper requires infrastructure beyond the current Strategy interface.

### IMPLEMENTATION ROADMAP — Next Strategies to Build

Based on this research, the following strategies should be added to SUPPORTED_STRATEGY_IDS:

1. **`absorption-reversal`** — Combined absorption score (delta absorption + volume divergence + VPIN toxicity) for institutional fade setups
2. **`network-momentum-spillover`** — Cross-asset lead-lag detection via rolling correlation; trade lagging assets when leaders confirm trend
3. **`vix-premium-harvest`** — VIX contango detection → signal to sell vol when term structure is in contango; flatten on backwardation
4. **`scalping-vwap-pullback`** — 1-min VWAP pullback with volume spike confirmation + ATR-based dynamic stops
5. **`cross-asset-ovx-momentum`** — OVX (crude vol) change as leading indicator for equity index futures direction

These 5 strategies are directly implementable with the current `Strategy` interface and `StrategyContext` (OHLCV bars only).
