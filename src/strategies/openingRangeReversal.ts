import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { minutesFromCtTime } from "../utils/time.js";

function wickToBodyRatio(open: number, high: number, low: number, close: number): { upper: number; lower: number } {
  const body = Math.max(Math.abs(close - open), 0.0001);
  const upper = (high - Math.max(open, close)) / body;
  const lower = (Math.min(open, close) - low) / body;
  return { upper, lower };
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);

  if (rr <= 0) {
    return null;
  }

  return {
    symbol: context.symbol,
    strategyId: "opening-range-reversal",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 20,
    meta: {
      sessionMinute: minutesFromCtTime(
        context.bar.ts,
        getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt).startCt
      )
    }
  };
}

export class OpeningRangeReversalStrategy implements Strategy {
  public readonly id = "opening-range-reversal";
  public readonly description = "Index-only opening auction sweep and reclaim strategy for the first hour.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) {
      return null;
    }

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 15 || sessionMinute > 60) {
      return null;
    }

    if (context.sessionHistory.length < 15) {
      return null;
    }

    const openingRange = context.sessionHistory.slice(0, 15);
    const openingHigh = Math.max(...openingRange.map((bar) => bar.high));
    const openingLow = Math.min(...openingRange.map((bar) => bar.low));
    const ratios = wickToBodyRatio(context.bar.open, context.bar.high, context.bar.low, context.bar.close);
    const targetRr = Math.max(context.config.guardrails.minRr, 2.8);
    const atr = averageTrueRange(context.sessionHistory, 14);

    if (context.bar.high > openingHigh && context.bar.close < openingHigh && ratios.upper >= 1.2) {
      const stop = atr > 0
        ? Math.min(context.bar.high, context.bar.close + atr)
        : context.bar.high;
      const risk = stop - context.bar.close;
      if (risk <= 0) {
        return null;
      }

      return buildSignal({
        context,
        side: "short",
        stop,
        target: context.bar.close - (risk * targetRr),
        confidence: 0.76
      });
    }

    if (context.bar.low < openingLow && context.bar.close > openingLow && ratios.lower >= 1.2) {
      const stop = atr > 0
        ? Math.max(context.bar.low, context.bar.close - atr)
        : context.bar.low;
      const risk = context.bar.close - stop;
      if (risk <= 0) {
        return null;
      }

      return buildSignal({
        context,
        side: "long",
        stop,
        target: context.bar.close + (risk * targetRr),
        confidence: 0.76
      });
    }

    return null;
  }
}
