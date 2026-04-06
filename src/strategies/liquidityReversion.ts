import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

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
      lookbackBars: context.config.tuning.reversionLookbackBars,
      barIntervalMinutes
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

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    const dailyLike = barIntervalMinutes >= 720;
    const sourceHistory = dailyLike ? context.history : context.sessionHistory;

    const sessionMinute = minutesFromCtTime(context.bar.ts, context.config.guardrails.sessionStartCt);
    if (!dailyLike && (sessionMinute < 5 || sessionMinute > 45)) {
      return null;
    }

    const effectiveLookback = dailyLike
      ? Math.max(4, Math.min(lookback, 6))
      : lookback;

    if (sourceHistory.length < effectiveLookback) {
      return null;
    }

    const recent = sourceHistory.slice(-effectiveLookback);
    const recentHigh = Math.max(...recent.map((bar) => bar.high));
    const recentLow = Math.min(...recent.map((bar) => bar.low));
    const ratios = wickToBodyRatio(context.bar.open, context.bar.high, context.bar.low, context.bar.close);
    const threshold = context.config.tuning.reversionWickToBody;
    const targetRr = dailyLike
      ? Math.max(2, context.config.guardrails.minRr)
      : Math.max(context.config.guardrails.minRr, 2.6);
    const atr = averageTrueRange(sourceHistory, Math.min(14, Math.max(5, effectiveLookback + 2)));
    const barRange = context.bar.high - context.bar.low;
    if (atr > 0 && barRange > (atr * context.config.tuning.volatilityKillAtrMultiple)) {
      return null;
    }

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
        confidence: 0.69,
        barIntervalMinutes
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
        confidence: 0.68,
        barIntervalMinutes
      });
    }

    return null;
  }
}
