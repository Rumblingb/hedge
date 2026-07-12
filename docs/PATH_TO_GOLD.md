# Path to GOLD — Battle Plan for Live Readiness
Date: 2026-05-13
Macro: SPX 7,400 (+0.1%), NDX 29,064 (-0.9%), VIX 17.99 (low vol, trending up)

## === ASSESSMENT: Why We Have 0 GOLD ===

### Quarantined Strategies: Root Cause Analysis

The no-edge ledger reveals THREE distinct failure modes, not one:

**Failure Mode 1: Genuinely Negative Edge (8 profiles)**
Strategies tested with 16-49 trades and statistically significant negative expectancy:
| Profile | Trades | Expectancy | Verdict |
|---------|--------|------------|---------|
| structural-flows-blend | 31 | -0.31R | Structural flows concept doesn't work on 1-min futures |
| ict-killzone-core | 37 | -0.63R | ICT is retail pseudoscience, not a quant strategy |
| ict-displacement-5m | 16 | -0.84R | Same — ICT concepts fail OOS |
| vwap-reversion-index | 34 | -0.76R | Implementation flawed: fixed thresholds without vol-scaling |
| session-momentum | 24 | -0.59R | Needs regime filter (works in trends, fails in chop) |
| csm-v2-index | 25 | -0.73R | Academic factor that should work — implementation broken |
| All WQ alphas | 48-49 | -1.04R to -1.30R | WorldQuant formulas need daily data, not 1-min futures |

**These are fundamentally broken** — no amount of tuning fixes ICT concepts or WorldQuant formulas applied to 1-min futures. They should be permanently retired, not re-tested.

**Failure Mode 2: Near-Zero Edge (2 profiles) — FIXABLE**

| Profile | Trades | Expectancy | What's Wrong |
|---------|--------|------------|--------------|
| short-term-reversal | 21 | **-0.018R** | Within noise of zero. Academically sound concept (Hanauer 2023). Fixed 60-bar lookback doesn't adapt to bar interval; no macro blackout; no vol-regime filter |
| topstep-index-open (ORB) | 25 | **-0.067R** | Within noise of zero. Classic prop strategy. Window too narrow (15-60 min); ATR kill filter too aggressive; fixed 20-min max hold too tight for NQ |

**These two can be fixed with targeted changes and re-tested.**

**Failure Mode 3: Insufficient Data (15 profiles)**
Zero OOS trades across ALL of them. The pipeline produces 0 signals because:
- Strategy thresholds too tight for current market regime
- Data window doesn't contain the right conditions (e.g., gap-fade needs gaps)
- Bar interval mismatch (1-min data vs strategy expecting 5-min)

---

## === PATH TO GOLD: 3-Phase Plan ===

### PHASE 1: Fix the Near-Zero Strategies (THIS WEEK)

**Target 1: Short-Term Reversal** (-0.018R → +0.15R)

Three surgical changes, NO overfitting:

1. **Macro news blackout** — Block trades 15 min before/after: FOMC, NFP, CPI, PPI, Fed minutes. These events create false reversals that get stopped out. This is a structural cost, not a parameter.

2. **VIX regime gate** — Only trade when VIX < 25. In high vol (VIX > 25), short-term reversal has negative skew because the trend is stronger than the reversal force. In low vol (VIX < 20), reversal edge increases.

3. **Adaptive lookback** — Replace hardcoded 60 bars with `max(20, 60 * (1/barIntervalMinutes))`. On 1-min data = 60 bars (1 hr). On 5-min data = 12 bars (1 hr). Same time horizon, regardless of data granularity.

No parameter tuning. These are structural guards that prevent trading in regimes where the strategy has known negative edge.

**Expected outcome**: -0.018R → +0.10R to +0.20R → SILVER

**Target 2: Opening Range Reversal** (-0.067R → +0.10R)

1. **Widen the window** — Current: 15-60 min session window. Change to 15-90 min. NQ/ES need the full first hour to establish the ORB range. The 60-min cutoff clips valid trades.

2. **Remove the ATR kill filter** — `volatilityKillAtrMultiple` is killing trades in the ORB period where volatility is naturally higher. Replace with volume-only filter (low volume = skip, high volume = signal is stronger).

3. **Extend max hold** — 20 min → 45 min. ORB trades need time to develop.

Again, structural changes, not parameter fishing.

**Expected outcome**: -0.067R → +0.05R to +0.15R → SILVER

---

### PHASE 2: Wire & Test Proven Assets (THIS WEEK)

**Target 3: Gold Rust strategies into TS pipeline**

Exists but never wired:
```
bill-core/src/gold_strategies.rs:
  - lw_donchian_breakout(data, 20)    // ✅ REAL
  - gapper_edge(data)                  // ✅ REAL
  - order_flow_80_20(data, 30)         // ✅ FIXED (was broken)
  - polymarket_edge_detector           // ❌ STUB (skip this)
```

Create a TS wrapper that imports these as strategy profiles. Donchian breakout on NQ with 20-bar lookback in the current trending market should produce positive signals. Test on current data first.

**Target 4: Prediction market edges — Fund the wallet**

The dry-run fills show real edges:
| Market | Edge | Status |
|--------|------|--------|
| Fed Decision in June? | **1.37x** | Wallet has $10.17, NOT deposited |
| NBA MVP | **1.43x** | Same — can't execute |
| Seoul Mayor | **1.10x** | Same |
| What will happen before GTA VI? | **1.43x** | Same |

The wallet has $10.17 USDC on Polygon but **never deposited on Polymarket**. The 0x25D10... deposit wallet needs the private key. The bot wallet 0x210885 has USDC on Polygon. The fix: transfer from Polygon to Polymarket via the Magic SDK wallet (0xaA55).

Expected edge: 1.37x on $2 = $2.74 expected value per trade. With 1-2 trades/day on prediction markets = $5-6/day in expected profit on $10 bankroll. 50%+ ROC.

---

### PHASE 3: Test 43 BRONZE Strategies (NEXT WEEK)

Run strategy-factory ONE PROFILE AT A TIME:
```
BILL_STRATEGY_FACTORY_PROFILE_IDS=bollinger-squeeze npx tsx src/cli.ts strategy-factory ...
```

Priority order by likelihood of positive edge:
1. `bollinger-squeeze` — volatility breakout on low-VIX market
2. `capitulation-score` — extreme sentiment reversal (complement to short-term-rev)
3. `drift-regime-csm` — regime-aware momentum (works when VIX < 20)
4. `intraday-momentum` — momentum in trending market
5. `expiry-flow` — options expiry effects (known institutional edge)
6. `rsi2-mean-reversion` — classic mean reversion
7. `pairs-trading` — statistical arbitrage (needs 2+ correlated symbols)

Each gets: 1 profile, 2 OOS windows minimum, 15-min timeout max. If first profile takes >5 min with 0 output → kill and document.

Expected: 2-4 of 43 BRONZE strategies will show positive OOS → SILVER candidates.

---

## === GATE CRITERIA: When We're LIVE ===

| Gate | Criteria | Current Status |
|------|----------|----------------|
| **SILVER** | Backtest PF >1.2, OOS pass ≥1/3 windows | 0/43 tested |
| **DEMO-READY** | SILVER + positive dry-run fills for 3 days | 0 strategies |
| **GOLD** | DEMO-READY + ≥20 demo trades, expectancy >0.10R | 0/0 tested |
| **LIVE** | 2+ GOLD strategies, wallet funded, daily loss <$200 | No GOLD |

**Path to first GOLD**:
```
short-term-reversal fix (1 day) → 
  backtest (1 hr) → 
    OOS (1 hr) → 
      demo, 20 trades minimum (5 trading days) →
        if expectancy > 0.10R → GOLD
```

Minimum timeline to first GOLD: **5-7 trading days**.

---

## === TRUTH: What We Actually Have ===

| Asset | Actual Edge | Action |
|-------|-------------|--------|
| Short-term reversal | -0.018R (fixable) | Fix this week |
| Opening range reversal | -0.067R (fixable) | Fix this week |
| 43 untested BRONZE | Unknown | Test this week |
| Gold Rust Donchian | Proven concept | Wire into TS |
| Prediction dry-run edges | 1.37x-1.43x | Fund wallet |
| 108 SKELETON names | Zero | Do not touch |
| 24 QUARANTINED | -0.3R to -1.3R | Do not re-test |

**Nothing else matters.** ICT strategies, WorldQuant alphas, and the 108 empty names are noise. The path to live goes through short-term-reversal, ORB, Donchian, and prediction markets. Everything else is a distraction until we have at least 2 GOLD strategies.
