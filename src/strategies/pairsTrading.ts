import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { inferBarIntervalMinutes } from "../utils/time.js";

function rollingStats(series: number[], period: number): { mean: number; stdDev: number } | null {
  if (series.length < period) {
    return null;
  }
  const window = series.slice(-period);
  const n = window.length;
  const mean = window.reduce((sum, v) => sum + v, 0) / n;
  const variance = window.reduce((sum, v) => sum + (v - mean) ** 2, 0) / n;
  const stdDev = Math.sqrt(Math.max(variance, 1e-10));
  return { mean, stdDev };
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  zScore: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, zScore } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);

  if (rr <= 0) {
    return null;
  }

  return {
    symbol: context.symbol,
    strategyId: "pairs-trading",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 30,
    meta: {
      zScore: Number(zScore.toFixed(4)),
      pairsLookback: context.config.tuning.pairsLookbackBars,
      pairsZEntry: context.config.tuning.pairsZEntry,
      barIntervalMinutes
    }
  };
}

export class PairsTradingStrategy implements Strategy {
  public readonly id = "pairs-trading";
  public readonly description = "Z-score mean reversion on close vs rolling MA for single-symbol pairs proxy.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const lookback = context.config.tuning.pairsLookbackBars;
    const zEntry = context.config.tuning.pairsZEntry;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    const dailyLike = barIntervalMinutes >= 720;
    const sourceHistory = dailyLike ? context.history : context.sessionHistory;

    // Need enough bars: lookback for MA/std + some padding
    if (sourceHistory.length < lookback + 2) {
      return null;
    }

    // Build close series from history + current bar
    const closeSeries = [
      ...sourceHistory.slice(-(lookback + 2), -1).map((bar) => bar.close),
      context.bar.close
    ];

    const stats = rollingStats(closeSeries, lookback);
    if (!stats || stats.stdDev <= 0) {
      return null;
    }

    const zScore = (context.bar.close - stats.mean) / stats.stdDev;

    // Check if |z| exceeds entry threshold
    if (Math.abs(zScore) < zEntry) {
      return null;
    }

    const atr = averageTrueRange(sourceHistory, Math.min(14, lookback + 2));
    if (atr <= 0) {
      return null;
    }

    const barRange = context.bar.high - context.bar.low;
    if (barRange > atr * context.config.tuning.volatilityKillAtrMultiple) {
      return null;
    }

    // Target at the rolling MA (where z = 0)
    const targetRr = Math.max(context.config.guardrails.minRr, 2.4);

    if (zScore < -zEntry) {
      // Z is very negative => price well below MA => mean-revert long
      const stop = context.bar.close - atr * 1.0;
      const risk = context.bar.close - stop;
      if (risk <= 0) {
        return null;
      }
      return buildSignal({
        context,
        side: "long",
        stop,
        target: stats.mean, // target at the moving average
        confidence: 0.67,
        barIntervalMinutes,
        zScore
      });
    }

    if (zScore > zEntry) {
      // Z is very positive => price well above MA => mean-revert short
      const stop = context.bar.close + atr * 1.0;
      const risk = stop - context.bar.close;
      if (risk <= 0) {
        return null;
      }
      return buildSignal({
        context,
        side: "short",
        stop,
        target: stats.mean, // target at the moving average
        confidence: 0.65,
        barIntervalMinutes,
        zScore
      });
    }

    return null;
  }
}
