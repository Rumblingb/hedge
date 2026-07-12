# Bill/Hedge — LOCKED ARCHITECTURE v2 (2026-05-04)
## MULTI-TRACK QUANT SYSTEM — 4 TRACKS, 136 STRATEGIES
## DO NOT MODIFY WITHOUT FOUNDER APPROVAL

## TRACK 0: FUTURES / PROP FIRMS (Primary — 110 strategies)
- 3 Topstep 50K demo accounts
- 6 markets: ES, NQ, CL, GC, 6E, ZB
- 90d 1-min data
- 44 strategy files, 7 engine modules
- Paper loop every 30 min via cron

## TRACK 1: PREDICTION MARKETS (8 strategies)
- Polymarket + Kalshi + Manifold
- Arbitrage, event-fade, momentum, mean-reversion, resolution front-run
- Cross-track: PM probabilities → futures directional bias

## TRACK 2: OPTIONS (8 strategies)
- Gamma scalping, vega harvesting, theta farming, vol arb
- 0DTE, earnings strangles, put spreads, iron condors
- Cross-track: gamma exposure → futures S/R levels

## TRACK 3: CRYPTO (10 strategies)
- Funding rate arb, basis trading, perps momentum/mean-rev
- BTC dominance rotation, stablecoin yield, on-chain arb
- Liquidation cascade fade, narrative rotation
- Cross-track: BTC leading NQ by 5-15 min

## CAPITAL ALLOCATION ($1,000 → compound):
- Futures/Prop firms: $600 (2×$50K accounts)
- Prediction Markets: $100
- Options: $200
- Crypto: $300 (from prop firm payouts)

## REINVESTMENT:
- Prop payouts → more prop accounts + crypto
- PM profits → PM compound + options
- Options theta → options scale + crypto
- Crypto → crypto compound + prop firms

---

## LAYER 0: DATA COLLECTION TRACKS

### Track 0a: Market Data
- Source: Polygon.io (primary), Yahoo Finance (fallback)
- Resolution: 1-minute OHLCV
- Universe: ES, NQ, CL, GC, 6E, ZB
- Depth: 90-day rolling, expanding window
- Path: `data/free/ALL-6MARKETS-1m-90d-normalized.csv`

### Track 0b: Research Agent (arXiv + Web)
- Source: arXiv API, arxiv Python package
- Corpus: 41 high-signal papers, 27 strategy hypotheses
- Feed: `.rumbling-hedge/research/researcher/strategy-hypotheses.latest.json`
- High-signals: `Agent-Shared/research-high-signals.md`
- Schedule: Every 70 minutes (researcher cron)

### Track 0c: MiroFish Research Edge Detection
- Source: MiroFish integration for cross-market anomaly detection
- Purpose: Identify market microstructure anomalies, unusual options flow, dark pool prints
- Status: To be integrated as separate research track
- Path: `src/research/miroFish.ts`

### Track 0d: Prediction Markets
- Sources: Polymarket (primary), Kalshi, Manifold
- Schedule: Every 10 minutes
- Path: `.rumbling-hedge/logs/prediction-cycle-history.jsonl`
- Integration: Prediction market signals feed into event-driven strategy

### Track 0e: News & Sentiment
- Source: Finnhub API (free tier), RSS feeds
- Output: `.rumbling-hedge/state/news-sentiment.json`
- Schedule: On-demand, pre-market
- Integration: News sentiment gates all strategies

### Track 0f: Economic Calendar & Macro
- Source: Finnhub economic calendar, FRED data
- Purpose: Event-driven gating, macro regime overlay
- Integration: Blocks trend strategies during high-impact events

---

## LAYER 1: SIGNAL GENERATION (STRATEGIES)

### Category A: Price-Derived (Technical)
1. **ICT Displacement** — Liquidity sweep → displacement → FVG entry
2. **Opening Range Reversal** — First 30-min range break and reverse
3. **Liquidity Reversion** — Sweep-and-close-back-inside reversal
4. **Session Momentum** — Breakout continuation with volume confirmation
5. **Cross-Sectional Momentum** — Relative strength ranking across 6 markets
6. **Pairs Trading** — Statistical arbitrage, cointegration-based
7. **Supply/Demand Zones** — Order block / supply-demand level trading (NEW)
8. **Breakout Pullback** — Breakout → pullback to level → continuation (NEW)
9. **Gap Fade** — Overnight gap mean-reversion (Korean/Japanese pattern) (NEW)
10. **Volume Profile** — Volume-weighted average price / POC / value area (NEW)

### Category B: Macro/Fundamental
11. **Carry Trade** — Yield differential, roll yield, contango/backwardation
12. **Event-Driven** — Economic surprise, FOMC, NFP, CPI reaction patterns
13. **Cross-Asset Rotation** — NQ/ES, CL/GC, ZB/ES ratio signals (BUILT)
14. **Macro Regime** — HMM-based regime detection with strategy gating (BUILT)
15. **News Sentiment** — NLP sentiment scoring on headlines (BUILT)

### Category C: Derivatives/Flow
16. **Expiry Flow** — Gamma exposure, OPEX patterns, pin risk
17. **Volatility Arbitrage** — VIX term structure, vol mean-reversion
18. **Options Flow** — Unusual options activity, put/call ratio signals

### Category D: Machine Learning / Advanced
19. **HMM Regime** — 4-state Hidden Markov Model for regime detection (BUILT)
20. **Multi-Factor Ranking** — ElasticNet + Bayesian Model Averaging (BUILT)
21. **Strategy Correlation** — Rolling correlation matrix with exposure caps (BUILT)
22. **Deep Learning Momentum** — LSTM/Transformer price prediction
23. **Reinforcement Learning** — RL-based position sizing and entry timing
24. **Anomaly Detection** — Isolation Forest / autoencoder for regime breaks

### Category E: Retail-Edge (Small Capital Advantage)
25. **Scalping** — 1-3 tick scalps on high-vol events
26. **Market Open Drive** — First 5-min directional bias
27. **Power Hour** — Last hour momentum/mean-reversion
28. **Overnight Hold** — Gap-and-go continuation patterns
29. **News Spike Fade** — Fade the initial spike on high-impact news

---

## LAYER 2: SIGNAL PROCESSING

1. **Multi-Factor Ranking** (src/engine/multiFactorRanking.ts) — ElasticNet feature selection + BMA weighting
2. **Strategy Correlation** (src/engine/strategyCorrelation.ts) — Rolling 20d Pearson, exposure capping at 0.7
3. **HMM Regime Detection** (scripts/hmm_regime.py) — 4-state, per-symbol regime labels
4. **Cross-Asset Rotation** (src/signals/crossAssetRotation.ts) — 4 ratio signals + rotation regime
5. **News Sentiment Gate** (scripts/finnhub_news.py) — Sentiment scoring + event gating
6. **Expected Value Surface** (src/engine/expectedValueSurface.ts) — EV computation per strategy/symbol/regime

---

## LAYER 3: RISK & EXECUTION

1. **Guardrails** (src/risk/guardrails.ts) — Stop losses, RR ratios, daily caps
2. **Kill Switch** (src/engine/killSwitch.ts) — Emergency stop, consecutive loss limit
3. **Promotion Gate** (src/engine/promotionGate.ts) — OOS evidence, walkforward, live readiness
4. **Strategy Factory** (src/engine/strategyFactory.ts) — Profile evaluation, deployment gating
5. **Demo Execution** (src/live/demoExecution.ts) — Topstep paper trading routing
6. **Risk Model** (src/engine/riskModel.ts) — VaR, CVaR, stress testing

---

## LAYER 4: META-LEARNING

1. **Walkforward** (src/engine/walkforward.ts) — Rolling OOS windows, survivability scoring
2. **Rolling OOS** (src/engine/rollingOos.ts) — Chronological validation
3. **Live Readiness** (src/engine/liveReadiness.ts) — Pre-deployment validation
4. **Strategy Evolution** (src/evolution/proposals.ts) — Auto-demote losing strategies
5. **Agentic Fund** (src/engine/agenticFund.ts) — Multi-agent strategy allocation
6. **Agentic Loop** (src/engine/agenticLoop.ts) — Continuous self-improvement cycle

---

## INVARIANTS (NEVER CHANGE WITHOUT FOUNDER)
1. Demo-only execution until OOS gate clears (2+ deployable windows)
2. Never route negative-EV signals to live accounts
3. Never exceed 1 contract in challenge phase
4. Never skip stop-loss placement
5. Never trade during news blackout windows
6. Always maintain chronological OOS split (no data leakage)
7. Research feed must be fresh before promotion
8. Founder reviews all strategy additions and removals
9. Architecture changes require updating this document
10. MiroFish runs as separate research track, not execution lane
