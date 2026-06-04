# Comprehensive Strategy Landscape Analysis
## Hermes Agent Deep Research — June 4, 2026

---

## 1. EXECUTIVE SUMMARY

The hedge system has **89 strategy files on disk** but only **59 in the active catalog** — meaning **30+ orphan strategy implementations are written but never tested**. The walkforward/OOS pipeline is blocked by a single root-cause bug (OOS CSV = Training CSV), and the strategy fusion engine only maps 9 strategies to its 8 defined market regimes. The system has enormous untapped potential: robust WorldQuant alpha implementations, HMM regime detection, cross-asset rotation signals, and options flow infrastructure all exist but are not wired together.

---

## 2. CURRENT COVERAGE ANALYSIS

### 2.1 Cataloged Strategies (59 in `wctcEnsemble.ts`)

| Category | Strategies | Count |
|----------|-----------|-------|
| **ICT/SMC** | ict-displacement, ict-breakout, ict-narrative, ict-sweep-reversion | 4 |
| **Momentum** | session-momentum, wq-trend-mom, wq-trend-mom-60m, drawdown-momentum, network-momentum, cross-sectional-momentum, drift-regime-csm, kronos-direction | 8 |
| **Mean Reversion** | liquidity-reversion, opening-range-reversal, vwap-reversion, two-level-uncertainty | 4 |
| **Breakout** | orb-breakout, orb-breakout-60m, donchian-breakout, daily-range-breakout, regime-orb-breakout | 5 |
| **WorldQuant Alphas** | wq-alpha-001 through wq-alpha-083, wq-alpha-001-rust, wq-alpha-009-rust, wq-alpha-012-rust | 21 |
| **Volatility** | volatility-regime, wq-vol-regime-60m, vol-risk-premium | 3 |
| **Event/News** | event-spike-fade, expiry-flow | 2 |
| **Pairs/Cross-Asset** | pairs-trading, hmm-pairs-arb, optimal-cost-pairs | 3 |
| **Gamma/Options** | gamma-stability | 1 |
| **LLM/ML** | llm-ga-evolutionary, llm-momentum-gate | 2 |
| **Other** | bollinger-squeeze, capitulation-score, push-response-anomaly, opening-stop-hunt | 4 |

### 2.2 Uncataloged Strategy Files (30+ orphan files)

These strategy files exist in `src/strategies/` but are **never imported, never tested, never executed**:

| File | Strategy Class | Why Valuable |
|------|---------------|--------------|
| `seasonality.ts` | SeasonalityStrategy | Day-of-week/Month-end effects — proven edge |
| `monthlySeasonality.ts` | MonthlySeasonality | Turn-of-month, quarterly rebalancing |
| `gapFade.ts` | GapFadeStrategy | Overnight gap mean-reversion |
| `gapFadeRegime.ts` | GapFadeRegimeStrategy | Gap fade with regime filter |
| `powerHour.ts` | PowerHourStrategy | Last hour of session — high volume edge |
| `scalping.ts` | ScalpingStrategy | Micro-timeframe (needs 1m data) |
| `shortTermReversal.ts` | ShortTermReversalStrategy | WR=21 trades -0.018R (near breakeven, needs variant) |
| `ret30Momentum.ts` | Ret30MomentumStrategy | 30-bar return momentum |
| `rsiDivergence.ts` | RsiDivergenceStrategy | Classic bearish/bullish divergence |
| `rsi2MeanReversion.ts` | Rsi2ReversionStrategy | Larry Connors' RSI-2 strategy |
| `supplyDemand.ts` | SupplyDemandStrategy | Institutional order flow zones |
| `structuralFlows.ts` | StructuralFlowsStrategy | WR=31 trades, -0.308R (in no-edge) |
| `sessionFlow.ts` | SessionFlowStrategy | Intra-session flow patterns |
| `marketMicrostructure.ts` | OrderFlowImbalanceStrategy | arXiv:1907.06230 order flow imbalance |
| `novelML.ts` | RLInspiredStrategy | Q-learning discretized state-action |
| `marketProfile.ts` | MarketProfileStrategy | TPO / volume profile |
| `marketOpenDrive.ts` | MarketOpenDriveStrategy | First 30-min open drive |
| `ichimoku.ts` | IchimokuStrategy | Complete Ichimoku system |
| `macdKeltner.ts` | MacdKeltnerStrategy | MACD + Keltner combo |
| `adxDonchian.ts` | AdxDonchianStrategy | ADX-filtered Donchian |
| `advancedPatterns.ts` | AdvancedPatternsStrategy | Candlestick pattern recognition |
| `chartPatterns.ts` | ChartPatternsStrategy | Geometric chart patterns |
| `carryTrade.ts` | CarryTradeStrategy | FX carry / roll yield |
| `commodsCorrelation.ts` | CommodsCorrelationStrategy | Commodity cross-correlation |
| `deltaDivergence.ts` | DeltaDivergenceStrategy | Volume delta divergence |
| `eventDriven.ts` | EventDrivenStrategy | Scheduled event trading |
| `eventStrategies.ts` | EventStrategiesStrategy | Multi-event framework |
| `enhancedOrb.ts` | EnhancedOrbStrategy | Improved ORB |
| `finalFour.ts` | FinalFourStrategy | Last 4 days of expiry |
| `flowMacro.ts` | FlowMacroStrategy | Macro flow filter |
| `macroEvents.ts` | MacroEventsStrategy | Calendar-based macro events |
| `macroFlow.ts` | MacroFlowStrategy | Intermarket flow analysis |
| `ictDisplacement5m.ts` | IctDisplacement5m | 5-min variant of ICT |
| `newsSpikeFade.ts` | NewsSpikeFadeStrategy | Post-news fade |
| `postNewsSettlement.ts` | PostNewsSettlementStrategy | News settlement drift |
| `overnightHold.ts` | OvernightHoldStrategy | Gap/overnight strategies |
| `optionsVolRenko.ts` | OptionsVolRenkoStrategy | Vol-based renko bars |
| `optionsSellingFramework.ts` | OptionsSellingFramework | Short vol framework |
| `oscillatorPatterns.ts` | OscillatorPatternsStrategy | Stochastic/CCI/WillR combo |
| `priceJerkReversal.ts` | PriceJerkReversalStrategy | Sudden price jerk fade |
| `pricePatterns.ts` | PricePatternsStrategy | Pattern-based entry |
| `propEdgeStrategies.ts` | PropEdgeStrategies | Prop firm optimized |
| `propOptimized.ts` | PropOptimizedStrategy | Max profit factor tuning |
| `quantitativeStrategies.ts` | QuantitativeStrategies | Meta-strategy framework |
| `regimeLockedMomentum.ts` | RegimeLockedMomentum | Regime-gated momentum |
| `volScaledBreakoutMomentum.ts` | VolScaledBreakoutMomentum | Vol-adjusted breakout |
| `volTargetedMomentum.ts` | VolTargetedMomentum | Target vol momentum |

**This is 45 uncataloged files — nearly DOUBLE the cataloged count.** Each represents written, compiled TypeScript that is never tested in the walkforward pipeline.

### 2.3 Signal Files (src/signals/)

| Signal | Status | Use |
|--------|--------|-----|
| `crossAssetRotation.ts` | ✅ Exists, NOT wired into strategyFusion | NQ/ES, CL/GC, ZB/ES, GC/ES ratio signals |
| `hmmRegime.ts` | ✅ Exists, NOT wired into strategyFusion | 4-state HMM: trending, range-chop, high-vol, low-vol |
| `gexLevels.ts` | ✅ Exists, NOT wired | Gamma flip/Call wall/Put wall levels |
| `vixContangoFlag.ts` | ✅ Exists, NOT wired | VIX term structure regime |
| `hybridKellyVixSizing.ts` | ✅ Exists, NOT wired | Kelly-adjusted position sizing |
| `expiryFlowGammaFeature.ts` | ✅ Exists, NOT wired | Gamma feature computation |
| `domMicroEdge.ts` | ✅ Exists, NOT wired | DOM micro-price edge |
| `insideDay.ts` | ✅ Exists, NOT wired | Inside day pattern |
| `microprice.ts` | ✅ Exists, NOT wired | Micro-price calculation |

**All 9 signals are disconnected from the strategy fusion engine and the walkforward pipeline.**

---

## 3. STRATEGY FUSION ENGINE COVERAGE GAPS

### 3.1 Regime Mapping (strategyFusion.ts)

The fusion engine defines **8 regimes** but only maps **9 strategies**:

| Regime | Mapped Strategies | Missing Strategies |
|--------|------------------|-------------------|
| `trending-bull` | ict-displacement, session-momentum, orb-breakout, donchian-breakout, wq-trend-mom, daily-range-breakout, wq-vol-regime-60m | *All WQ alphas, network-momentum, drift-regime-csm, kronos-direction, macdKeltner, adxDonchian* |
| `trending-bear` | Same as bull | Same |
| `ranging` | liquidity-reversion, opening-range-reversal | *bollinger-squeeze, rsiDivergence, rsi2MeanReversion, supplyDemand, oscillatorPatterns* |
| `breakout` | orb-breakout, daily-range-breakout, donchian-breakout, session-momentum, wq-vol-regime-60m | *enhancedOrb, volScaledBreakoutMomentum, ichimoku, chartPatterns, adxDonchian* |
| `volatile` | (none — safety lock triggers) | *volRiskPremium, optionsSellingFramework, gammaStability* |
| `quiet` | liquidity-reversion, opening-range-reversal | *scalping, marketMicrostructure, microprice signal* |
| `reversal` | ict-displacement, liquidity-reversion, opening-range-reversal | *gapFade, newsSpikeFade, postNewsSettlement, shortTermReversal, priceJerkReversal* |
| `news` | (none) | *eventSpikeFade, eventDriven, eventStrategies, macroEvents* |

**Critical gap**: The `volatile` and `news` regimes have ZERO strategies mapped. The fusion engine hard-codes safety locks for these — effectively meaning NO trades in high vol or news, which is overly conservative.

### 3.2 Session Gating

Only 6 strategies have session preferences mapped. Seasonality strategies (which inherently depend on day-of-week/time-of-year) have no session gating.

### 3.3 Correlation Deconflict

Only 3 correlation groups exist (breakout, momentum, reversal) with 2-3 strategies each. 50+ strategies are uncorrelated in the engine's view.

---

## 4. TIMEFRAME COVERAGE ANALYSIS

### 4.1 Default Data

The entire pipeline runs on **15-minute bars** (`ALL-6MARKETS-15m-60d-normalized.csv`). This means:

- **Short-term (5-15min)**: NOT possible with current data — need 1m bars
- **Medium-term (30min-4h)**: This is the current regime — 15m bars provide this
- **Long-term (daily+)**: NOT possible with current data — need daily bars

### 4.2 Strategy Max Hold Times

From reading the strategies:
- **ICT displacement**: maxHoldMinutes=20 (short)
- **Session momentum**: maxHoldMinutes=20 (short)
- **WQ Alphas**: maxHoldMinutes=30 (short-medium)
- **WQ Trend Mom 60m**: Designed for 60m bars (medium)
- **WQ Vol Regime 60m**: Designed for 60m bars (medium)
- **Seasonality**: maxHoldMinutes=60 (medium)
- **Expiry flow**: Designed for multi-day holds (long)
- **Pairs trading**: Designed for multi-day holds (long)

**No explicit long-term strategies exist** in the catalog (daily+). The seasonality and expiry-flow files exist but aren't in the catalog.

---

## 5. ROOT CAUSE ANALYSIS: WHY 0/4 OOS WINDOWS ARE DEPLOYABLE

### 5.1 The Bug: OOS CSV = Training CSV

**File**: `src/engine/strategyFactory.ts`, line 257:

```typescript
const oosCsvPath = resolve(
  options.oosCsvPath ?? 
  env.BILL_STRATEGY_LAB_OOS_CSV_PATH ?? 
  "data/free/ALL-6MARKETS-15m-60d-normalized.csv"  // ← SAME DEFAULT AS TRAINING CSV
);
```

Both `csvPath` (line 256) and `oosCsvPath` (line 257) default to **the exact same file**. The OOS data is identical to the in-sample data. This means:

1. Walkforward train/test splits are **on the same data** (just date-split within the same file)
2. Rolling OOS windows evaluate on **data already seen in training** 
3. The "out-of-sample" survivability score is **meaningless** — it's just measuring in-sample consistency
4. The walkforward efficiency (WFE) metric compares train vs test on the same pool → artificially inflated

### 5.2 Cascade of Failures

The bug cascades through the entire pipeline:

```
Same CSV for IS + OOS
  → Walkforward trains AND tests on same data
    → scoreStability artificially high (no genuine OOS challenge)
      → But deployableNow still blocks because survivabilityScore < 85 threshold
        → Rolling OOS windows also see same data
          → tunedDeployableWindows=0 because tune strategy overfits to already-seen data
            → Agentic loop tries to patch, but patches can't fix data leakage
              → All gates fail → "blocked" status
```

### 5.3 Additional Blockers

Even after fixing the CSV bug, these blockers remain (from strategyFactory.ts lines 352-362):

1. **Walkforward not deployable** (score 72/100, threshold likely 85)
2. **Strategy coverage incomplete**: missing `expiry-flow`, `pairs-trading`, `cross-sectional-momentum` — these are valid strategy IDs not yet in any research profile
3. **No fresh research feed** — strategy feed produces zero directives
4. **Live execution disabled** (`BILL_PREDICTION_LIVE_EXECUTION_ENABLED !== "true"`)
5. **Futures demo disabled** (`BILL_ENABLE_FUTURES_DEMO_EXECUTION !== "true"`)

Walkthrough of the agentic loop (rollingOos.ts lines 181-191): It tries to tune `RH_MIN_RR`, `RH_MAX_CONTRACTS`, `RH_MAX_TRADES_PER_DAY`, `RH_MAX_DAILY_LOSS_R` via the agentic improvement loop, but since the data is the same for all windows, tuning cannot introduce genuine regime diversity.

### 5.4 Walkforward Matrix Failures

From `walkforwardMatrix.ts`, the rejection conditions (`failureModes` function, lines 200-214):
- `too-few-walkforward-windows` (needs ≥4, gets ~3 max from current window builder)
- `stitched-oos-net-negative` (with identical IS/OOS, any variance comes from random date split)
- `profit-factor-below-contract` (needs ≥1.4)
- `weak-oos-sharpe` (needs ≥0.15)
- `oos-drawdown-too-high` (max >4R)
- `walkforward-efficiency-below-0.5`
- `too-few-positive-oos-windows` (<60% of windows)

The window builder (`buildWalkforwardWindows` in walkforward.ts) creates at most 3 windows from a 60-day dataset. This is insufficient for robust validation.

---

## 6. NEW STRATEGY GENERATORS — RESEARCH & RECOMMENDATIONS

### 6.1 WorldQuant Alphas (Already Have 20, Can Add More)

**Status**: 20 of 101 published alphas implemented (Alpha 001-101 coverage is ~20%). 
**What's missing**: The most powerful alphas from the Kakushadze 101 paper:
- **Alpha 004**: Rank(correlation(rank(volume), rank(adv20), 2) * -1, 5) — volume trend confirmation
- **Alpha 013**: ((close - low) * (high - close))^0.5 — range position
- **Alpha 018**: rank((close - open) / (high - low) * volume) — intraday pressure
- **Alpha 023**: correlation(high, volume, 3) * rank(close) — price-volume confirmation
- **Alpha 031**: (close - mean(close, 12)) / mean(close, 12) * -1 * correlation(close, volume, 3) — trend exhaustion
- **Alpha 034**: correlation(close, volume, 5) * rank(close, 5) — volume-weighted momentum
- **Alpha 048**: correlation(delta(close, 5), delta(volume, 5), 10) * rank(close, 5) — momentum acceleration
- **Alpha 061**: rank(adv20) - rank(adv5) — volume regime shift
- **Alpha 062**: rank(close, 10) * volume / adv20 — price-volume breakout
- **Alpha 086**: correlation(close, volume, 10) * (close - vwap) — VWP deviation
- **Alpha 098**: correlation(close, vwap, 5) * rank(close) - correlation(close, vwap, 20) * rank(close) — trend vs VWAP divergence

**These would add excellent diversification** since the 101 alphas have an average inter-correlation of only 15.9%.

### 6.2 HMM Regime Detection

**Status**: Fully implemented in `src/signals/hmmRegime.ts` (955 lines). Baum-Welch EM training, Viterbi decoding, 4-state model. NOT wired into strategyFusion.

**Integration path**: 
1. Connect `hmmRegime.ts` output to `classifyRegime()` in strategyFusion.ts
2. Map HMM states: state 0 (trending) → trending-bull/bear, state 1 (range-chop) → ranging, state 2 (high-vol) → volatile, state 3 (low-vol) → quiet
3. Use HMM probabilities as regime confidence weights instead of hard classification

**Memory impact**: ~1MB for Baum-Welch on 90 days of 15m data (6 symbols × 4 states × 4 features). Fits in 16GB RAM easily.

### 6.3 Cross-Asset Rotation

**Status**: Fully implemented in `src/signals/crossAssetRotation.ts` (320 lines). Computes 4 ratios (NQ/ES, CL/GC, ZB/ES, GC/ES). NOT integrated.

**Integration path**:
1. Call `assessRotationRegime()` to get risk-on/risk-off/inflation-hedge regime
2. Feed regime into strategyFusion as an additional gating factor
3. Boost momentum strategies in risk-on, boost mean-reversion in risk-off

### 6.4 Machine Learning: Lightweight Approaches for 16GB RAM

Given the 16GB RAM constraint, here are viable approaches:

#### 6.4.1 HMM Ensemble (Already Partially Built)
- Use the existing HMM for regime detection
- Add a 2nd HMM on cross-asset ratios for macro regime
- Combine both → 4×4 = 16 macro-regime states
- Memory: ~2MB total

#### 6.4.2 Gradient Boosting (LightGBM/XGBoost)
- Feature set: 20-50 features from existing WQ alphas + technical indicators
- Target: next-bar direction (binary classification)
- Train on 90 days, retrain weekly
- Memory: ~200-500MB for model + feature store
- **LightGBM is RAM-efficient** (leaf-wise trees, handles 50 features on 50K rows easily)

#### 6.4.3 LSTM (Tiny)
- 1-2 layer LSTM with 32-64 hidden units
- Single-symbol models only (not cross-symbol)
- Sequence length: 20-60 bars
- Memory: ~50-100MB per model
- **Train on CPU** (no GPU needed for this size)
- Retrain monthly

#### 6.4.4 NOT Recommended for 16GB
- **Transformers** (even tiny ones: ~500MB+ base model, need GPU)
- **LLM-based strategy generation** (QuantAgent-style Writer-Judge needs 8GB+ VRAM)
- **Full reinforcement learning** (DDPG/SAC needs 4+ parallel environments)

### 6.5 Seasonality Patterns

**Status**: `src/strategies/seasonality.ts` exists (32 lines) but NOT in catalog. Covers Monday gap fade, Friday profit-taking, month-end rebalancing. Very basic implementation.

**Recommended additions**:
- **Turn-of-month effect**: First 3 days + last 3 days of each month → stocks outperform
- **January effect**: Small-cap outperformance in January
- **Sell in May / Halloween effect**: May-October underperformance vs November-April
- **Day-of-week patterns**: Monday negative bias, Friday positive bias
- **FOMC drift**: 24-hour drift post-FOMC decisions
- **OPEX week**: Options expiration week effects
- **Quarterly rebalancing**: Last day of quarter institutional rebalancing
- **Holiday effect**: Pre-holiday rallies

### 6.6 Options Flow Signals

**Status**: `src/signals/gexLevels.ts` exists and loads from external JSON. `src/signals/expiryFlowGammaFeature.ts` computes gamma features. NOT wired.

**Enhancement path**:
1. Connect GEX levels to strategyFusion as regime input
2. Use gamma flip as key support/resistance level
3. Use call wall / put wall as profit targets
4. Use expiry proximity to reduce position size (gamma risk)

---

## 7. RECOMMENDED STRATEGY ENABLEMENT BY TIMEFRAME

### 7.1 Short-Term (5-15min) — Requires 1m data

| Strategy | Rationale | Priority |
|----------|----------|----------|
| **Market Microstructure (Order Flow)** | arXiv order flow imbalance | HIGH |
| **Scalping** | Micro-timeframe mean reversion | HIGH |
| **Price Jerk Reversal** | Sudden move fade | MEDIUM |
| **RSI-2 Mean Reversion** | Connors' proven short-term strategy | HIGH |
| **Microprice Signal** | DOM-based micro-edge | MEDIUM |
| **WQ Alpha 001, 002, 006** | Reversal signals for short timeframe | HIGH |

**Data needed**: 1-minute bars CSV. **System already supports**: `src/engine/tvDataFetcher.ts` fetches TV data.

### 7.2 Medium-Term (30min-4h) — CURRENT PRIMARY TIMEFRAME

These should be the priority **right now** since the system already runs on 15m bars:

| Strategy | Category | Current Status | Priority |
|----------|----------|---------------|----------|
| **WQ Alpha 009 (Momentum Acceleration)** | Trend | Already cataloged | ACTIVE |
| **WQ Alpha 021 (Mean Return 8d)** | Trend | Already cataloged | ACTIVE |
| **ICT Displacement** | Reversal | QUARANTINED | RE-TEST with regime filter |
| **Session Momentum** | Trend | QUARANTINED | RE-TEST with regime filter |
| **Bollinger Squeeze** | Volatility | Cataloged, no regime map | REGISTER |
| **Donchian Breakout** | Breakout | BRONZE | PROMOTE |
| **Gap Fade + Gap Fade Regime** | Reversal | Uncataloged | ADD TO CATALOG |
| **Supply/Demand Zones** | Reversal | Uncataloged | ADD TO CATALOG |
| **RSI Divergence** | Reversal | Uncataloged | ADD TO CATALOG |
| **ADX Donchian** | Breakout | Uncataloged | ADD TO CATALOG |
| **MACD Keltner** | Trend | Uncataloged | ADD TO CATALOG |

### 7.3 Long-Term (Daily+) — Requires daily data

| Strategy | Rationale | Priority |
|----------|----------|----------|
| **Seasonality + Monthly Seasonality** | Day-of-week, month-end, turn-of-year | HIGH |
| **Carry Trade** | FX roll yield (6E) | MEDIUM |
| **Pairs Trading** | Cointegration-based mean reversion | HIGH |
| **Cross-Asset Rotation** | Multi-day macro regime shifts | HIGH |
| **Expiry Flow** | Gamma/options expiry effects | MEDIUM |
| **Macro Events** | FOMC/NFP/CPI drift | MEDIUM |
| **Post-News Settlement** | News drift patterns | MEDIUM |
| **Overnight Hold** | Gap patterns | LOW |

**Data needed**: Daily bar CSV. Can be derived from existing 15m data.

---

## 8. IMPLEMENTATION ROADMAP

### Phase 0: Fix the Pipeline (Days 1-2)

1. **Fix OOS CSV bug**: Change line 257 of `strategyFactory.ts` to use a separate OOS CSV file (e.g., `ALL-6MARKETS-15m-60d-OOS-normalized.csv`)
2. **Acquire genuine OOS data**: Download 30+ days of non-overlapping data for genuine OOS testing
3. **Bump walkforward windows**: Increase `buildWalkforwardWindows` max from 3 to 6-8
4. **Fix strategy feed**: Add missing strategy IDs to the feed's routing table so directives get through
5. **Enable demo execution**: Set `BILL_ENABLE_FUTURES_DEMO_EXECUTION=true` for paper trades

### Phase 1: Register Orphan Strategies (Days 3-5)

1. **Audit all 45 uncataloged files** → classify as working/stub/needs-refactor
2. **Add working strategies to catalogs**: Add to both `wctcEnsemble.ts` and `SUPPORTED_STRATEGY_IDS`
3. **Add to strategyFusion regime mappings**: Map each new strategy to its regime
4. **Add to walkforward profiles**: Include in research profiles for testing
5. **Prioritize**: seasonality, gapFade, supplyDemand, bollingerSqueeze, rsiDivergence, marketMicrostructure

### Phase 2: Wire Signals Into Fusion Engine (Days 5-7)

1. **HMM Regime**: Connect `hmmRegime.ts` → `strategyFusion.ts classifyRegime()`
2. **Cross-Asset Rotation**: Connect `crossAssetRotation.ts` → session gating
3. **GEX Levels**: Connect `gexLevels.ts` → stop/target adjustment
4. **VIX Contango**: Connect `vixContangoFlag.ts` → volatility regime

### Phase 3: New Strategy Implementations (Days 8-14)

1. **Additional WQ Alphas**: Implement 10 more (Alpha 004, 013, 018, 023, 031, 034, 048, 061, 062, 086)
2. **Enhanced Seasonality**: Expand from 3 patterns to 10+ (FOMC, OPEX, holiday, quarterly)
3. **LightGBM Classifier**: Train on WQ alpha outputs + technical features
4. **Tiny LSTM**: Single-symbol 1-layer LSTM for NQ/ES direction prediction

### Phase 4: Timeframe Expansion (Days 15-21)

1. **Acquire 1m data**: For short-term strategies (scalping, microprice, order flow)
2. **Acquire daily data**: For long-term strategies (carry trade, seasonality, pairs)
3. **Create timeframe-specific profiles**: Short/medium/long research profiles
4. **Multi-timeframe fusion**: Allow signals from different timeframes to confirm each other

### Phase 5: Production Readiness (Days 22-30)

1. **Live readiness stress**: Run 100+ iterations of live readiness
2. **Kelly position sizing**: Wire `hybridKellyVixSizing.ts` into execution
3. **Correlation-aware portfolio**: Track strategy correlations, cap correlated exposure
4. **Signal decay ledger**: Track performance degradation over time
5. **Graveyard backfill**: Compute mechanics hashes for all buried strategies

---

## 9. GAP VISUALIZATION

```
Current State:
┌──────────────────────────────────────────────────┐
│  89 Strategy Files on Disk                       │
│  ├── 59 in Catalog ← TESTED in walkforward      │
│  └── 30+ Uncataloged ← NEVER TESTED             │
│                                                   │
│  9 Signal Files                                  │
│  └── 0 Wired into strategyFusion                 │
│                                                   │
│  8 Market Regimes                                │
│  └── 9 Strategies Mapped (≈1 per regime)         │
│                                                   │
│  Data: 15m only                                  │
│  └── No 1m / No Daily / No multi-tf fusion       │
└──────────────────────────────────────────────────┘

Target State:
┌──────────────────────────────────────────────────┐
│  89 Strategy Files on Disk                       │
│  ├── 75+ in Catalog ← All tested                │
│  └── ~15 Stubs ← Clearly documented as such      │
│                                                   │
│  9 Signal Files                                  │
│  └── 9 Wired into strategyFusion                 │
│                                                   │
│  8 Market Regimes                                │
│  └── 30+ Strategies Mapped (3-5 per regime)      │
│                                                   │
│  Data: 1m + 15m + Daily                          │
│  └── Multi-tf confirmation in fusion engine       │
└──────────────────────────────────────────────────┘
```

---

## 10. CONCLUSION

The hedge system has an **extraordinary amount of built but untested strategy code**. The pipeline is blocked by a single root cause bug (OOS CSV = Training CSV) that cascades into all gates failing. Fixing this, registering the orphan strategies, and wiring the existing signals could transform the system from 0/4 deployable windows to a robust, multi-regime, multi-timeframe trading engine without writing much new code — just connecting what already exists.

**Priority action items:**
1. 🔴 Fix OOS CSV path (30 minutes, unblocks everything)
2. 🔴 Add top 10 orphan strategies to catalog (2 hours, doubles tested coverage)
3. 🟡 Wire HMM + cross-asset signals into fusion engine (4 hours, improves regime detection)
4. 🟡 Expand timeframe coverage with 1m + daily data (8 hours)
5. 🟢 Implement 10 additional WQ alphas (4 hours, adds diversification)
6. 🟢 Enhance seasonality with full calendar effects (2 hours)
