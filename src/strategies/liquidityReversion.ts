import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { isIndexSymbol } from "../utils/markets.js";
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
    strategyId: "liquidity-reversion",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 15,
    meta: {
      lookbackBars: context.config.tuning.reversionLookbackBars
    }
  };
}

export class LiquidityReversionStrategy implements Strategy {
  public readonly id = "liquidity-reversion";
  public readonly description = "Sweep-and-close-back-inside reversal proxy for short hold trades.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const lookback = context.config.tuning.reversionLookbackBars;
    if (!isIndexSymbol(context.symbol)) {
      return null;
    }

    const sessionMinute = minutesFromCtTime(context.bar.ts, context.config.guardrails.sessionStartCt);
    if (sessionMinute < 5 || sessionMinute > 45) {
      return null;
    }

    if (context.sessionHistory.length < lookback) {
      return null;
    }

    const recent = context.sessionHistory.slice(-lookback);
    const recentHigh = Math.max(...recent.map((bar) => bar.high));
    const recentLow = Math.min(...recent.map((bar) => bar.low));
    const ratios = wickToBodyRatio(context.bar.open, context.bar.high, context.bar.low, context.bar.close);
    const threshold = context.config.tuning.reversionWickToBody;
    const targetRr = Math.max(context.config.guardrails.minRr, 2.6);

    if (context.bar.high > recentHigh && context.bar.close < recentHigh && ratios.upper >= threshold) {
      const stop = context.bar.high;
      const risk = stop - context.bar.close;
      if (risk <= 0) {
        return null;
      }
      return buildSignal({
        context,
        side: "short",
        stop,
        target: context.bar.close - (risk * targetRr),
        confidence: 0.69
      });
    }

    if (context.bar.low < recentLow && context.bar.close > recentLow && ratios.lower >= threshold) {
      const stop = context.bar.low;
      const risk = context.bar.close - stop;
      if (risk <= 0) {
        return null;
      }
      return buildSignal({
        context,
        side: "long",
        stop,
        target: context.bar.close + (risk * targetRr),
        confidence: 0.68
      });
    }

    return null;
  }
}
