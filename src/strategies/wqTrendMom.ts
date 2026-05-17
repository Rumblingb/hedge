import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { inferBarIntervalMinutes } from "../utils/time.js";

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
    strategyId: "wq-trend-mom",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 60,
    meta: {
      lookbackBars: 20,
      barIntervalMinutes,
    },
  };
}

export class WqTrendMomStrategy implements Strategy {
  public readonly id = "wq-trend-mom";
  public readonly description = "WQ Trend Momentum strategy based on SMA5/SMA20 crossover and ATR-based stops/targets.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Need at least 20 history bars to compute SMA20 (plus current bar makes 21)
    if (context.history.length < 20) {
      return null;
    }

    const bars = [...context.history, context.bar];
    const i = bars.length - 1;

    // SMA5: average of last 5 closes (including current)
    const sma5 =
      bars.slice(i - 4, i + 1).reduce((sum, bar) => sum + bar.close, 0) / 5.0;
    // SMA20: average of last 20 closes (including current)
    const sma20 =
      bars.slice(i - 19, i + 1).reduce((sum, bar) => sum + bar.close, 0) / 20.0;

    // ATR using averageTrueRange over last 14 bars (excluding current)
    const atr = averageTrueRange(context.history, 14);
    if (atr <= 0) {
      return null;
    }

    const entry = context.bar.close;
    const trendUp = sma5 > sma20 && entry > sma20;
    const trendDown = sma5 < sma20 && entry < sma20;

    if (trendUp) {
      const stop = entry - atr * 1.5;
      const target = entry + atr * 2.0;
      const barIntervalMinutes = inferBarIntervalMinutes(
        context.history[context.history.length - 1]?.ts ?? 0,
        context.bar.ts
      );
      return buildSignal({
        context,
        side: "long",
        stop,
        target,
        confidence: 0.55,
        barIntervalMinutes,
      });
    }

    if (trendDown) {
      const stop = entry + atr * 1.5;
      const target = entry - atr * 2.0;
      const barIntervalMinutes = inferBarIntervalMinutes(
        context.history[context.history.length - 1]?.ts ?? 0,
        context.bar.ts
      );
      return buildSignal({
        context,
        side: "short",
        stop,
        target,
        confidence: 0.55,
        barIntervalMinutes,
      });
    }

    return null;
  }
}