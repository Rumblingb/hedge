import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { inferBarIntervalMinutes } from "../utils/time.js";

const EXIT_OFFSET = 8;
const STOP_ATR = 1.5;
const TARGET_ATR = 3.0;
const MAX_HOLD = 480;
const TARGET_SYMBOLS = new Set(["ES", "NQ"]);

function getPrevDayHighLow(bars: Array<{ ts: string; high: number; low: number }>, currentIdx: number): { high: number; low: number } | null {
  if (currentIdx < 1) return null;
  const currentTs = new Date(bars[currentIdx].ts);
  // Walk backwards to find the previous trading day
  for (let i = currentIdx - 1; i >= 0; i--) {
    const barTs = new Date(bars[i].ts);
    if (barTs.getUTCDate() !== currentTs.getUTCDate() ||
        barTs.getUTCMonth() !== currentTs.getUTCMonth() ||
        barTs.getUTCFullYear() !== currentTs.getUTCFullYear()) {
      // Found previous day range
      let high = bars[i].high;
      let low = bars[i].low;
      for (let j = i; j >= 0; j--) {
        const jTs = new Date(bars[j].ts);
        if (jTs.getUTCDate() === barTs.getUTCDate() &&
            jTs.getUTCMonth() === barTs.getUTCMonth() &&
            jTs.getUTCFullYear() === barTs.getUTCFullYear()) {
          high = Math.max(high, bars[j].high);
          low = Math.min(low, bars[j].low);
        } else {
          break;
        }
      }
      return { high, low };
    }
  }
  return null;
}

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
  if (rr <= 0) return null;
  return {
    symbol: context.symbol,
    strategyId: "daily-range-breakout",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: MAX_HOLD,
    meta: { exitOffset: EXIT_OFFSET, barIntervalMinutes }
  };
}

export class DailyRangeBreakoutStrategy implements Strategy {
  public readonly id = "daily-range-breakout";
  public readonly description = "Breakout of previous day's high or low with continuation.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;

    const barIntervalMinutes = inferBarIntervalMinutes(
      context.history[context.history.length - 1]?.ts,
      context.bar.ts
    );

    const allBars = [...context.history, context.bar];
    const currentIdx = allBars.length - 1;
    if (currentIdx < 20) return null;

    const prevDay = getPrevDayHighLow(allBars, currentIdx);
    if (!prevDay) return null;

    const bar = context.bar;
    const atr = averageTrueRange(allBars.slice(0, currentIdx), 14);
    if (atr <= 0) return null;

    // Volume check
    const recentVol = allBars.slice(-20).reduce((s, b) => s + b.volume, 0) / 20;
    const volOk = recentVol <= 0 || bar.volume >= recentVol * 1.0; // vol_mult=1.0 (no filter)

    if (bar.close > prevDay.high && volOk) {
      return buildSignal({
        context, side: "long",
        stop: bar.close - atr * STOP_ATR,
        target: bar.close + atr * TARGET_ATR,
        confidence: 0.58, barIntervalMinutes
      });
    } else if (bar.close < prevDay.low && volOk) {
      return buildSignal({
        context, side: "short",
        stop: bar.close + atr * STOP_ATR,
        target: bar.close - atr * TARGET_ATR,
        confidence: 0.58, barIntervalMinutes
      });
    }
    return null;
  }
}
