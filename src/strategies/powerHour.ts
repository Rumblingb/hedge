import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * Power Hour Strategy
 * Last hour of regular session: mean-reversion on extremes, momentum on breakouts.
 * 3:00-4:00 PM ET window. High volume, institutional repositioning.
 */

function buildSignal(args: {
  context: StrategyContext; side: TradeSide; stop: number; target: number;
  confidence: number; pattern: string;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, pattern } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol, strategyId: "power-hour", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 15,
    meta: { pattern, sessionMinute: minutesFromCtTime(context.bar.ts,
      getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt).startCt) },
  };
}

export class PowerHourStrategy implements Strategy {
  public readonly id = "power-hour";
  public readonly description = "Last hour mean-reversion and breakout momentum. High-vol close patterns on index futures.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 330 || sessionMinute > 390) return null; // Last 60 min

    const sourceHistory = context.sessionHistory.slice(-30);
    if (sourceHistory.length < 10) return null;

    const atr = averageTrueRange(sourceHistory, 14);
    if (atr <= 0) return null;

    const currentBar = context.bar;
    const currentRange = currentBar.high - currentBar.low;
    const closeLoc = (currentBar.close - currentBar.low) / Math.max(currentRange, 0.0001);

    // Breakout: range > 1.5x ATR, close at extreme
    if (currentRange > atr * 1.5) {
      if (closeLoc > 0.75) {
        const stop = currentBar.low - atr * 0.3;
        const target = currentBar.close + atr * 1.2;
        if (stop >= currentBar.close) return null;
        return buildSignal({ context, side: "long", stop, target, confidence: 0.64, pattern: "power-breakout-long" });
      }
      if (closeLoc < 0.25) {
        const stop = currentBar.high + atr * 0.3;
        const target = currentBar.close - atr * 1.2;
        if (stop <= currentBar.close) return null;
        return buildSignal({ context, side: "short", stop, target, confidence: 0.64, pattern: "power-breakout-short" });
      }
    }

    // Mean reversion: price stretched beyond 2 ATR from session VWAP
    const sessionCloses = sourceHistory.map((b) => b.close);
    const vwap = sessionCloses.reduce((a, b) => a + b, 0) / sessionCloses.length;
    const deviation = currentBar.close - vwap;

    if (Math.abs(deviation) > atr * 1.8) {
      if (deviation > 0) {
        const stop = currentBar.high + atr * 0.3;
        const target = vwap;
        if (stop <= currentBar.close) return null;
        return buildSignal({ context, side: "short", stop, target, confidence: 0.58, pattern: "power-reversion-short" });
      }
      if (deviation < 0) {
        const stop = currentBar.low - atr * 0.3;
        const target = vwap;
        if (stop >= currentBar.close) return null;
        return buildSignal({ context, side: "long", stop, target, confidence: 0.58, pattern: "power-reversion-long" });
      }
    }

    return null;
  }
}
