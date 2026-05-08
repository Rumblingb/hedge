# Macro Context Wiring Plan
**Status**: Plumbing done. Behavior changes pending founder review.
**Written**: 2026-05-05 by Claude Code night session

## What's done (safe, no behavior change)

`MacroContext` interface added to `src/domain.ts`. Optional field `macro?` on `StrategyContext`.
No strategy reads it yet. OOS results unchanged. TypeScript clean.

---

## Phase 1: Load HMM + COT into backtest (1-2 hrs, no strategy behavior change)

**File**: `src/engine/backtest.ts`

Before the main bar loop, load two JSON files:

```typescript
// Load HMM regime map: symbol → regime string
const hmmState = await loadHmmState('.rumbling-hedge/state/hmm-regime.json');
// Load COT z-scores: symbol → dealer z52
const cotScores = await loadCotScores('.rumbling-hedge/state/cot-status.latest.json');

// In the bar loop, pass macro context:
const macro: MacroContext = {
  hmmRegime: hmmState[bar.symbol]?.current_regime,
  hmmConfidence: hmmState[bar.symbol]?.confidence ?? 0.5,
  cotDealerZ52: cotScores[bar.symbol]?.z52,
};
const signal = strategy.generateSignal({ ..., macro });
```

**Risk**: Zero. No strategy reads `macro` yet. Pure data plumbing.

---

## Phase 2: HMM regime gates (requires founder sign-off, run OOS first)

**Rationale**: NQ=range-chop, CL=trending-down, GC=range-chop. Regime-inappropriate strategies fail in wrong regimes.

**Proposed gates** (verify OOS testTradeCount ≥ 8 after each change):

| Strategy | Gate | Reason |
|----------|------|--------|
| `session-momentum` | Only in `trending` regime | Momentum strategies lose in chop |
| `liquidity-reversion` | Only in `range-chop` or `high-vol` | Reversion needs mean-reversion regime |
| `ict-displacement` | Only in `trending` | Displacement requires directional move |
| `vwap-reversion` | Only in `range-chop` | VWAP reversion needs ranging market |
| `opening-range-reversal` | All regimes (keep unrestricted) | Works across regime types |

**Implementation**: In each strategy's `generateSignal`, before the main logic:
```typescript
if (context.macro?.hmmRegime && !allowedRegimes.has(context.macro.hmmRegime)) {
  return null;
}
```

**CRITICAL CHECK**: Run `oos-rolling` after each gate addition. testTradeCount must stay ≥ 8.
If it drops below 8, make the gate a soft multiplier (lower confidence) instead of hard null.

**Soft multiplier version (safer)**:
```typescript
const regimeMultiplier = context.macro?.hmmRegime === 'range-chop' ? 1.0 :
                         context.macro?.hmmRegime === 'trending' ? 0.6 : 0.4;
// Apply to confidence: signal.confidence *= regimeMultiplier
// If multiplied confidence < 0.4, return null
```

---

## Phase 3: COT macro bias gate (1 day, run after Phase 2 validates)

**Current COT z-scores** (Apr 28, 2026):
- ZN: z52 = -1.40 (dealers VERY short bonds → short bias on ZN)
- CL: z52 = -1.15 (dealers short crude → short bias on CL)
- GC: z52 = +0.75 (dealers modestly long gold → neutral)
- ES: z52 = -0.15 (neutral)
- NQ: z52 = +0.07 (neutral)

**Gate logic**:
```typescript
function cotBiasAllowed(side: 'long' | 'short', cotZ?: number): boolean {
  if (!cotZ || Math.abs(cotZ) < 1.0) return true; // neutral → allow both
  if (cotZ < -1.0 && side === 'long') return false; // dealers short → no longs
  if (cotZ > +1.0 && side === 'short') return false; // dealers long → no shorts
  return true;
}
```

**Where to add**: `evaluateSignalGuardrails()` in `src/risk/guardrails.ts`. 
Requires COT data to be loaded and passed through (Phase 1 prerequisite).

**Expected impact**: Eliminates ~15-20% of signals that go against institutional positioning.
Win rate should improve; trade count drops slightly. Net expectancy improves.

---

## Phase 4: Capitulation Score + Tail Trade (1 week, needs options data)

**Prerequisites**: Polygon Starter ($29/mo) for put/call ratio. VIX spot data (free via Yahoo).

**Capitulation Score formula**:
```
cap_score = 0
+ 1 if COT leveraged fund short z52 < -1.5 (extreme short)
+ 1 if VIX > 30 (fear elevated)
+ 1 if VIX term structure in backwardation (stress mode)
+ 1 if put/call ratio > 1.5 (retail panic)
+ 1 if HMM regime = "high-vol" for NQ or ES
```

**Trigger**: When cap_score ≥ 3/5 → add mean-reversion bias, reduce maxContracts to 1,
extend maxHoldMinutes to 60 for all active strategies. Log to OUTBOX as "Capitulation Alert."

**Expected**: Fires 6-10×/year. Each event is the highest-edge trade of the quarter.

---

## Phase 5: Three Scalp Strategies (2 weeks, needs L2 + economic calendar)

### Type A: Event Spike Fade
**Data needed**: ForexFactory RSS (free) for economic event times
**Logic**:
1. At scheduled macro event (NFP/CPI/FOMC), watch first 3 bars
2. If any bar is > 2.5× ATR → spike detected
3. Fade direction of spike with target = 80% retrace, stop = 110% of spike
4. Max hold 15 min, size 1 contract

### Type B: Opening Stop Hunt
**Data needed**: Current OHLCV (already have)
**Logic**:
1. In 08:30-08:35 CT, watch for sweep of prior session high/low
2. If sweep bar closes BACK inside prior session range → stop hunt confirmed
3. Enter in reversal direction, target mid-session VWAP, stop 0.5× ATR beyond sweep
4. Max hold 30 min, size 2 contracts

### Type C: L2 Absorption (future)
**Data needed**: Databento CME MBO (~$30/mo)
**Logic**: 3 consecutive bars with bid/ask imbalance > 4:1 at prior level → entry in absorption direction

---

## Decision checklist for Rajiv

Before Phase 2 goes live:
- [ ] Run `oos-rolling 30d 1 20 5 1` → verify testTradeCount ≥ 8 with new gates
- [ ] Check: does HMM data cover the full OOS test period? (Apr 29-May 4). If not, Phase 2 is leaking training data.
- [ ] Decide: hard gate vs soft confidence multiplier?
- [ ] Approve Phase 3 COT gate (low risk, mostly eliminates bad directional trades)

For scalps (Phase 5):
- [ ] Subscribe to Polygon Starter ($29/mo) for GEX + options chain
- [ ] Add ForexFactory RSS parser to prediction-cycle pipeline
- [ ] Decision on L2 data (Databento ~$30/mo for CME MBO feed)

