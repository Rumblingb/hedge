# Backlog — Items 2 & 3

## Item 2: ATR Regime Gating → freeMacroContext.ts

**Source**: ochenryceo/trading-factory — ATR regime gating (from README)
**Current State**: freeMacroContext.ts calculates VIX, tail risk, credit, equity trend.
**Missing**: NQ-specific ATR regime classification per session.

### Implementation Plan

**File**: `src/signals/atrRegime.ts`

```typescript
export enum AtrRegime {
  LOW = "LOW",       // ATR < 20-period percentile-25
  NORMAL = "NORMAL", // ATR between percentile 25-75
  HIGH = "HIGH",     // ATR > 20-period percentile-75
  EXTREME = "EXTREME", // ATR > 50-period percentile-90
}

export interface AtrRegimeSnapshot {
  regime: AtrRegime;
  atr: number;
  percentile20: number;
  sessionWindow: string; // e.g. "30m"
  timestamp: string;
}

export function classifyAtrRegime(currentAtr: number, atrHistory: number[]): AtrRegime;
export function loadAtrSnapshot(onDemand?: boolean): Promise<AtrRegimeSnapshot | null>;
```

**Wire into**: `freeMacroContext.ts` — add `atrRegime: AtrRegime` to `MacroContextSnapshot`
**Wire into**: `strategyFactory.ts` — breakout/trend strategies check ATR regime before entry
**Wire into**: `pipeline.ts` — ATR regime becomes one of the regime gates required for VALIDATION stage

**Data**: Use our existing NQ-30m-60d.csv to build the ATR percentile baseline.

---

## Item 3: Shadow Execution / Fill Probability → backtest.ts

**Source**: vincent212/kaspar-hft — shadow execution algorithm
**Current State**: backtest.ts assumes fills at signal price instantly (standard backtest assumption).
**Missing**: Queue-position-aware fill simulation for more realistic backtest results.

### Implementation Plan

**File**: `src/engine/fillSimulator.ts`

```typescript
export interface FillConfig {
  /** Probability of fill at the signal bar's price level (default 0.8) */
  baseFillRate: number;
  /** Queue position decay: each additional tick away reduces fill rate by this factor (default 0.7) */
  distanceDecay: number;
  /** Volume ratio threshold: if trade volume / avg volume < this, fill rate halves (default 0.3) */
  minVolumeRatio: number;
  /** Spread width in ticks — wider spread = lower fill rate (default 2 for NQ) */
  typicalSpreadTicks: number;
}

export function simulateFill(
  signalPrice: number,
  bar: { open: number; high: number; low: number; close: number; volume: number },
  avgVolume: number,
  config?: Partial<FillConfig>
): {
  filled: boolean;
  fillPrice: number;
  fillProbability: number;
  slippage: number;
};
```

**Wire into**: `backtest.ts` — replace instant-fill assumption with `simulateFill()` in trade execution
**Wire into**: `pipeline.ts` — add `fillSlippage` to metrics tracked during VALIDATION stage

**Data**: Use our `dom_micro_edges.py` output to estimate typical spread widths for NQ.

---

## Dependency Order

1. ATR regime → can be built standalone from existing NQ bar data ✓
2. Fill simulation → depends on spread estimation from DOM data ✓

Both are independent and can be built in parallel.
