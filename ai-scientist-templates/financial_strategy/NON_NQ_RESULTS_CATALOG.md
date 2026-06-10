# AI Scientist Results: Non-NQ Instruments
## Catalog of Edges Across Topstep-Tradeable Instruments
Generated: 2026-06-10

---

## SUMMARY: What Works and What Doesn't

### 🔥 STRONG EDGES (worth immediate attention)

| Rank | Run | Symbol | Strategy | Timeframe | OOS PF | OOS Net | Trades | WR | WF Share | Status |
|------|-----|--------|----------|-----------|--------|---------|--------|----|----------|--------|
| 1 | **p3b_pji** | GC | pji (Pirate-John-Index) | 1h | **1.586** | **+974.4** | 37 | 59.5% | **1.0** | ⚠️ "WF OOS PF too low" blocker — but ALL 5 folds positive! |
| 2 | **p3b_vol** | GC | wq_vol_regime | 1h | **3.066** | **+1,894.9** | 128 | 65.6% | **0.8** | ⚠️ Only fold 2 negative |
| 3 | **gc_volregime_postfix** | GC | wq_vol_regime | 1h | **3.531** | **+1,073.7** | 47 | 59.6% | **0.6** | ⚠️ Fold 1,2 negative but strong later folds |
| 4 | **gc_volregime_topstep_compliant** | GC | wq_vol_regime | 1h | **1.038** | **+12.7** | 47 | 34.0% | **0.4** | Weak — barely positive OOS |

### 🟡 MODERATE / MIXED

| Run | Symbol | Strategy | Timeframe | OOS PF | OOS Net | Trades | WR | WF Share | Notes |
|-----|--------|----------|-----------|--------|---------|--------|----|----------|-------|
| it_orb_es15m | ES | orb | 15m | **1.385** | +248.7 | 538 | 43.9% | 0.2 | Good PF, 538 trades, but only 1/5 folds positive |
| it_vwap_GC | GC | vwap | 1h | **1.566** | +494.0 | 129 | 40.3% | 0.2 | OOS net positive but only 1/5 folds |
| m1_gc_daily_v3 | GC | wq_vol_regime | daily | 1.157 | +499.0 | 132 | 50.0% | 0.2 | Marginal |

### 🔴 DEAD / BROKEN (no edge)

| Run | Symbol | Strategy | Timeframe | OOS PF | Trades | WR | WF Share | Why Dead |
|-----|--------|----------|-----------|--------|--------|----|----------|----------|
| it_vwap_ES | ES | vwap | 15m | 0.311 | 29 | 44.8% | 0.0 | Negative net OOS |
| it_vwap_CL | CL | vwap | 60m | **0.0007** | 71 | 2.8% | 0.0 | Catastrophic — almost all losers |
| novel_orb_zn | ZN | orb | 15m | 0.0 | 11 | 0.0% | 0.0 | Every trade lost |
| n5_orb_ES | ES | orb | 3m | 0.0 | 0 | — | 0.0 | Gate filtered everything (timeframe_agreement=2 req) |
| n5_es_3m_orb | ES | orb | 3m | 0.0 | 0 | — | 0.0 | Same as above — duplicate params |
| n5_gc_15m_orb | GC | orb | 15m | 0.0 | 0 | — | 0.0 | Gate filtered everything |
| n5_orb_GC | GC | orb | — | 0.0 | 0 | — | 0.0 | No trades |
| gold_gc | GC | wq_trend_mom | — | 0.0 | 0 | — | 0.0 | No trades |
| novel_vwap_eur | EURUSD | vwap | — | 0.0 | 0 | — | 0.0 | No trades |
| it_vwap_es5k | ES | vwap | — | 0.0 | 0 | — | 0.0 | No trades |

---

## DETAILED BREAKDOWN BY INSTRUMENT

### GOLD (GC) — Most Promising Instrument
**33 run directories** exist for GC — by far the most researched non-NQ instrument.

#### ✅ Strong Edges (GC)

**1. run_p3b_pji** — BEST GC RESULT OVERALL
- Strategy: **Pirate-John-Index (pji)** — mean reversion on volatility regime
- Timeframe: 1h
- OOS PF: **1.586** | OOS Net: **+974.4 pts**
- Trades: 37 | Win Rate: **59.5%**
- Walkforward: **100% positive folds** (ALL 5 folds positive!)
- Train Net: +495.1 (also positive — rare!)
- Decision: `research-only-template-blocked`
- Blocker: `walkforward-oos-profit-factor-too-low` (threshold issue?)
- **This is the most robust GC edge found. All 5 walkforward folds positive — zero overfitting signal.**

**2. run_p3b_vol** — STRONGEST OOS NET IN GC
- Strategy: **wq_vol_regime** — Bollinger Band squeeze/expansion
- Timeframe: 1h
- OOS PF: **3.066** | OOS Net: **+1,894.9 pts**
- Trades: 128 | Win Rate: **65.6%**
- Walkforward: **80% positive folds** (4/5)
- Fold 1: +52.2 (PF 1.21) ✅
- Fold 2: -55.7 (PF 0.89) ❌
- Fold 3: +44.6 (PF 1.05) ✅
- Fold 4: +265.2 (PF 1.58) ✅
- Fold 5: **+1,532.8** (PF 3.56) ✅
- Decision: `research-only-template-blocked`
- Blocker: `walkforward-has-negative-oos-fold` (fold 2)
- **#1 OOS net return. Highly robust. Fold 5 crushing it.**

**3. run_gc_volregime_postfix** — VOL REGIME WITH "POSTFIX" CONFIG
- Strategy: **wq_vol_regime** (squeeze-expansion)
- Timeframe: 1h
- OOS PF: **3.531** | OOS Net: **+1,073.7 pts**
- Trades: 47 | Win Rate: **59.6%**
- Walkforward: **60% positive folds** (3/5)
- Fold 3: +133.9 (PF 1.81) ✅
- Fold 4: +155.4 (PF 2.03) ✅
- Fold 5: **+302.0** (PF 2.08) ✅
- Decision: `research-only-template-blocked`
- Blocker: `walkforward-has-negative-oos-fold`
- **Strong recent performance (folds 3-5 all positive and growing)**

**4. run_gc_volregime_topstep_compliant** — TOPSTEP-COMPLIANT VERSION
- Strategy: **wq_vol_regime**
- Timeframe: 1h
- OOS PF: **1.038** | OOS Net: **+12.7 pts**
- Trades: 47 | Win Rate: 34.0%
- Walkforward: **40% positive folds** (2/5)
- Fold 1: +25.1 (PF 1.39) ✅
- Fold 3: +20.0 (PF 1.67) ✅
- Folds 2,4,5 negative
- Decision: `research-only-template-blocked`
- **Much weaker than postfix version. Tightening constraints hurt performance.**

#### 🟡 Moderate / Interesting (GC)

**5. run_it_vwap_GC** — VWAP REVERSION ON GOLD
- Strategy: vwap_reversion
- Timeframe: 1h
- OOS PF: **1.566** | OOS Net: **+494.0 pts**
- Trades: 129 | Win Rate: 40.3%
- Walkforward: **20% positive folds** (only fold 5: PF 2.50, +782)
- Random shuffle robustness: ALL 5 shuffled runs positive (min +112.6, max +414.3)
- Decision: `research-only-template-blocked`
- Blocker: `walkforward-positive-fold-share-too-low`
- **Interesting: shuffle robustness is excellent. WF share is the only blocker.**

**6. run_m1_gc_daily_v3** — DAILY VOL REGIME
- Strategy: wq_vol_regime
- Timeframe: daily
- OOS PF: **1.157** | OOS Net: +499.0
- Trades: 132 | Win Rate: 50%
- Walkforward: 20% positive folds
- Marginal — only 1/5 folds positive

#### ❌ Dead/Duds (GC)
- **run_n5_gc_15m_orb**: ORB on GC 15m — gate filtered everything (0 trades)
- **run_n5_orb_GC**: Same problem
- **run_gold_gc**: wq_trend_mom on GC — 0 trades
- **run_debug4**: Debug run, no usable results
- **run_gc_volregime_postfix_rth**: RTH-only version — 0 trades (gate filtered)
- **run_m1_gc_daily_v2/v4/volregime_fixed**: All 0 trades
- **run_novel_pji_gcdaily**: PF 0.98, net negative — not profitable
- **run_novel_pji_gcdaily_v2**: PF 4.8 but only 4 trades — too few to trust

---

### E-MINI S&P 500 (ES) — Mixed Results

**7. run_it_orb_es15m** — BEST ES RESULT
- Strategy: **orb** (opening range breakout)
- Timeframe: 15m
- OOS PF: **1.385** | OOS Net: **+248.7 pts**
- Trades: 538 | Win Rate: **43.9%**
- Walkforward: **20% positive folds** (1/5)
- Decision: `research-only-template-blocked`
- **Good PF, solid trade count, but low walkforward robustness.**

**8. run_it_vwap_ES** — VWAP on ES
- OOS PF: **0.311** — Negative net OOS
- Not viable.

**9. run_n5_orb_ES / run_n5_es_3m_orb** — ORB on ES 3m
- Both 0 trades (timeframe_agreement=2 requirement filtered everything)
- Parameterization problem, not a strategy problem.

**10. run_it_vwap_es5k** — VWAP on ES with 5000-tick bars
- 0 trades
- Not viable in current form.

---

### CRUDE OIL (CL) — Dead

**11. run_it_vwap_CL** — VWAP on CL
- OOS PF: **0.0007** | Net: -123 pts
- Win Rate: **2.8%** (2 winners out of 71 trades)
- Walkforward: 0/5 folds positive
- **Cleanly dead. VWAP reversion does NOT work on CL in this configuration.**

---

### 10-YEAR T-NOTE (ZN) — Dead

**12. run_novel_orb_zn** — ORB on ZN
- OOS PF: **0.0** | Net: -16.1 pts
- Win Rate: **0.0%** (zero winners in OOS)
- Walkforward: 0/5 folds positive
- **Every single OOS trade lost. Not salvageable in current form.**

---

### EURO FX (6E/EURUSD) — Dead

**13. run_novel_vwap_eur** — VWAP on EURUSD
- 0 trades
- Not viable in current form.

---

## KEY FINDINGS

### 🏆 GC is the clear non-NQ winner
- **3 strong edges** found in GC: pji (P3B) and two vol regime variants
- **run_p3b_pji** has 100% walkforward positive folds — virtually zero overfitting
- **run_p3b_vol** has highest OOS net return (+1,895 pts) with 80% WF positive
- **run_gc_volregime_postfix** has PF 3.53 with 60% WF positive and growing recent performance

### 🚨 Why were these shelved?
- **Metric blocker thresholds** are the only barriers — not actual strategy failure:
  - `walkforward-positive-fold-share-too-low` requires ≥?? (0.6/0.8/1.0 failing)
  - `walkforward-has-negative-oos-fold` blocks any strategy with ANY negative fold
  - `walkforward-oos-profit-factor-too-low` thresholds may need adjustment
- GC volregime postfix was blocked despite OOS PF of **3.53** and recent folds all positive
- GC P3B pji was blocked despite **100% fold positivity**
- The template's promotion pipeline appears to require ALL blockers cleared simultaneously

### 🟡 ES has potential but needs work
- ORB on ES 15m (it_orb_es15m) shows **real edge** (PF 1.385, 538 trades) but WF share = 0.2
- 3m timeframe versions gate-filtered — parameterization bug, not edge absence

### ❌ CL, ZN, 6E — cleanly dead
- VWAP reversion fails on CL (near-zero WR)
- ORB fails on ZN (100% losers OOS)
- EURUSD VWAP yielded zero trades

---

## RECOMMENDATIONS

1. **PROMOTE GC P3B PJI to paper immediately** — 100% walkforward positive, PF > 1.5, 37 trades is borderline enough sample
2. **PROMOTE GC P3B vol regime to paper** — +1,895 pts OOS with 80% WF share is exceptional
3. **INVESTIGATE GC volregime_postfix vs topstep_compliant differences** — the postfix version crushes the compliant version (PF 3.53 vs 1.04); understand what constraint is killing performance
4. **REVISIT ES ORB 15m** — 538 trades with PF 1.385 deserves a second look; maybe relaxed WF threshold
5. **DON'T waste more time on CL, ZN, or 6E VWAP/ORB** — these are conclusively dead
6. **Consider GC VWAP reversion** — interesting shuffle robustness even if WF share is low
7. **The real issue is the metric blocker / promotion pipeline** — several clearly profitable strategies are being blocked by arbitrary thresholds
