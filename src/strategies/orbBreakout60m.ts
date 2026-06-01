/**
 * Orb Breakout 60m — Rust param_sweep opening range breakout, timeframe-adjusted
 *
 * Strategy: Fixed opening range breakout with volume confirmation.
 * The opening range is computed from the first bars[0..RANGE_WINDOW] of the
 * available history. Subsequent bars that break out above/below this range
 * with elevated volume (>1.3× trailing avg) trigger directional signals.
 *
 * Base sweep (15m NQ): rw=8/10/12, vt=1.3, eo=8 → +385.21R (best edge)
 * Sweep (30m NQ): rw=8, vt=1.3, eo=8 → +280.94R
 * Adjusted for 60m: rw=4 (4-bar range ≈ 4h, comparable to 12×15m), vt=1.3
 *
 * Targets: NQ, ES
 * Research-only until promotion gates clear.
 */

import type { Bar, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const RANGE_WINDOW = 4;   // 4-bar opening range on 60m (≈4h, matches 12×15m on 15m sweep)
const VOL_THRESHOLD = 1.3; // volume > 1.3× trailing average
const STOP_ATR = 1.2;
const TARGET_ATR = 2.0;
const MAX_HOLD_MINUTES = 240; // 4 hours — covers a reasonable swing

/**
 * Compute a fixed opening range from the first RANGE_WINDOW bars of history.
 * Returns {rangeHigh, rangeLow} or null if insufficient data / degenerate range.
 */
function computeOpeningRange(bars: Bar[]): { rangeHigh: number; rangeLow: number } | null {
  if (bars.length < RANGE_WINDOW) return null;
  const openingBars = bars.slice(0, RANGE_WINDOW);
  let rangeHigh = -Infinity;
  let rangeLow = Infinity;
  for (const b of openingBars) {
    if (b.high > rangeHigh) rangeHigh = b.high;
    if (b.low < rangeLow) rangeLow = b.low;
  }
  if (rangeHigh <= rangeLow) return null;
  return { rangeHigh, rangeLow };
}

export class OrbBreakout60m implements Strategy {
  public readonly id = "orb-breakout-60m";
  public readonly description =
    "60m opening range breakout — fixed range from first 4 bars, breakout with volume >1.3× avg. Timeframe-adjusted from Rust-proven rw=8/10/12, vt=1.3. Research-only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;

    // Need enough history: RANGE_WINDOW for opening range + 14 for ATR + buffer
    if (context.history.length < RANGE_WINDOW + 14) return null;

    // Compute fixed opening range from the first RANGE_WINDOW bars of the available history
    const range = computeOpeningRange(context.history);
    if (!range) return null;

    const { rangeHigh, rangeLow } = range;

    // Current bar index in history (0-indexed); must be PAST the opening range window
    const barIndex = context.history.length - 1;
    if (barIndex < RANGE_WINDOW) return null;

    // Volume check: current volume > 1.3× trailing 10-bar average (matches Rust sweep)
    const avgVol10 = context.history.slice(-10).reduce((s, b) => s + b.volume, 0) / 10;
    if (avgVol10 <= 0) return null;
    if (context.bar.volume < avgVol10 * VOL_THRESHOLD) return null;

    // ATR for stop/target sizing
    const atr = averageTrueRange(context.history, 14);
    if (atr <= 0) return null;

    const entry = context.bar.close;

    // LONG breakout: close above range high
    if (entry > rangeHigh) {
      const stop = entry - atr * STOP_ATR;
      const target = entry + atr * TARGET_ATR;
      const rr = calculateRr(entry, stop, target, "long");
      if (rr <= 0) return null;
      return {
        symbol: context.symbol,
        strategyId: this.id,
        side: "long",
        entry,
        stop,
        target,
        rr,
        confidence: 0.56,
        contracts: 1,
        maxHoldMinutes: MAX_HOLD_MINUTES,
        meta: { rangeHigh: rangeHigh, rangeLow: rangeLow, atr },
      };
    }

    // SHORT breakout: close below range low
    if (entry < rangeLow) {
      const stop = entry + atr * STOP_ATR;
      const target = entry - atr * TARGET_ATR;
      const rr = calculateRr(entry, stop, target, "short");
      if (rr <= 0) return null;
      return {
        symbol: context.symbol,
        strategyId: this.id,
        side: "short",
        entry,
        stop,
        target,
        rr,
        confidence: 0.56,
        contracts: 1,
        maxHoldMinutes: MAX_HOLD_MINUTES,
        meta: { rangeHigh, rangeLow, atr },
      };
    }

    return null;
  }
}
