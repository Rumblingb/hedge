# Bill/Hedge — Complete Operational Architecture
## 327 Strategies × 7 Tracks × End-to-End Workflow
## 2026-05-04 | Final Integrated Plan

---

## 1. THE COMPLETE WORKFLOW — Strategy Lifecycle

### STAGE 0: RESEARCH & IDEATION
```
Sources → Evaluation → Gate → Next Stage
─────────────────────────────────────────
arXiv papers      ┐
Quant research    ├─→ Research Agent ──→ Score & classify
Web/social trends ┤                      (relevance ≥ 7)
Trader intuition  ┘                      Novelty assessment
Market observation                      Gap matching
```

**Gate 0 Criteria:**
- Relevance score ≥ 7/10
- Fills identified strategy gap
- Has backtest-able logic (not purely qualitative)
- Different from existing strategies (dedup check)
- **Rejection rate expected: 80-90%** (Man AHL model)

### STAGE 1: INITIAL BACKTEST (IS — In-Sample)
```
Strategy code ──→ IS Backtest (90d data) ──→ Metrics ──→ Gate 1
```

**Metrics computed:**
- Sharpe ratio, Sortino ratio, Calmar ratio
- Win rate, avg RR, profit factor
- Max drawdown, max consecutive losses
- Exposure time, trade frequency
- **Adversarial validation: can classifier distinguish train/test?**
- **Deflated Sharpe ratio (Harvey-Liu-Zhu 2015)**

**Gate 1 Criteria:**
- Sharpe > 0.5 OR Profit factor > 1.2
- Max drawdown < 30%
- Win rate > 35%
- Adversarial validation: NO regime shift detected
- Deflated Sharpe: statistically significant
- **Pass rate expected: 20-30%**

### STAGE 2: WALKFORWARD (WFA — Walk-Forward Analysis)
```
Strategy ──→ Rolling WFA (4 windows, 60d train/30d test) ──→ OOS Metrics ──→ Gate 2
```

**This is the REAL test. IS means nothing without OOS confirmation.**

**Gate 2 Criteria:**
- OOS Sharpe > 0 (positive on unseen data)
- OOS profit factor ≥ 1.0
- At least 2/4 OOS windows profitable
- No catastrophic OOS window (Sharpe < -2)
- **Survivability score ≥ 60/100**
- **Pass rate expected: 10-15%**

### STAGE 3: PAPER/DEMO TRADING
```
Passed WFA ──→ Demo execution (Topstep paper) ──→ 30-day live paper ──→ Gate 3
```

**Paper trading rules:**
- 1 contract only
- Max 3 trades/day
- Realistic fills (slippage + commission)
- All guardrails active
- Journal every trade

**Gate 3 Criteria (30 trading days minimum):**
- Net R positive over 30 days
- Max daily drawdown < 2R
- Win rate consistent with backtest (±10%)
- No guardrail violations
- No emotional/override interventions
- **Survivability score ≥ 75/100**
- **Pass rate expected: 5-8%**

### STAGE 4: LIVE EXECUTION (Funded)
```
Paper passed ──→ Founder review ──→ Live allocation ──→ Continuous monitoring
```

**Live rules:**
- Start at 50% of paper size
- Scale up over 2 weeks
- All guardrails HARD CODED (no override)
- Daily P&L review by Hermes
- Weekly strategy performance review

**~5% of initial ideas reach live execution. This is NORMAL.**

---

## 2. RUNTIME EXECUTION — When to Run, When to Stop

### 2A. STRATEGY REGIME CLASSIFICATION

Every strategy gets classified by the regime it works in:

| Strategy Type | Bullish Regime | Bearish Regime | Neutral/Chop | High Vol |
|--------------|---------------|---------------|-------------|----------|
| Momentum/Trend | ACTIVE | ACTIVE (short) | SLEEP | REDUCED |
| Mean Reversion | SLEEP | SLEEP | ACTIVE | ACTIVE |
| Breakout | ACTIVE | ACTIVE | SLEEP | CAUTION |
| Scalping | ACTIVE | ACTIVE | ACTIVE | REDUCED |
| Carry/Spread | ACTIVE | REDUCED | ACTIVE | SLEEP |
| Options Sell | REDUCED | REDUCED | ACTIVE | SLEEP |
| Options Buy | ACTIVE | ACTIVE | SLEEP | ACTIVE |
| Arb (all types) | ACTIVE | ACTIVE | ACTIVE | ACTIVE |

### 2B. HARD STOP RULES (Never Override)

```
TRIGGER                          →  ACTION
────────────────────────────────────────────────────────────────
Daily loss > $1,000 (prop firm)  →  Hard stop all futures
Trailing drawdown > $2,000       →  Hard stop all futures
Consecutive losses = 3           →  Stop for 2 hours
Consecutive losing days = 3      →  Stop for rest of day
Single strategy DD > 30%         →  Deactivate strategy
Portfolio DD > 15%               →  Reduce all positions 50%
VIX spike > 10 points in 1 day   →  Reduce to 25% size
News event (red folder)          →  Close all 5 min before
Circuit breaker (market halt)    →  Cancel all orders
Strategy OOS Sharpe < 0 for 30d  →  Demote to paper
```

### 2C. AUTOMATIC VS MANUAL DECISIONS

**Fully Automatic (Hermes can decide):**
- Strategy on/off based on regime
- Position sizing (Kelly/VoI-targeting)
- Stop loss placement
- Take profit levels
- Correlation-based exposure capping
- Strategy weight adjustments (BMA)

**Semi-Automatic (Hermes proposes, founder approves):**
- New strategy promotion to demo
- Strategy promotion to live
- Strategy demotion/retirement
- Capital allocation changes between tracks
- New instrument addition

**Manual Only (Founder must approve):**
- Live execution activation (initial)
- Risk limit increases
- New track activation
- System architecture changes
- Emergency override of any hard stop

---

## 3. THE COMPLETE ARCHITECTURE — How Everything Connects

```
                           ┌─────────────────────────────────────┐
                           │     RESEARCH AGENT (arXiv + Web)     │
                           │  Continuous paper collection + NLP   │
                           └──────────────┬──────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
          ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
          │  STRATEGY    │      │  SIGNAL GEN  │      │  ALT DATA    │
          │  BLACK BOX   │      │  (7 Tracks)  │      │  (Trends)    │
          │  327 strats  │      │  110 futures │      │  Google/Social│
          │              │      │  42 PM       │      │  SEC/Consumer │
          └──────┬───────┘      │  46 options  │      │  Innovation   │
                 │              │  10 crypto   │      └──────┬───────┘
                 │              │  52 commod   │             │
                 │              │  29 novel    │             │
                 │              │  38 trend    │             │
                 │              └──────┬───────┘             │
                 │                     │                     │
                 └──────────┬──────────┴──────────┬──────────┘
                            ▼                     ▼
                   ┌─────────────────────────────────────┐
                   │     SIGNAL PROCESSING LAYER          │
                   │  HMM Regime → Strategy Gating        │
                   │  ElasticNet → Feature Selection      │
                   │  BMA → Dynamic Weights               │
                   │  Correlation → Exposure Caps         │
                   │  Kelly → Position Sizing             │
                   │  Market Cycle → Macro Overlay        │
                   │  News/Sentiment → Event Gating       │
                   └──────────────┬──────────────────────┘
                                  │
                   ┌──────────────┴──────────────────────┐
                   │        RISK MANAGEMENT LAYER        │
                   │  Per-trade: Stop loss + sizing      │
                   │  Per-day: Loss cap + trade limit    │
                   │  Per-strategy: DD limit + decay     │
                   │  Per-track: Correlation cap         │
                   │  Portfolio: VaR + Circuit breakers  │
                   └──────────────┬──────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
   │  DEMO PAPER  │      │  LIVE FUNDED │      │  MONITORING  │
   │  Topstep     │      │  Topstep     │      │  Dashboard   │
   │  3 accounts  │      │  Prop firm   │      │  Real-time   │
   │  Learning    │      │  Real money  │      │  Alerts      │
   └──────────────┘      └──────────────┘      └──────────────┘
```

---

## 4. HOLES — WHAT'S MISSING & MUST BE BUILT

### CRITICAL (Must Build Now)
1. **Unified Dashboard** — Single view of all 7 tracks, P&L, positions, regime
2. **Strategy Onboarding Pipeline** — Automated Stage 0→4 workflow
3. **Cross-Track Risk Aggregation** — Portfolio-level VaR across all tracks
4. **Circuit Breaker System** — Automated hard stops at every level
5. **Performance Attribution** — Which strategies contributed what P&L
6. **Strategy Decay Monitor** — Automatic demotion when OOS Sharpe < 0

### HIGH (Build This Week)
7. **Regime-Based Strategy Gating** — Auto on/off based on HMM regime
8. **Correlation-Based Pruning** — Auto-deactivate correlated strategies
9. **Daily Performance Report** — Automated P&L, drawdown, exposure summary
10. **A/B Testing Framework** — Compare strategy variants side-by-side
11. **Strategy Version Control** — Track changes to strategy parameters
12. **Backtest Queue** — Prioritize which strategies to backtest next

### MEDIUM (Build This Month)
13. **Real-Time P&L Streaming** — Live P&L updates during trading
14. **Cross-Track Alpha Transfer** — PM signals → futures, Options → futures
15. **Capital Allocation Optimizer** — Dynamic allocation across tracks
16. **Stress Test Scenarios** — Historical crisis replay (2008, 2020, 2022)
17. **Execution Quality Analysis** — Slippage, fill rate, market impact
18. **Sentiment Overlay Dashboard** — Real-time sentiment across sources

### LOW (Ongoing)
19. **Strategy Marketplace** — Internal library of vetted strategies
20. **Community Signals** — Integrate external signal providers
21. **ML Model Versioning** — Track model versions for ML strategies
22. **Tax Optimization** — Wash sale management, tax-loss harvesting

---

## 5. STRATEGY DECISION MATRIX — Bullish/Bearish/Neutral

### How to decide which strategies to activate:

```
REGIME DETECTION (HMM)
        │
        ├──→ Trending Up ──→ Momentum, Breakout, Trend-following, Long-biased options
        │
        ├──→ Trending Down ──→ Momentum (short), Put spreads, VIX longs, Gold longs
        │
        ├──→ Range/Chop ──→ Mean reversion, Iron condors, Scalping, Theta selling
        │
        └──→ High Vol/Crisis ──→ Tail hedges, VIX options, Gold, Reduce all sizes
```

### Concurrent activation limits:
```
Max concurrent strategies per track:
  Futures:    15-20 of 110 (actively trading)
  PM:          5-8 of 42 (liquidity-limited)
  Options:     5-8 of 46 (capital-limited)
  Crypto:      3-5 of 10 (volatility-limited)
  Commodities: 3-5 of 52 (specialized)
  Novel:       2-3 of 29 (experimental)
  Trend Alpha: signals feed into futures, not standalone
```

---

## 6. WHAT WE DO BETTER THAN MOST — Our Edge

1. **Strategy count (327)** — Most funds run 20-50. We have depth.
2. **Multi-track** — Most are single-asset. We span 6 asset classes.
3. **Research pipeline** — Automated arXiv + NLP + backtest. Continuous.
4. **Regime adaptivity** — HMM + market cycle + sentiment. Not static.
5. **Prop firm optimize** — Specific strategies for challenge rules.
6. **Small capital advantage** — No market impact, instant execution.
7. **AI-native** — Hermes orchestrates, not humans. 24/7 operation.
8. **Open architecture** — Every strategy is documented, versioned, testable.

---

## 7. EXECUTION PRIORITY — What To Build Next

```
IMMEDIATE (Today/Tomorrow):
  1. Unified dashboard for all 7 tracks
  2. Circuit breaker system
  3. Cross-track risk aggregation
  4. Regime-based strategy gating automation

WEEK 1:
  5. Strategy onboarding pipeline (Stage 0→4)
  6. Performance attribution system
  7. Strategy decay monitor
  8. Daily automated performance report

WEEK 2:
  9. A/B testing framework
  10. Cross-track alpha transfer automation
  11. Capital allocation optimizer
  12. Strategy version control

ONGOING:
  13. Paper loop continuous execution (cron every 30 min)
  14. OOS evidence accumulation
  15. Research agent continuous collection
  16. Parameter optimization sweeps
```

---

## 8. THE TRUTH — What Will Actually Make Us Profitable

**It's not about having 327 strategies. It's about:**
1. **Ruthless strategy selection** — 90%+ rejection rate at research stage
2. **OOS validation** — Never trust in-sample results
3. **Position sizing** — Kelly > fixed size. Compounding > linear.
4. **Regime adaptation** — Wrong strategy in wrong regime = guaranteed loss
5. **Hard stops** — The system protects itself when it's wrong
6. **Continuous learning** — Every trade is a data point for improvement

**The formula:**
`Profitability = (Good Strategies × Right Regime × Proper Sizing) - (Bad Strategies × Wrong Regime × Overleverage)`

**Our job: maximize the left term, minimize the right term.**
