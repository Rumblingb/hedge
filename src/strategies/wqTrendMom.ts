import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { inferBarIntervalMinutes } from "../utils/time.js";

/**
 * WQ Trend Momentum — Rust param_sweep optimized (ss=20, sl=60, vt=1.3, eo=8)
 *
 * Strategy: SMA(20) vs SMA(60) crossover with volume confirmation.
 * On 15m NQ data (Rust sweep): 60.96% WR, +252.69R total.
 * On 30m NQ data (Rust sweep): 61.0% WR, +252.69R total.
 *
 * Parameters (bar-count, independent of timeframe):
 * - sma_short = 20 bars (≈5h on 15m bars)
 * - sma_long  = 60 bars (≈15h on 15m bars)
 * - vol_ratio_threshold = 1.3 (volume must exceed 1.3× trailing avg)
 * - Exit via ATR-based stop (eo=8 in sweep was time-based; ATR stops are more robust live)
 *
 * Only generates signals when:
 * 1. Close > SMA20 > SMA60 (long) or Close < SMA20 < SMA60 (short)
 * 2. Volume > 1.3× trailing average
 *
 * Research-only until promotion gates clear.
 */
function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);

  if (rr <= 0) {
    return null;
  }

  return {
    symbol: context.symbol,
    strategyId: "wq-trend-mom",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 60,
    meta: {
      lookbackBars: 60,
      barIntervalMinutes,
    },
  };
}

export class WqTrendMomStrategy implements Strategy {
  public readonly id = "wq-trend-mom";
  public readonly description =
    "WQ Trend Momentum — SMA20/SMA60 crossover + 1.3× vol confirmation. Rust param_sweep optimized (ss=20, sl=60, vt=1.3). Research-only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Need at least 60 history bars for SMA60 + 14 for ATR
    if (context.history.length < 60) {
      return null;
    }

    const bars = [...context.history, context.bar];
    const i = bars.length - 1;

    // SMA20: average of last 20 closes (including current)
    const sma20 =
      bars.slice(i - 19, i + 1).reduce((sum, bar) => sum + bar.close, 0) / 20.0;
    // SMA60: average of last 60 closes (including current)
    const sma60 =
      bars.slice(i - 59, i + 1).reduce((sum, bar) => sum + bar.close, 0) / 60.0;

    if (sma60 <= 0) return null;

    // Volume ratio: current volume vs 10-bar trailing average (matches Rust: avg_vol_window(bars, i, 10))
    const avgVol10 = context.history.slice(-10).reduce((s, b) => s + b.volume, 0) / 10;
    if (avgVol10 <= 0) return null;
    const volRatio = context.bar.volume / avgVol10;

    // ATR for stop/target sizing
    const atr = averageTrueRange(context.history, 14);
    if (atr <= 0) {
      return null;
    }

    const entry = context.bar.close;
    const prevTs = context.history[context.history.length - 1];
    const barIntervalMinutes = inferBarIntervalMinutes(
      prevTs?.ts ?? context.bar.ts,
      context.bar.ts
    );

    // LONG: close > sma20 > sma60 AND volume > 1.3× avg
    if (entry > sma20 && sma20 > sma60 && volRatio > 1.3) {
      const stop = entry - atr * 1.5;
      const target = entry + atr * 2.0;
      const rr = calculateRr(entry, stop, target, "long");
      if (rr <= 0) return null;
      return buildSignal({ context, side: "long", stop, target, confidence: 0.58, barIntervalMinutes });
    }

    // SHORT: close < sma20 < sma60 AND volume > 1.3× avg
    if (entry < sma20 && sma20 < sma60 && volRatio > 1.3) {
      const stop = entry + atr * 1.5;
      const target = entry - atr * 2.0;
      const rr = calculateRr(entry, stop, target, "short");
      if (rr <= 0) return null;
      return buildSignal({ context, side: "short", stop, target, confidence: 0.58, barIntervalMinutes });
    }

    return null;
  }
}
