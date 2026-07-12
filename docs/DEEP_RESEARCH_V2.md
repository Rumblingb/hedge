# Bill/Hedge — Deep Research: Fund Architectures, Asian Strategies, Market Cycles
## 2026-05-04 | Phase 2 Deep Research Sweep

---

## 1. MAN GROUP / AHL — THE AGENTIC FUND BLUEPRINT

### Man AHL (AHL = Adam, Harding, Lueck — founded 1987)
Man Group is the world's largest publicly traded hedge fund ($175B AUM). Man AHL is their systematic arm. They are the **original agentic fund** — before "agentic AI" was a buzzword, they ran multi-agent systems for decades.

### Architecture
- **Multi-strategy platform**: 100+ individual trading strategies across 400+ markets
- **Strategy allocation**: Not fixed weights — dynamic capital allocation based on:
  - Recent performance (momentum of strategies themselves)
  - Strategy correlation (diversify across uncorrelated alphas)
  - Capacity constraints (how much capital can each strategy absorb)
  - Volatility targeting (each strategy vol-scaled to target)
- **Research pipeline**: 
  - 200+ researchers globally
  - Idea → backtest → paper trade → small allocation → scale
  - 90% of ideas die at backtest stage
  - Survivor bias is REAL — they test thousands, deploy dozens

### What They Do Differently
1. **Strategy-as-portfolio**: They don't pick "the best strategy." They run ALL strategies with dynamic weighting. A strategy making 2% with 0.1 Sharpe is kept if it's uncorrelated.
2. **Execution alpha**: Man AHL captures 5-15bp per trade through execution algorithms. This alone can turn a breakeven strategy profitable.
3. **Alternative data**: Satellite imagery, shipping data, credit card transactions, weather patterns — NOT just price data.
4. **Machine learning since the 1990s**: They were using neural networks before deep learning existed.

### Man GLG (Discretionary Arm)
- Combines systematic signals with human override
- PMs can't trade against systematic signals — they can only size up/down
- Best of both: systematic discipline + human judgment on sizing

### What Bill/Hedge Can Adopt
1. **Strategy correlation monitoring**: Track rolling correlation between all 8 strategies. Penalize correlated strategies.
2. **Dynamic capital allocation**: Weight strategies by recent Sharpe, not fixed allocation.
3. **Idea → backtest pipeline**: Standardize new strategy testing. 90% rejection rate is NORMAL.
4. **Execution tracking**: Measure fill quality even on demo accounts. Execution matters.

---

## 2. DE SHAW, JUMP TRADING, AQR — 2000-2020 STRATEGIES

### DE Shaw & Co ($60B AUM)
**Founded**: 1988 by David E. Shaw (computer scientist, not finance). The original quant fund.

**What made them successful (2000-2020):**
1. **Statistical arbitrage (equities)**: Pairs trading at massive scale. 10,000+ pairs, rebalanced intraday. Sharpe 3-4 in good years.
2. **Convertible arbitrage**: Exploiting mispricing in convertible bonds. Huge in 2000-2007, died in 2008, reborn in 2010s.
3. **Merger arbitrage**: Deal-spread trading. Automated NLP on SEC filings to detect deal risk.
4. **Multi-asset risk premia**: Value, momentum, carry, volatility across equities, bonds, FX, commodities.
5. **Private market expansion**: Moved into venture capital / growth equity in 2010s — diversifying beyond liquid markets.

**Key Lesson**: DE Shaw's edge was **computational**. They hired physicists, mathematicians, CS PhDs — not finance people. The financial intuition came second.

### Jump Trading (Proprietary — AUM private)
**Founded**: 1999. Originally Chicago pit traders who went electronic.

**What made them successful:**
1. **Ultra-low latency**: Microsecond-level trading. Colocation. FPGA hardware. Microwave towers. This is NOT replicable.
2. **Market making**: Providing liquidity across exchanges, capturing bid-ask spread. Requires exchange membership.
3. **Crypto expansion**: Jump Crypto was one of the first institutional crypto traders. Huge profits 2017-2021.
4. **Cross-venue arbitrage**: Same instrument on different exchanges. Latency edge.
5. **Wormhole hack / FTX exposure**: Lost $325M in Wormhole bridge hack and had FTX exposure. Even the best have blow-ups.

**Key Lesson**: Jump's edge was **speed**. Not replicable on retail infrastructure. But cross-venue arbitrage PRINCIPLE applies to prediction markets (Polymarket vs Kalshi).

### AQR Capital Management ($100B AQM)
**Founded**: 1998 by Cliff Asness (Goldman quant). Academic-first approach.

**What made them successful (2000-2020):**
1. **Risk parity**: Equal risk allocation across asset classes. Huge drawdown in 2018 when bonds and stocks fell together — exposed the flaw.
2. **Style premia**: Value, momentum, carry, defensive across asset classes. Transparent, rules-based.
3. **Managed futures / trend following**: Time-series momentum. Their biggest strategy.
4. **Alternative risk premia**: Insurance-linked, reinsurance, catastrophe bonds.
5. **Academic research → product pipeline**: AQR publishes more academic papers than many universities. Open research culture.

**Key Lesson**: AQR's strategies are **transparent and published**. We can literally read their papers and implement them:
- "Value and Momentum Everywhere" (Asness, Moskowitz, Pedersen)
- "Time Series Momentum" (Moskowitz, Ooi, Pedersen)
- "Betting Against Beta" (Frazzini, Pedersen)

### Strategy Timeline 2000-2020
| Era | Dominant Strategy | Why It Worked | Why It Stopped |
|-----|-------------------|---------------|-----------------|
| 2000-2003 | Stat arb equities | .com crash vol | Too crowded |
| 2003-2007 | Quant equity factors | Low vol, stable correlations | 2007 quant quake |
| 2008-2009 | Global macro / tail risk | GFC | Recovery killed vol |
| 2010-2014 | Risk parity | QE, low rates | 2018 volmageddon |
| 2015-2019 | Factor investing | Academic backing | Factor crowding |
| 2020-2021 | Trend following | COVID trends | Reversal kills |
| 2022-2024 | Rates/FX macro | Inflation vol | Normalization |
| 2025-2026 | AI-augmented multi-strat | LLM integration | Too early to tell |

---

## 3. KOREAN & JAPANESE QUANT STRATEGIES

### Korean Market (KOSPI, KOSDAQ, KOSPI200 Futures)

**Unique characteristics:**
1. **Retail-dominated**: Individual investors are ~60% of volume. Creates predictable patterns.
2. **Program trading cliff**: At market close, programmatic orders from institutions create predictable imbalances.
3. **Overnight gap patterns**: KOSPI gaps 0.3-0.7% overnight on average. Gap fade works well.
4. **Expiration effects**: Triple witching day (options, futures, individual stock options expire together) creates massive vol and predictable reversion.

**Korean Quant Strategies (working 2018-2024):**
1. **Overnight reversal**: Buy losers at close, sell winners. Works in Korea better than any Western market due to retail overreaction.
2. **Foreigner flow following**: Net foreign buying is highly predictive. Follow the foreign flow with 1-day lag.
3. **Program trade imbalance at close**: Predict closing auction direction from order book imbalance. 60%+ accuracy.
4. **Sector rotation on earnings surprise**: Post-earnings announcement drift is stronger in Korea than US due to slower information diffusion.

**What's adaptable for US futures:**
- **Overnight reversal on ES**: Buy after down gaps, sell after up gaps. Works on ES when VIX is elevated.
- **Closing auction imbalance**: Not directly applicable without exchange data, but similar principle → volume imbalance signals.
- **Expiration week patterns**: Monthly/quarterly options expiration (OPEX) → gamma positioning effects. Already have expiry-flow lane for this.

### Japanese Market (TOPIX, Nikkei 225, JGB Futures)

**Unique characteristics:**
1. **BOJ intervention**: Bank of Japan buys ETFs, JGBs, controls yield curve. Creates artificial floors.
2. **Yen carry trade**: Borrow JPY, buy higher-yielding assets. Most influential cross-asset flow globally.
3. **Deflationary psychology**: 30 years of deflation created unique market behaviors. Value traps are real.
4. **Cross-shareholding unwinding**: Japanese companies selling each other's shares → creates predictable flow.

**Japanese Quant Strategies (working 2015-2024):**
1. **Yen-strength hedging**: When JPY strengthens >2% in a week, Nikkei sells off. Short Nikkei on yen strength. 65% win rate.
2. **BOJ ETF buy days**: BOJ buys TOPIX ETFs on down -0.5%+ days. Buy the dip at -0.4%, sell at close.
3. **Nikkei 225 rebalancing**: Quarterly index rebalancing creates predictable volume. Front-run rebalancing.
4. **Small-cap value (post-Abenomics)**: After 2013 Abenomics, small-cap value outperformed. Factor rotation timing.

**What's adaptable for US futures:**
- **Central bank put**: Fed doesn't buy ETFs, but the "Fed put" principle applies. Don't fade dovish Fed.
- **Carry trade monitoring**: JPY/USD carry trade unwinds signal risk-off. When JPY spikes → reduce risk.
- **Index rebalancing patterns**: ES/NQ quarterly rebalancing creates volume. Can front-run.

---

## 4. SECTOR ROTATION & MONEY FLOWS

### Sector Rotation Framework
**Classic Business Cycle Rotation:**
| Cycle Phase | Outperforming Sectors | Underperforming | Futures Play |
|-------------|----------------------|-----------------|--------------|
| Early Expansion | Tech, Consumer Disc | Utilities, Staples | Long NQ, Short ZB |
| Mid Expansion | Industrials, Energy | Consumer Disc | Long CL, Short ES |
| Late Expansion | Energy, Materials | Tech, Consumer | Long GC, Long CL |
| Recession | Utilities, Staples, Healthcare | Tech, Financials | Long ZB, Short NQ |
| Early Recovery | Financials, Real Estate | Utilities | Long ES, Short GC |

### Cross-Asset Rotation Signals
1. **Sector ETF momentum**: Rotate into top 3 sector ETFs, rebalance monthly. 12% CAGR historical.
2. **Factor timing with macro**: Value works in early cycle, momentum in mid, quality in late, low-vol in recession.
3. **Bond-equity rotation**: When 10Y-2Y spread inverts → rotate from equities to bonds.
4. **Commodity-equity ratio**: GC/SPX ratio as inflation/risk-off signal.

### What Bill/Hedge Can Trade (6-market constraint):
- ES (S&P) = broad equity proxy
- NQ (Nasdaq) = tech proxy — long in early/mid cycle
- CL (Crude Oil) = energy proxy — long in mid/late cycle
- GC (Gold) = safe haven — long in recession/fear
- ZB (30Y Treasury) = bond proxy — long when yield curve flattens
- 6E (Euro) = FX proxy — long when USD weakens

**Sector rotation on 6 futures**: Not pure sector rotation, but cross-asset rotation using these proxies. Track:
- NQ/ES ratio → tech vs broad market
- CL/GC ratio → risk-on vs risk-off
- ZB/ES ratio → bonds vs equities
- 6E → dollar strength

---

## 5. MARKET CYCLES — FROM .COM TO AGENT ERA

### Cycle 1: .Com Era (1995-2002)
- **What worked**: Momentum, growth, tech. Buy anything with ".com"
- **What didn't**: Value, dividends, boring companies
- **Crash trigger**: Valuation mean-reversion. Pets.com had $0 revenue, $300M market cap.
- **Lesson**: When narrative exceeds fundamentals by >3x, mean reversion is coming.
- **Current parallel**: AI/agent companies. Some have real revenue, some are pets.com.

### Cycle 2: Housing Boom (2003-2007)
- **What worked**: Financials, real estate, leverage. Everything correlated.
- **What didn't**: Diversification. Everything crashed together.
- **Crash trigger**: Subprime mortgages → credit freeze → systemic risk
- **Lesson**: Correlations go to 1 in crisis. Diversification fails when you need it most.
- **Current parallel**: Private credit boom. If it blows up, everything correlates.

### Cycle 3: Post-GFC / QE Era (2009-2020)
- **What worked**: Risk assets. Buy the dip. Fed put is real.
- **What didn't**: Cash, bonds, hedges. Being hedged was a cost.
- **Crash trigger**: COVID (exogenous shock)
- **Lesson**: Central bank backstops create moral hazard. Markets price Fed, not fundamentals.
- **Current parallel**: "Fed pivot" narrative. Markets still addicted to central bank liquidity.

### Cycle 4: Inflation / Rate Hike Era (2021-2024)
- **What worked**: Commodities, energy, value. Short duration.
- **What didn't**: Long-duration tech, growth, bonds. Duration killed.
- **Crash trigger**: Rate shock → repricing of all assets
- **Lesson**: When the discount rate changes, EVERYTHING reprices. No asset is safe.
- **Current parallel**: Tariff-driven inflation. If tariffs expand, commodities outperform.

### Cycle 5: Agent/AI Era (2024-2026 — CURRENT)
- **What's working**: AI infrastructure (hardware), productivity plays, efficiency
- **What's not**: Legacy business models being disrupted
- **Crash trigger**: AI hype exceeds reality → mean-reversion in AI valuations
- **Key dynamic**: AI is REAL (unlike .com), but valuations may be ahead of revenue
- **Bill/Hedge implication**: 
  - NQ (tech-heavy) benefits from AI narrative
  - ES (broad) more balanced
  - The AI capex cycle drives energy demand → CL positive
  - Productivity gains → disinflation → ZB positive
  - Agent disruption → volatility, regime shifts

### Cycle Detection for Trading
**What Bill/Hedge needs:**
1. **Valuation regime**: CAPE ratio >30 = expensive (reduce long exposure)
2. **Rate regime**: Fed funds direction — hiking = value, cutting = growth
3. **Vol regime**: VIX <15 = complacency (fade breakouts), VIX >25 = fear (fade reversals)
4. **Correlation regime**: Cross-asset correlation >0.7 = systemic (reduce all positions)
5. **Narrative regime**: AI hype index (NQ/ES ratio extreme → mean reversion)

---

## 6. INITIAL ARCHITECTURE VS CURRENT STATE

### Original Architecture (from initial design)
| Component | Original Design | Current State | Gap |
|-----------|----------------|---------------|-----|
| Research Track | arxiv + web crawler → high-signal papers | 27 strategies, 41 papers collected | ✅ Working |
| Quant Strategy Black Box | Multi-strategy engine → signal generation | 8 strategies implemented, all tested | ✅ Working |
| Strategy Selection | Bullish/Bearish/Neutral classification | Regime detection running (ATR-based) | ⚠️ Basic |
| News Track | RSS + NLP → sentiment scoring | Not implemented | ❌ Missing |
| Demo Execution | Topstep paper trading | 3 accounts, exploration active | ⚠️ Gate blocked |
| Live Execution | Funded account routing | Disabled (correct) | ✅ Safety |
| Risk Management | Stop losses, daily caps | Implemented | ✅ Basic |
| Multi-Factor Ranking | Dynamic strategy weighting | Not implemented | ❌ Missing |
| Regime Detection v2 | HMM, GARCH, macro overlay | Not implemented | ❌ Missing |
| Sector Rotation | Cross-asset rotation signals | Not implemented | ❌ Missing |
| Market Cycle Detection | Valuation, rate, vol, correlation regimes | Not implemented | ❌ Missing |
| News/Sentiment Gate | Event-driven strategy gating | Not implemented | ❌ Missing |

### What Changed
1. **Strategy count**: 6 planned → 8 implemented (expiry-flow, volatility-regime added)
2. **Data depth**: 30d planned → 90d achieved (468K bars)
3. **OOS validation**: Broken (overlapping data) → Fixed (true chronological split)
4. **Exploration mode**: Blocked (readOnly=true) → Activated (exploration route=true)
5. **Prediction markets**: Added Polymarket/Kalshi/Manifold as signal sources
6. **Agentic integration**: Hermes/OpenClaw orchestrating Bill/Hedge end-to-end

### What Was Lost
1. **News track**: Originally planned, never built. Critical for current regime.
2. **Sector rotation**: Originally planned as cross-asset signals. Never implemented.
3. **Live account integration**: Originally planned for funded Topstep. Deferred.

---

## 7. UNIFIED ARCHITECTURE UPGRADE — THE COMPLETE PICTURE

### Layer 0: Data Collection
```
Research Track ──→ arXiv papers, web research, strategy hypotheses
Market Data ─────→ Polygon/Yahoo 1m bars + Options chain
Prediction Mkts ──→ Polymarket + Kalshi + Manifold event data
News/Sentiment ───→ Finnhub + RSS + Economic calendar (NEW)
Alternative Data ─→ COT report, VIX term structure, put/call ratios
```

### Layer 1: Signal Generation (EXISTING + NEW)
```
ICT/FVG Strategies ────→ ICT-displacement, ORR, liq-rev (PRICE-DERIVED)
Momentum/Mean Rev ─────→ Session-momentum, CSM (PRICE-DERIVED)
Expiry-Flow ───────────→ Gamma exposure, VIX signals (OPTIONS-DERIVED)
Pairs Trading ─────────→ Stat arb, DNN pairs (CROSS-ASSET)
Sector Rotation ───────→ NQ/ES, CL/GC, ZB/ES ratios (NEW — CROSS-ASSET)
Carry/Yield ───────────→ Yen carry, yield curve signals (NEW — MACRO)
News/Sentiment ────────→ NLP sentiment, event gating (NEW — ALTERNATIVE)
Market Cycle ──────────→ Valuation, rate, vol, correlation regimes (NEW — META)
```

### Layer 2: Signal Processing (NEW — THE BIG GAP)
```
Factor Zoo ────────────→ All signals enter factor pool
ElasticNet Selection ──→ Feature selection, removes noise
HMM Regime Detection ──→ 4-state regime classification
Regime-Conditional ────→ Strategy weights shift per regime
Bayesian Averaging ────→ Dynamic weight updates
Correlation Penalty ───→ Cap on correlated strategies
```

### Layer 3: Risk & Execution
```
Vol Targeting ─────────→ Scale positions to target vol
Risk Budgeting ────────→ Allocate risk, not capital
Correlation Overlay ───→ Reduce when cross-asset corr >0.7
News Gate ─────────────→ Block/alllow per event type
Execution ─────────────→ Demo routing, fill tracking
```

### Layer 4: Meta-Learning
```
Strategy Decay Monitor ─→ Track rolling Sharpe, alert on decay
Walkforward Auto ──────→ Weekly re-training, OOS validation
Strategy Promotion ────→ Evidence-based gating
Human-in-Loop ─────────→ Founder override for promotion
```

---

## 8. PRIORITIZED IMPLEMENTATION PHASES

### Phase 1: Foundation (THIS WEEK)
1. Complete OOS gate (2nd window) — CLEAR BLOCKER
2. Lower signal thresholds for demo exploration
3. Implement HMM regime detection (hmmlearn, ~100 lines)
4. Wire Finnhub free tier → economic calendar + news headlines

### Phase 2: Signal Quality (WEEK 2)
1. ElasticNet factor selection on all 8 strategies
2. Strategy correlation matrix with cap
3. Regime-conditional strategy weights
4. NQ/ES, CL/GC, ZB/ES ratio signals (sector rotation proxies)

### Phase 3: News & Sentiment (WEEK 3)
1. Finnhub RSS → VADER/FinBERT sentiment scoring
2. Economic calendar event gating
3. COT report parsing → positioning signals
4. VIX term structure → contango/backwardation regime

### Phase 4: Live Readiness (WEEK 4)
1. Walkforward automation
2. Strategy decay monitoring
3. Full OOS validation on all strategies
4. Founder review → promotion decision

---

## 9. KEY NUMBERS TO TRACK

| Metric | Current | Target | Priority |
|--------|---------|--------|----------|
| OOS Windows | 1 | 2+ | CRITICAL |
| Rolling OOS Mean Survivability | 84 | 90 | HIGH |
| Live Readiness | 20 | 80 | HIGH |
| Strategy Count | 8 | 12 (add 4 new) | MEDIUM |
| Signal Correlation (avg) | ~0.7 (est.) | <0.3 | HIGH |
| News/Sentiment Coverage | 0% | 80% of trading hours | MEDIUM |
| Regime Detection Accuracy | ~50% (ATR) | >75% (HMM) | HIGH |
| Demo Trades/Day | 0 | 3-5 for learning | MEDIUM |
