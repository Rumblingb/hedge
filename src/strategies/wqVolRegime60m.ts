/**
 * WQ Volatility Regime 60m — Rust param_sweep optimized vol-regime ratio
 *
 * Strategy: Short-term vs long-term volatility ratio.
 * When short-term vol >> long-term vol (st > 1.6): high vol → short (fade)
 * When short-term vol << long-term vol (lt < 0.8): low vol → long (trend)
 *
 * Base sweep (60m NQ): slk=10, llk=20, st=1.6, lt=0.8, eo=5 → +210.64R, 71.05% WR
 * This matches the Rust param_sweep wq_vol_regime function.
 *
 * Research-only until promotion gates clear.
 */

import type { Bar, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const SHORT_LOOKBACK = 10;   // slk=10: short-term vol over 10 bars
const LONG_LOOKBACK = 20;    // llk=20: long-term vol over 20 bars
const SHORT_THRESHOLD = 1.6; // st=1.6: short_vol/long_vol > 1.6 → high vol → short
const LONG_THRESHOLD = 0.8;  // lt=0.8: short_vol/long_vol < 0.8 → low vol → long
const EXIT_OFFSET = 5;       // eo=5 (time-based in sweep; ATR stops below for robustness)
const STOP_ATR = 1.2;
const TARGET_ATR = 2.0;
const MAX_HOLD_MINUTES = 45;

export class WqVolRegime60m implements Strategy {
  public readonly id = "wq-vol-regime-60m";
  public readonly description =
    "60m volatility regime — vol ratio breakout (slk=10, llk=20, st=1.6, lt=0.8). Rust param_sweep optimized: +210.64R, 71.05% WR on NQ. Research-only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;

    const bars = [...context.history, context.bar];
    const i = bars.length - 1;
    const bar = bars[i];

    // Need enough bars: long_lookback + buffer for vol computation
    if (i < LONG_LOOKBACK + 14) return null;

    // Short-term volatility: average range over SHORT_LOOKBACK bars
    const shortVol =
      bars.slice(i - SHORT_LOOKBACK, i).reduce((s, b) => s + (b.high - b.low), 0) / SHORT_LOOKBACK;

    // Long-term volatility: average range over LONG_LOOKBACK bars (before current)
    const longVol =
      bars.slice(i - LONG_LOOKBACK, i).reduce((s, b) => s + (b.high - b.low), 0) / LONG_LOOKBACK;

    if (longVol <= 0) return null;

    const volRatio = shortVol / longVol;

    // ATR for stop/target sizing
    const atr = averageTrueRange(context.history, 14);
    if (atr <= 0) return null;

    const entry = bar.close;

    // HIGH VOL: short_vol/long_vol > 1.6 → volatility expansion → short (fade the breakout)
    if (volRatio > SHORT_THRESHOLD) {
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
        confidence: 0.62,
        contracts: 1,
        maxHoldMinutes: MAX_HOLD_MINUTES,
        meta: { volRatio: Number(volRatio.toFixed(4)), regime: "high-vol" },
      };
    }

    // LOW VOL: short_vol/long_vol < 0.8 → volatility compression → long (ride expansion)
    if (volRatio < LONG_THRESHOLD) {
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
        confidence: 0.62,
        contracts: 1,
        maxHoldMinutes: MAX_HOLD_MINUTES,
        meta: { volRatio: Number(volRatio.toFixed(4)), regime: "low-vol" },
      };
    }

    return null;
  }
}
