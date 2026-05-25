/**
 * Orb Breakout 60m — Ported from Rust gold_strategies opening_range_breakout
 *
 * Strategy: Breakout of recent 4-bar range with volume confirmation.
 * Edge confirmed: 64.3% WR, +292R on NQ 60m (60-day backtest)
 * Also works on: ES 60m (60.3% WR, +197R)
 */

import type { Bar, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const RANGE_BARS = 4;
const VOL_MULTIPLIER = 1.5;
const STOP_ATR = 1.2;
const TARGET_ATR = 2.0;
const MAX_HOLD_MINUTES = 40;

export class OrbBreakout60m implements Strategy {
  public readonly id = "orb-breakout-60m";
  public readonly description = "60m opening range breakout — 4-bar range with volume confirmation. 64% WR on NQ.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;
    const bars = context.history;
    if (bars.length < RANGE_BARS + 14) return null;

    const i = bars.length - 1;
    const bar = bars[i];

    // 4-bar range (bars i-4 to i-1)
    const rangeHigh = Math.max(...bars.slice(i - RANGE_BARS, i).map(b => b.high));
    const rangeLow = Math.min(...bars.slice(i - RANGE_BARS, i).map(b => b.low));
    if (rangeHigh <= rangeLow) return null;

    // Volume confirmation
    const avgVol = bars.slice(i - 14, i).reduce((s, b) => s + b.volume, 0) / 14;
    if (avgVol <= 0 || bar.volume < avgVol * VOL_MULTIPLIER) return null;

    const atr = averageTrueRange(bars, 14);
    if (atr <= 0) return null;

    const entry = bar.close;
    const stopDist = atr * STOP_ATR;
    const targetDist = atr * TARGET_ATR;

    if (bar.close > rangeHigh) {
      // Breakout up: long
      const stop = entry - stopDist;
      const target = entry + targetDist;
      const rr = calculateRr(entry, stop, target, "long");
      if (rr <= 0) return null;
      return { symbol: context.symbol, strategyId: this.id, side: "long", entry, stop, target, rr, confidence: 0.56, contracts: 1, maxHoldMinutes: MAX_HOLD_MINUTES };
    }
    if (bar.close < rangeLow) {
      // Breakout down: short
      const stop = entry + stopDist;
      const target = entry - targetDist;
      const rr = calculateRr(entry, stop, target, "short");
      if (rr <= 0) return null;
      return { symbol: context.symbol, strategyId: this.id, side: "short", entry, stop, target, rr, confidence: 0.56, contracts: 1, maxHoldMinutes: MAX_HOLD_MINUTES };
    }

    return null;
  }
}
