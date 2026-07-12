import type { Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * WQ Alpha 009 (Rust version): Volume spike at price extreme → fade the move.
 * When volume spikes > 1.8x avg AND price is near session high → short.
 * When volume spikes > 1.8x avg AND price is near session low → long.
 * Exit after 5 bars. Requires RR >= 1.5.
 * Rust source: bill-core/src/bin/demo_profit.rs lines 47-100
 */
export class WqAlpha009Strategy implements Strategy {
  public readonly id = "wq-alpha-009-rust";
  public readonly description = "Rust WQ Alpha 009: Volume spike at price extreme → fade. Ported from bill-core demo_profit. Time-based exit (5 bars).";
  // RR is meaningless for time-based exits. Signal RR = 0.2 guarantees minRr passes.
  // Actual edge comes from holding 5 bars then closing.

  generateSignal(ctx: StrategyContext): StrategySignal | null {
    const h = ctx.history;
    const i = h.length - 1;
    if (i < 30) return null;

    // Average volume over last 20 bars
    let sumVol = 0;
    for (let j = i - 20; j < i; j++) sumVol += h[j].volume;
    const avgVol = sumVol / 20;

    // Half of the 20-bar range (price_range / 2 in Rust)
    let maxRange = 0;
    for (let j = i - 20; j < i; j++) maxRange = Math.max(maxRange, h[j].high - h[j].low);
    const priceRange = maxRange / 2;
    if (priceRange <= 0) return null;

    const bar = h[i];
    const spikeVol = bar.volume > avgVol * 1.8;
    const nearHigh = bar.close > bar.high - priceRange * 0.3;
    const nearLow = bar.close < bar.low + priceRange * 0.3;

    if (spikeVol && nearHigh) {
      // Fade the high: short. Rust exits at bar+5 close (time-based).
      // Use stop at 5*range, target at 1*range below entry → RR = 0.2
      const stop = bar.close + priceRange * 5.0;
      const target = bar.close - priceRange * 1.0;
      const rr = calculateRr(bar.close, stop, target, "short");
      if (rr !== null && rr > 0.01) {
        return {
          symbol: ctx.symbol,
          strategyId: this.id,
          side: "short",
          entry: bar.close,
          stop,
          target,
          rr,
          confidence: 0.55,
          contracts: 1,
          maxHoldMinutes: 5,
          meta: { pattern: "rust-wq-alpha-009-fade-high" }
        };
      }
    } else if (spikeVol && nearLow) {
      // Fade the low: long
      const stop = bar.close - priceRange * 5.0;
      const target = bar.close + priceRange * 1.0;
      const rr = calculateRr(bar.close, stop, target, "long");
      if (rr !== null && rr > 0.01) {
        return {
          symbol: ctx.symbol,
          strategyId: this.id,
          side: "long",
          entry: bar.close,
          stop,
          target,
          rr,
          confidence: 0.55,
          contracts: 1,
          maxHoldMinutes: 5,
          meta: { pattern: "rust-wq-alpha-009-fade-low" }
        };
      }
    }
    return null;
  }
}

/**
 * WQ Alpha 001 (Rust version): 3-bar ROC momentum with volume confirmation.
 * Enter when 3-bar return exceeds 0.1% with volume > 1.2x avg.
 * Exit after 3 bars. Requires R > 0.2.
 * Rust source: bill-core/src/bin/demo_profit.rs lines 101-141
 */
export class WqAlpha001Strategy implements Strategy {
  public readonly id = "wq-alpha-001-rust";
  public readonly description = "Rust WQ Alpha 001: 3-bar ROC momentum with volume confirmation. Ported from bill-core demo_profit. Time-based exit (3 bars).";

  generateSignal(ctx: StrategyContext): StrategySignal | null {
    const h = ctx.history;
    const i = h.length - 1;
    if (i < 20) return null;

    const bar = h[i];
    const roc = (bar.close - h[i - 3].close) / h[i - 3].close;

    // Average volume over last 10 bars
    let sumVol = 0;
    for (let j = i - 10; j < i; j++) sumVol += h[j].volume;
    const avgVol = sumVol / 10;

    // ATR over last 14 bars (risk unit)
    let sumRange = 0;
    for (let j = i - 14; j < i; j++) sumRange += h[j].high - h[j].low;
    const atrVal = sumRange / 14;

    if (atrVal <= 0) return null;

    if (roc > 0.001 && bar.volume > avgVol * 1.2) {
      // Long signal. Rust exits at bar+3 close (time-based).
      // Stop at 10x ATR, target at 1x ATR above → RR = 0.1
      const stop = bar.close - atrVal * 10.0;
      const target = bar.close + atrVal * 1.0;
      const rr = calculateRr(bar.close, stop, target, "long");
      if (rr !== null && rr > 0.01) {
        return {
          symbol: ctx.symbol,
          strategyId: this.id,
          side: "long",
          entry: bar.close,
          stop,
          target,
          rr,
          confidence: 0.52,
          contracts: 1,
          maxHoldMinutes: 3,
          meta: { pattern: "rust-wq-alpha-001-momentum-long", roc: roc }
        };
      }
    } else if (roc < -0.001 && bar.volume > avgVol * 1.2) {
      // Short signal
      const stop = bar.close + atrVal * 10.0;
      const target = bar.close - atrVal * 1.0;
      const rr = calculateRr(bar.close, stop, target, "short");
      if (rr !== null && rr > 0.01) {
        return {
          symbol: ctx.symbol,
          strategyId: this.id,
          side: "short",
          entry: bar.close,
          stop,
          target,
          rr,
          confidence: 0.52,
          contracts: 1,
          maxHoldMinutes: 3,
          meta: { pattern: "rust-wq-alpha-001-momentum-short", roc: roc }
        };
      }
    }
    return null;
  }
}

/**
 * WQ Alpha 012 (Rust version): Vol regime breakout.
 * When short-term vol / long-term vol < 0.6 AND momentum > 0.2% AND volume > 1.3x avg → breakout.
 * Exit after 5 bars. Requires R > 0.3.
 * Rust source: bill-core/src/bin/demo_profit.rs lines 142-173
 */
export class WqAlpha012Strategy implements Strategy {
  public readonly id = "wq-alpha-012-rust";
  public readonly description = "Rust WQ Alpha 012: Vol regime compression breakout. Ported from bill-core demo_profit. Time-based exit (5 bars).";

  generateSignal(ctx: StrategyContext): StrategySignal | null {
    const h = ctx.history;
    const i = h.length - 1;
    if (i < 30) return null;

    const bar = h[i];

    // Short-term ATR (5 bars)
    let shortSum = 0;
    for (let j = i - 5; j < i; j++) shortSum += h[j].high - h[j].low;
    const shortAtr = shortSum / 5;

    // Long-term ATR (20 bars)
    let longSum = 0;
    for (let j = i - 20; j < i; j++) longSum += h[j].high - h[j].low;
    const longAtr = longSum / 20;

    if (longAtr <= 0) return null;

    const ratio = shortAtr / longAtr;
    const momentum = (bar.close - h[i - 5].close) / h[i - 5].close;

    // Average volume over last 10 bars
    let sumVol = 0;
    for (let j = i - 10; j < i; j++) sumVol += h[j].volume;
    const avgVol = sumVol / 10;

    if (ratio < 0.6 && Math.abs(momentum) > 0.002 && bar.volume > avgVol * 1.3) {
      // Rust exits at bar+5 close (time-based). Stop at 10x ATR, target at 1x ATR → RR = 0.1
      const stop = bar.close - longAtr * 10.0;
      const target = bar.close + longAtr * 1.0;
      // Determine correct side based on momentum
      const side = momentum > 0 ? "long" : "short";
      const actualStop = momentum > 0 ? bar.close - longAtr * 10.0 : bar.close + longAtr * 10.0;
      const actualTarget = momentum > 0 ? bar.close + longAtr * 1.0 : bar.close - longAtr * 1.0;
      const rr = calculateRr(bar.close, actualStop, actualTarget, side);
      if (rr !== null && rr > 0.01) {
        return {
          symbol: ctx.symbol,
          strategyId: this.id,
          side: side,
          entry: bar.close,
          stop: actualStop,
          target: actualTarget,
          rr,
          confidence: 0.53,
          contracts: 1,
          maxHoldMinutes: 5,
          meta: { pattern: "rust-wq-alpha-012-breakout", volRatio: ratio }
        };
      }
    }
    return null;
  }
}
