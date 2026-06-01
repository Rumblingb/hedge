/**
 * WQ Trend Momentum 60m — Rust param_sweep optimized, timeframe-adjusted
 *
 * Base sweep (15m NQ): ss=20, sl=60, vt=1.3, eo=8 → +252.69R
 * Adjusted for 60m data: ss=5, sl=15 (same 5h/15h time horizon)
 * Volume threshold: 1.3× trailing average
 * Exit: ATR-based stops (time-based eo=8 may be added later)
 *
 * Research-only until promotion gates clear.
 */

import type { Bar, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const SMA_SHORT = 5;    // ≈5h on 60m bars (matches ss=20 on 15m)
const SMA_LONG = 15;    // ≈15h on 60m bars (matches sl=60 on 15m)
const VOL_THRESHOLD = 1.3;
const STOP_ATR = 1.3;  // Matches Rust-proven vt=1.3 from param_sweep
const TARGET_ATR = 2.0;
const MAX_HOLD_MINUTES = 60;

export class WqTrendMom60m implements Strategy {
  public readonly id = "wq-trend-mom-60m";
  public readonly description =
    "60m trend momentum — SMA5/SMA15 crossover + 1.3× vol confirmation. Timeframe-adjusted from Rust-proven ss=20, sl=60. Research-only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;
    if (context.history.length < SMA_LONG + 1) return null;

    const bars = [...context.history, context.bar];
    const i = bars.length - 1;
    const bar = bars[i];

    // SMA(short) and SMA(long)
    const smaShort = bars.slice(i - SMA_SHORT + 1, i + 1).reduce((s, b) => s + b.close, 0) / SMA_SHORT;
    const smaLong = bars.slice(i - SMA_LONG + 1, i + 1).reduce((s, b) => s + b.close, 0) / SMA_LONG;
    if (smaLong <= 0) return null;

    // Volume ratio: current vs 10-bar trailing average
    const avgVol10 = context.history.slice(-10).reduce((s, b) => s + b.volume, 0) / 10;
    if (avgVol10 <= 0) return null;
    const volRatio = bar.volume / avgVol10;

    const atr = averageTrueRange(bars, 14);
    if (atr <= 0) return null;

    const entry = bar.close;

    // LONG: close > smaShort > smaLong AND volume > 1.3× avg
    if (entry > smaShort && smaShort > smaLong && volRatio > VOL_THRESHOLD) {
      const stop = entry - atr * STOP_ATR;
      const target = entry + atr * TARGET_ATR;
      const rr = calculateRr(entry, stop, target, "long");
      if (rr <= 0) return null;
      return { symbol: context.symbol, strategyId: this.id, side: "long", entry, stop, target, rr, confidence: 0.58, contracts: 1, maxHoldMinutes: MAX_HOLD_MINUTES };
    }

    // SHORT: close < smaShort < smaLong AND volume > 1.3× avg
    if (entry < smaShort && smaShort < smaLong && volRatio > VOL_THRESHOLD) {
      const stop = entry + atr * STOP_ATR;
      const target = entry - atr * TARGET_ATR;
      const rr = calculateRr(entry, stop, target, "short");
      if (rr <= 0) return null;
      return { symbol: context.symbol, strategyId: this.id, side: "short", entry, stop, target, rr, confidence: 0.58, contracts: 1, maxHoldMinutes: MAX_HOLD_MINUTES };
    }

    return null;
  }
}
