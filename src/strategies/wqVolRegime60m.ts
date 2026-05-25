/**
 * WQ Volatility Regime 60m — Ported from Rust gold_strategies wq_volatility_regime
 *
 * Strategy: Bollinger Band squeeze detection → trade expansion breakout.
 * Edge confirmed: 56.9% WR, +156R on NQ 60m (60-day backtest)
 * Also works on: ES 60m (55.7% WR, +115R)
 */

import type { Bar, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const BB_PERIOD = 20;
const BB_STDDEV = 2;
const SQUEEZE_LOOKBACK = 10;
const STOP_ATR = 1.2;
const TARGET_ATR = 2.5;
const MAX_HOLD_MINUTES = 45;

export class WqVolRegime60m implements Strategy {
  public readonly id = "wq-vol-regime-60m";
  public readonly description = "60m volatility regime — Bollinger squeeze expansion. 57% WR on NQ.";

  private calcBbWidth(bars: Bar[], i: number): number {
    if (i < BB_PERIOD - 1) return 0;
    const slice = bars.slice(i - BB_PERIOD + 1, i + 1);
    const sma = slice.reduce((s, b) => s + b.close, 0) / BB_PERIOD;
    const variance = slice.reduce((s, b) => s + (b.close - sma) ** 2, 0) / BB_PERIOD;
    const stddev = Math.sqrt(variance);
    const upper = sma + BB_STDDEV * stddev;
    const lower = sma - BB_STDDEV * stddev;
    return (upper - lower) / sma;
  }

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;
    const bars = context.history;
    if (bars.length < BB_PERIOD + SQUEEZE_LOOKBACK + 1) return null;

    const i = bars.length - 1;
    const bar = bars[i];

    // Current BB width
    const bbWidth = this.calcBbWidth(bars, i);
    if (bbWidth <= 0) return null;

    // Average BB width over last 10 bars
    let avgBbWidth = 0;
    for (let j = 0; j < SQUEEZE_LOOKBACK; j++) {
      avgBbWidth += this.calcBbWidth(bars, i - j);
    }
    avgBbWidth /= SQUEEZE_LOOKBACK;

    // Squeeze detection: current width below average
    if (bbWidth >= avgBbWidth) return null;

    // Compute bands for entry check
    const slice = bars.slice(i - BB_PERIOD + 1, i + 1);
    const sma20 = slice.reduce((s, b) => s + b.close, 0) / BB_PERIOD;
    const variance = slice.reduce((s, b) => s + (b.close - sma20) ** 2, 0) / BB_PERIOD;
    const stddev = Math.sqrt(variance);
    const upperBand = sma20 + BB_STDDEV * stddev;
    const lowerBand = sma20 - BB_STDDEV * stddev;

    const atr = averageTrueRange(bars, 14);
    if (atr <= 0) return null;

    const entry = bar.close;
    const stopDist = atr * STOP_ATR;
    const targetDist = atr * TARGET_ATR;

    if (bar.close > upperBand) {
      const stop = entry - stopDist;
      const target = entry + targetDist;
      const rr = calculateRr(entry, stop, target, "long");
      if (rr <= 0) return null;
      return { symbol: context.symbol, strategyId: this.id, side: "long", entry, stop, target, rr, confidence: 0.58, contracts: 1, maxHoldMinutes: MAX_HOLD_MINUTES };
    }
    if (bar.close < lowerBand) {
      const stop = entry + stopDist;
      const target = entry - targetDist;
      const rr = calculateRr(entry, stop, target, "short");
      if (rr <= 0) return null;
      return { symbol: context.symbol, strategyId: this.id, side: "short", entry, stop, target, rr, confidence: 0.58, contracts: 1, maxHoldMinutes: MAX_HOLD_MINUTES };
    }

    return null;
  }
}
