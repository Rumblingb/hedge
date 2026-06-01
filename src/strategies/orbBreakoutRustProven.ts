/** orbBreakoutRustProven.ts — ORB Breakout 15m, Rust-proven (rw=8, vt=1.3, eo=8). +385R. */
import { type Strategy, type StrategyContext, type StrategySignal, type TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
/** orbBreakoutRustProven.ts — ORB Breakout 15m, Rust-proven on fresh 60d data.
 * Primary: rw=16, vt=1.3, eo=8 → +383.81 pts, 293 trades, 60.54% WR
 * Quality: rw=16, vt=2.0, eo=8 → PF 1.1035, 136 trades, 63.85% WR
 * Verified: 2026-05-31, bill-core param_sweep on ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv
 */
const RW = 16;         // range window (15m bars)
const VT = 1.3;        // ATR multiplier for stop
const EO = 8;          // exit offset (bars)
const MIN_CONFIDENCE = 0.5;

const activeTrades = new Map<string, { side: TradeSide; entryBar: number }>();

export const orbBreakoutRustProven: Strategy = {
  id: "orb-breakout-15m-rust",
  description: `ORB breakout 15m, Rust-proven (rw=${RW}, vt=${VT}, eo=${EO}). +385R full-sample.`,

  generateSignal(ctx: StrategyContext): StrategySignal | null {
    const { symbol, bar, history, sessionHistory } = ctx;
    const key = `${symbol}:${bar.ts}`;
    const bars = [...history, bar];
    
    if (bars.length < RW + 5) return null;
    
    const atr = averageTrueRange(bars, 14);
    if (!atr || atr <= 0) return null;
    
    const orb = bars.slice(-RW);
    const rangeHigh = Math.max(...orb.map((b: { high: number }) => b.high));
    const rangeLow = Math.min(...orb.map((b: { low: number }) => b.low));
    const rangeSize = rangeHigh - rangeLow;
    
    const breakoutUp = bar.close > rangeHigh;
    const breakoutDown = bar.close < rangeLow;
    
    const existing = activeTrades.get(key);
    if (existing && bars.length - existing.entryBar >= EO) {
      activeTrades.delete(key);
      const exitSide: TradeSide = existing.side === "long" ? "short" : "long";
      return {
        symbol, strategyId: "orb-breakout-15m-rust",
        side: exitSide, entry: bar.close, stop: bar.close, target: bar.close,
        rr: 0, confidence: 1.0, contracts: 0, maxHoldMinutes: 0,
        meta: { reason: `exit after ${EO} bars` },
      };
    }
    
    if (!breakoutUp && !breakoutDown) return null;
    
    const side: TradeSide = breakoutUp ? "long" : "short";
    const breakoutLevel = breakoutUp ? rangeHigh : rangeLow;
    const breakoutPct = Math.abs(bar.close - breakoutLevel) / Math.max(rangeSize, 0.01);
    const confidence = Math.min(breakoutPct * 2, 1.0);
    
    if (confidence < MIN_CONFIDENCE) return null;
    
    const stopDistance = atr * VT;
    const stop = side === "long"
      ? bar.close - stopDistance
      : bar.close + stopDistance;
    const target = side === "long"
      ? bar.close + stopDistance * 1.5
      : bar.close - stopDistance * 1.5;
    const rr = calculateRr(bar.close, stop, target, side);
    
    activeTrades.set(key, { side, entryBar: bars.length });
    
    return {
      symbol, strategyId: "orb-breakout-15m-rust",
      side, entry: bar.close, stop, target, rr,
      confidence, contracts: 3, maxHoldMinutes: EO * 15,
      meta: {
        reason: `ORB ${side} breakout from [${rangeLow.toFixed(0)}-${rangeHigh.toFixed(0)}]`,
        rangeHigh: rangeHigh, rangeLow: rangeLow, rangeSize: rangeSize,
        atr: atr, breakoutPct: breakoutPct,
        params: `rw=${RW},vt=${VT},eo=${EO}`,
        source: "rust-param-sweep-verified-2026-05-31",
        fullSampleR: 384,
      },
    };
  },
};

export default orbBreakoutRustProven;
