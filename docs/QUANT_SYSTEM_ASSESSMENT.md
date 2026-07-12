# Bill/Hedge — Full Quant System Assessment
## 2026-05-04 | Market: Monday 10:30 AM EDT | Regime: Displacement-up

---

## 1. WHERE WE STAND

### Architecture
- **8 strategies** implemented, registered, type-checked
- **6 markets**: ES, NQ, CL, GC, 6E, ZB
- **90 days** of 1-minute data (~468K bars)
- **3 Topstep demo accounts** ready for paper execution
- **Research feed**: 27 strategy hypotheses, 41 high-signal arXiv papers
- **OOS split**: Fixed (60d train / 30d test, zero overlap)

### Survivability Breakdown
| Metric | Score | Target | Status |
|--------|-------|--------|--------|
| Walkforward | RED | GREEN | BLOCKED |
| Rolling OOS Mean Survivability | 84 | ≥90 | CLOSE |
| Live Readiness | 20 | ≥80 | POOR |
| OOS Windows | 1/2 | 2 | 1 SHORT |
| Deployable Windows | 0/2 | 2 | NONE |
| Research Feed | FRESH | FRESH | ✅ |

### Signal State (Live, Monday AM)
| Strategy | Symbol | Regime | EV | Direction |
|----------|--------|--------|-----|-----------|
| session-momentum | NQ | displacement-up | -0.92 | long |
| session-momentum | ES | displacement-up | -0.74 | long |
| ict-displacement | — | no routable signal | — | — |
| opening-range-reversal | — | no routable signal | — | — |
| liquidity-reversion | — | no routable signal | — | — |

---

## 2. TOP 1% HEDGE FUND ARCHITECTURE — WHAT WE'RE MISSING

### The Renaissance/Two Sigma/Citadel Blueprint

**Layer 1: Signal Generation (We have this — partially)**
- Multi-strategy framework: ✅ (8 strategies)
- Diverse alpha sources: ⚠️ (all price-derived, no fundamental/alternative)
- Non-correlated signals: ❌ (all strategies use same price data)

**Layer 2: Signal Weighting & Combination (WE DON'T HAVE THIS)**
- This is the SINGLE BIGGEST GAP. Top funds don't just run strategies — they combine them:
  - **Factor zoo approach**: Hundreds of candidate signals, Lasso/Ridge/ElasticNet for feature selection
  - **Bayesian Model Averaging**: Weights shift with uncertainty — key for regime changes
  - **Information-decay weighting**: Recent performance matters more, with half-life decay
  - **Volatility-targeting**: Scale positions inversely to realized vol
  - **Signal correlation matrix**: Diversify across uncorrelated alphas — NOT what we do (all price-derived)

**Layer 3: Regime Detection (WE HAVE BASIC, NEED ADVANCED)**
- **Hidden Markov Models**: Renaissance-level regime detection. 2-4 hidden states (bull, bear, chop, crisis). Transition probabilities. State-conditional strategy weights.
- **GARCH/EGARCH vol clustering**: Not just ATR — model vol of vol
- **Macro regime overlay**: Fed cycle, yield curve, VIX term structure → strategy gating
- Current state: We only have ATR-based vol regime detection. This is inadequate.

**Layer 4: Risk Management (BASIC)**
- ✅ Stop losses, max contracts, daily loss caps
- ❌ Portfolio-level VaR/CVaR
- ❌ Correlation-based position sizing
- ❌ Dynamic risk budgeting across strategies
- ❌ Stress testing on historical crisis scenarios

**Layer 5: Execution (NOT APPLICABLE — demo only)**
- Market impact models
- VWAP/TWAP algorithms
- Smart order routing

### What Separates Elite from Mid-Tier
1. **Signal diversification**: Elite funds have 100+ uncorrelated signals. Mid-tier has 5-10 correlated.
2. **Regime adaptivity**: Elite funds switch strategy weights per regime. Mid-tier runs fixed weights.
3. **Risk budgeting**: Elite allocates risk, not capital. Mid-tier allocates capital.
4. **Execution alpha**: Elite captures 5-15bp in execution. Mid-tier bleeds it.
5. **Decay detection**: Elite monitors signal decay in real-time. Mid-tier discovers it in drawdown.

---

## 3. CHINESE QUANT APPROACHES — WHAT'S DIFFERENT

### Key Chinese Quant Fund Approaches
1. **High-Flyer (幻方量化)**: Deep learning-first. LSTM/Transformer for price prediction. Multi-timeframe fusion. Known for aggressive positioning in index futures during volatility events.

2. **Ubiquant (九坤投资)**: Factor-based with alternative data. Satellite imagery, supply chain, shipping data. Cross-asset (equity + commodity + bond). Typical Western multi-strat approach adapted to Chinese markets.

3. **Minghong (明宏投资)**: Mean-reversion specialist. Statistical arbitrage on index futures. Very profitable in range-bound Chinese markets (A-shares have longer chop periods than US).

### Chinese-Specific Strategies That Work
1. **Intraday reversal on limit-up/limit-down exhaustion**: Chinese markets have 10% price limits. Reversal at limit exhaustion is highly profitable. Adaptable to US futures at circuit-breaker levels.

2. **Overnight gap fade**: Chinese futures gap heavily on policy news. Fading the gap works more often than following it. Same principle applies to US futures on FOMC/NFP days.

3. **Volume-price divergence**: Volume climax without price follow-through → reversal. Works cross-market.

4. **Sector rotation momentum**: Not applicable to our 6-market futures but the principle of cross-asset momentum ranking IS applicable.

### What We Can Adapt
- **Mean-reversion focus**: Chinese quants lean more mean-reversion than trend-following. In range-chop regimes, this is superior. We're over-weighted to trend/momentum strategies.
- **Limit-based strategies**: Adapt circuit-breaker behavior for ES/NQ
- **Multi-timeframe fusion**: LSTM across 1m, 5m, 15m, 1h simultaneously

---

## 4. STRATEGY DIAGNOSIS — WHAT'S BROKEN VS WHAT'S RANGE-LIMITED

### Strategy-by-Strategy Assessment

#### ICT-Displacement [KEEP — needs regime]
- **Theory**: Valid. Liquidity sweep → displacement → FVG entry. Works in trending markets.
- **Current problem**: Needs clean displacement. Monday chop with news noise → no clear structure.
- **Verdict**: NOT broken. Market conditions don't favor it. Will fire when trend establishes.
- **Fix**: Add displacement quality filter (size, speed, volume confirmation). Don't fire on weak displacement.

#### Opening-Range-Reversal [KEEP — needs parameter tuning]
- **Theory**: Valid. First 30-min range → break and reverse. Classic auction market theory.
- **Current problem**: No routable signal in current conditions. ORB is sensitive to range width.
- **Verdict**: Likely parameter issue. ORB on NQ needs wider range thresholds than ES.
- **Fix**: Adaptive ORB width based on ATR(14) percentile. Wider range → wider ORB zone.

#### Liquidity-Reversion [KEEP — best strategy in theory]
- **Theory**: Strong. Liquidity sweep → mean reversion. Works in all regimes.
- **Current problem**: No routable signal. Signal detection thresholds too strict.
- **Verdict**: Probably threshold issue. Liquidity sweeps are happening.
- **Fix**: Lower detection thresholds, add volume confirmation.

#### Session-Momentum [PROBLEMATIC — but highest potential]
- **Theory**: Sound. Trend following with session filters.
- **Current problem**: EV -0.92 even in displacement-up regime. Consistently negative.
- **Verdict**: This is concerning. The strategy finds regime correctly but can't extract positive EV.
- **Fix**: Add volatility filter (don't trade low-vol chops), tighten entry timing, add exit optimization.

#### Expiry-Flow, Pairs-Trading, Cross-Sectional-Momentum [UNPROVEN]
- Implemented in code but 0 OOS evidence
- Pairs-trading: Has best paper support (Attention Factors, DNN stat arb, Graph Learning)
- Expiry-flow: Gamma/Vix features built, no live data feed yet
- CSM: Needs ranking framework (papers exist — Learning to Rank, Spatio-Temporal)

#### Volatility-Regime [UTILITY — not a standalone strategy]
- Should be a meta-layer, not a standalone strategy
- VIX contango/backwardation detection is useful for GATING other strategies
- Currently trying to produce trade signals — wrong role

---

## 5. WHAT'S WORTHLESS VS WHAT NEEDS DATA

### Worthless (remove or repurpose):
1. **Volatility-regime as standalone strategy**: Convert to meta-gate. Don't try to trade it directly.
2. **6E (Euro FX)**: 4 trades, -3.77R, already eliminated. Confirm and remove from allowed symbols.
3. **CSV-based "live" data**: 30d CSV that was identical to training. Already fixed with true OOS.

### Needs more data (keep, expand):
1. **Pairs-trading**: Best research backing, zero runtime. Needs live data feed.
2. **Expiry-flow**: Gamma/VIX features built. Needs Polygon options data or Yahoo fallback.
3. **Cross-sectional momentum**: Needs 20+ instruments for ranking. 6 markets is barely enough.

### Needs parameter tuning (keep, adjust):
1. **All 4 active strategies**: Thresholds too strict, no regime-adaptive parameters
2. **Session-momentum**: Entry timing needs work — finding regime but missing entries

---

## 6. IMPLEMENTATION ROADMAP

### Phase 1: Foundation Fixes (THIS WEEK — 2-3 days)

**1a. Complete OOS Gate (1 more window)**
- Run strategy-factory on different date range to accumulate 2nd window
- Target: clear walkforward gate

**1b. Strategy Parameter Audit**
- Review all 4 active strategies' signal thresholds
- Lower detection sensitivity for live market testing
- Add volume confirmation to ICT-displacement
- Add adaptive ORB width

**1c. Regime Detection v2**
- Replace simple ATR regime with HMM (2-4 states)
- Map strategies to regimes:
  - Trending (displacement): ICT-displacement, session-momentum
  - Range/Chop: liquidity-reversion, opening-range-reversal
  - High Vol: reduce exposure, widen stops
  - Crisis: all off, or volatility-regime only
- Implementation: hmmlearn or custom Baum-Welch on 90d data

### Phase 2: Signal Quality (WEEK 2 — 3-4 days)

**2a. Multi-Factor Signal Ranking**
- Combine all 8 strategies into factor zoo
- Implement ElasticNet for feature selection
- Bayesian Model Averaging for dynamic weighting
- Target: eliminate negative-EV signal combinations

**2b. Strategy Correlation Matrix**
- Calculate rolling correlation between strategy returns
- Cap exposure to correlated strategies
- Force diversification across alpha sources

**2c. News/Sentiment Gate**
- Free data: Finnhub free tier (60 calls/min), RSS feeds
- Economic calendar: ForexFactory scraping or investing.com
- Simple NLP: FinBERT or VADER sentiment on headlines
- Gate: block momentum in high-news windows, allow mean-reversion
- Implementation: Python microservice, <500MB RAM

### Phase 3: Advanced Features (WEEK 3-4)

**3a. Pairs-Trading Live Implementation**
- DNN stat arb (Neufeld et al.) — model-free, no cointegration
- OR Attention Factors (Epstein et al.) — joint estimation
- 6-market futures graph → latent pair detection

**3b. Learning-to-Rank for CSM**
- Poh et al. (2020) → transfer ranking → spatio-temporal
- 6-market ranking feasible with simple neural net

**3c. Expiry-Flow Data Feed**
- Polygon options chain → gamma exposure calculation
- VIX term structure → contango/backwardation signal
- Weekly expiration cycle gating

### Phase 4: Production Hardening (ONGOING)

**4a. Signal Decay Monitoring**
- Track each strategy's rolling Sharpe over 20-day windows
- Alert on >30% decay → pause strategy, investigate

**4b. Walkforward Automation**
- Weekly automatic re-training on expanding window
- Strategy promotion/demotion based on OOS performance
- Human-in-loop only for new strategy approval

**4c. Stress Testing**
- Historical scenarios: 2020 COVID crash, 2022 rate hike cycle, 2008 GFC
- Monte Carlo with fat tails (t-distribution, not normal)
- What-if: 3-sigma events, correlation breakdown

---

## 7. IMMEDIATE NEXT ACTIONS

1. **Run strategy-factory** with different date window to get 2nd OOS window → clears gate
2. **Audit signal thresholds** — lower by 20-30% for demo exploration mode
3. **Implement HMM regime detection** — scikit-learn hmmlearn, ~100 lines of Python
4. **Wire Finnhub free tier** — economic calendar + news sentiment for event gating
5. **Remove vol-regime as trade strategy** — convert to meta-gate function

---

## 8. CURRENT MARKET ASSESSMENT (May 4, 2026)

- **Regime**: Displacement-up on NQ, range-chop on ES
- **Drivers**: Tariff uncertainty, Fed hold pattern, pre-CPI positioning
- **Expected duration**: Chop through CPI (May 12-14), then trend resolution
- **Best strategies for this regime**: Liquidity-reversion (chop fade), reduced-size momentum on NQ displacement
- **Worst strategies**: Pure trend-following, breakout strategies
- **News risk**: High. Every tariff headline moves markets 1-2%. Need event gating.
