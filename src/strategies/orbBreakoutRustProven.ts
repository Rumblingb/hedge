/**
 * orbBreakoutRustProven.ts — ORB Breakout 15m research wrapper.
 *
 * Older full-sample parameter sweeps looked attractive, but this wrapper is
 * research-only until the current OOS, cost, Topstep data, and route gates
 * clear. It emits entries only; exits remain the backtest engine's job.
 */
import { type Strategy, type StrategyContext, type StrategySignal, type TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

const RW = 16;         // range window (15m bars)
const VT = 1.3;        // ATR multiplier for stop
const EO = 8;          // exit offset (bars)
const CONFIRM_BARS = 3;
const MIN_CONFIDENCE = 0.5;

export const orbBreakoutRustProven: Strategy = {
  id: "orb-breakout-15m-rust",
  description: `ORB breakout 15m research wrapper (rw=${RW}, vt=${VT}, eo=${EO}); not execution-promoted.`,

  generateSignal(ctx: StrategyContext): StrategySignal | null {
    const { symbol, bar, history, sessionHistory } = ctx;
    const bars = [...history, bar];
    const sessionBars = sessionHistory && sessionHistory.length > 0 ? sessionHistory : bars;
    
    if (sessionBars.length < RW + CONFIRM_BARS) return null;
    
    const atr = averageTrueRange(bars, 14);
    if (!atr || atr <= 0) return null;
    
    const orb = sessionBars.slice(0, RW);
    const rangeHigh = Math.max(...orb.map((b: { high: number }) => b.high));
    const rangeLow = Math.min(...orb.map((b: { low: number }) => b.low));
    const rangeSize = rangeHigh - rangeLow;
    if (rangeSize <= 0) return null;
    
    const confirmation = sessionBars.slice(-CONFIRM_BARS);
    const breakoutUp = confirmation.every((b) => b.close > rangeHigh);
    const breakoutDown = confirmation.every((b) => b.close < rangeLow);
    
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
    
    return {
      symbol, strategyId: "orb-breakout-15m-rust",
      side, entry: bar.close, stop, target, rr,
      confidence, contracts: 1, maxHoldMinutes: EO * 15,
      meta: {
        reason: `ORB ${side} breakout from [${rangeLow.toFixed(0)}-${rangeHigh.toFixed(0)}]`,
        rangeHigh: rangeHigh, rangeLow: rangeLow, rangeSize: rangeSize,
        atr: atr, breakoutPct: breakoutPct,
        params: `rw=${RW},vt=${VT},eo=${EO}`,
        source: "rust-param-sweep-research-only-2026-05-31",
        confirmationBars: CONFIRM_BARS,
        researchOnly: true,
      },
    };
  },
};

export default orbBreakoutRustProven;
