/**
 * WQ Trend Momentum 60m — Ported from Rust gold_strategies wq_trend_momentum
 *
 * Strategy: SMA(5) vs SMA(20) crossover with trend confirmation.
 * Edge confirmed: 60.2% WR, +198R on NQ 60m (60-day backtest)
 * Also works on: ES 60m (57% WR, +110R)
 */

import type { Bar, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const STOP_ATR = 1.5;
const TARGET_ATR = 2.0;
const MAX_HOLD_MINUTES = 60;

export class WqTrendMom60m implements Strategy {
  public readonly id = "wq-trend-mom-60m";
  public readonly description = "60m trend momentum — SMA5/SMA20 crossover. 60% WR on NQ.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;
    const bars = context.history;
    if (bars.length < 21) return null;

    const i = bars.length - 1;
    const bar = bars[i];

    // SMA(5) and SMA(20)
    const sma5 = bars.slice(i - 4, i + 1).reduce((s, b) => s + b.close, 0) / 5;
    const sma20 = bars.slice(i - 19, i + 1).reduce((s, b) => s + b.close, 0) / 20;

    const atr = averageTrueRange(bars, 14);
    if (atr <= 0) return null;

    const entry = bar.close;
    const stopDist = atr * STOP_ATR;
    const targetDist = atr * TARGET_ATR;

    const trendUp = sma5 > sma20 && bar.close > sma20;
    const trendDown = sma5 < sma20 && bar.close < sma20;

    if (trendUp) {
      const stop = entry - stopDist;
      const target = entry + targetDist;
      const rr = calculateRr(entry, stop, target, "long");
      if (rr <= 0) return null;
      return { symbol: context.symbol, strategyId: this.id, side: "long", entry, stop, target, rr, confidence: 0.55, contracts: 1, maxHoldMinutes: MAX_HOLD_MINUTES };
    }
    if (trendDown) {
      const stop = entry + stopDist;
      const target = entry - targetDist;
      const rr = calculateRr(entry, stop, target, "short");
      if (rr <= 0) return null;
      return { symbol: context.symbol, strategyId: this.id, side: "short", entry, stop, target, rr, confidence: 0.55, contracts: 1, maxHoldMinutes: MAX_HOLD_MINUTES };
    }

    return null;
  }
}
