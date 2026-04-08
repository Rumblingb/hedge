import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketCategory } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

function averageBodySize(history: Bar[], period: number): number {
  if (history.length === 0) {
    return 0;
  }

  const tail = history.slice(-period);
  const total = tail.reduce((sum, bar) => sum + Math.abs(bar.close - bar.open), 0);
  return total / tail.length;
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  liquidityPoolLevel: number;
  fairValueGapBoundary: number;
}): StrategySignal | null {
  const {
    context,
    side,
    stop,
    target,
    confidence,
    barIntervalMinutes,
    liquidityPoolLevel,
    fairValueGapBoundary
  } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);

  if (rr <= 0) {
    return null;
  }

  return {
    symbol: context.symbol,
    strategyId: "ict-displacement",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 20,
    meta: {
      pattern: "liquidity-sweep-displacement-fvg",
      liquidityPoolLevel: Number(liquidityPoolLevel.toFixed(4)),
      fairValueGapBoundary: Number(fairValueGapBoundary.toFixed(4)),
      barIntervalMinutes
    }
  };
}

export class IctDisplacementStrategy implements Strategy {
  public readonly id = "ict-displacement";
  public readonly description = "ICT-style liquidity sweep, displacement, and fair value gap continuation for liquid session markets.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const category = getMarketCategory(context.symbol);
    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    const dailyLike = barIntervalMinutes >= 720;

    if (!dailyLike && category !== "index" && category !== "fx") {
      return null;
    }

    const sourceHistory = dailyLike ? context.history : context.sessionHistory;
    const lookback = Math.max(6, context.config.tuning.reversionLookbackBars + 2);
    if (sourceHistory.length < lookback) {
      return null;
    }

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (!dailyLike) {
      const maxSessionMinute = category === "index" ? 120 : 150;
      if (sessionMinute < 5 || sessionMinute > maxSessionMinute) {
        return null;
      }
    }

    const first = sourceHistory[sourceHistory.length - 2];
    const second = sourceHistory[sourceHistory.length - 1];
    if (!first || !second) {
      return null;
    }

    const liquidityHistory = sourceHistory.slice(-(lookback + 2), -2);
    if (liquidityHistory.length < Math.max(4, lookback - 2)) {
      return null;
    }

    const liquidityHigh = Math.max(...liquidityHistory.map((bar) => bar.high));
    const liquidityLow = Math.min(...liquidityHistory.map((bar) => bar.low));
    const atr = averageTrueRange([...sourceHistory, context.bar], Math.min(14, lookback + 3));
    const avgBody = averageBodySize(sourceHistory, Math.min(lookback, 8));
    const currentBody = Math.abs(context.bar.close - context.bar.open);
    const barRange = context.bar.high - context.bar.low;
    const displacementThreshold = Math.max(0.0001, atr * 0.55, avgBody * 1.35);
    if (atr > 0 && barRange > (atr * context.config.tuning.volatilityKillAtrMultiple)) {
      return null;
    }

    const targetRr = Math.max(context.config.guardrails.minRr, context.config.tuning.measuredMoveRr);
    const bullishSweep = Math.min(second.low, context.bar.low) < liquidityLow;
    const bearishSweep = Math.max(second.high, context.bar.high) > liquidityHigh;
    const bullishDisplacement = context.bar.close > context.bar.open && currentBody >= displacementThreshold;
    const bearishDisplacement = context.bar.close < context.bar.open && currentBody >= displacementThreshold;
    const bullishFairValueGap = context.bar.low > first.high;
    const bearishFairValueGap = context.bar.high < first.low;
    const bullishStructureShift = context.bar.close > second.high;
    const bearishStructureShift = context.bar.close < second.low;

    if (bullishSweep && bullishDisplacement && bullishFairValueGap && bullishStructureShift) {
      const stop = Math.min(first.low, second.low, context.bar.low);
      const risk = context.bar.close - stop;
      if (risk <= 0) {
        return null;
      }

      return buildSignal({
        context,
        side: "long",
        stop,
        target: context.bar.close + (risk * targetRr),
        confidence: 0.81,
        barIntervalMinutes,
        liquidityPoolLevel: liquidityLow,
        fairValueGapBoundary: first.high
      });
    }

    if (bearishSweep && bearishDisplacement && bearishFairValueGap && bearishStructureShift) {
      const stop = Math.max(first.high, second.high, context.bar.high);
      const risk = stop - context.bar.close;
      if (risk <= 0) {
        return null;
      }

      return buildSignal({
        context,
        side: "short",
        stop,
        target: context.bar.close - (risk * targetRr),
        confidence: 0.81,
        barIntervalMinutes,
        liquidityPoolLevel: liquidityHigh,
        fairValueGapBoundary: first.low
      });
    }

    return null;
  }
}
