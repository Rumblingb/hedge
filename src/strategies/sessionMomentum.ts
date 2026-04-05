import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { minutesFromCtTime } from "../utils/time.js";

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
    strategyId: "session-momentum",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 20,
    meta: {
      lookbackBars: context.config.tuning.momentumLookbackBars
    }
  };
}

export class SessionMomentumStrategy implements Strategy {
  public readonly id = "session-momentum";
  public readonly description = "Winner-inspired session breakout continuation with volume confirmation.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const lookback = context.config.tuning.momentumLookbackBars;
    if (context.sessionHistory.length < lookback) {
      return null;
    }

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (isIndexSymbol(context.symbol) && sessionMinute < 30) {
      return null;
    }

    const recent = context.sessionHistory.slice(-lookback);
    const recentHigh = Math.max(...recent.map((bar) => bar.high));
    const recentLow = Math.min(...recent.map((bar) => bar.low));
    const avgVolume = recent.reduce((sum, bar) => sum + bar.volume, 0) / recent.length;
    const needsVolume = avgVolume * context.config.tuning.momentumVolumeMultiplier;
    const targetRr = Math.max(context.config.guardrails.minRr, context.config.tuning.measuredMoveRr);
    const atr = averageTrueRange(context.sessionHistory, 14);

    if (context.bar.close > recentHigh && context.bar.volume >= needsVolume) {
      const stop = atr > 0
        ? Math.max(recentLow, context.bar.close - (atr * 1.25))
        : recentLow;
      const risk = context.bar.close - stop;
      if (risk <= 0) {
        return null;
      }
      return buildSignal({
        context,
        side: "long",
        stop,
        target: context.bar.close + (risk * targetRr),
        confidence: 0.73
      });
    }

    if (context.bar.close < recentLow && context.bar.volume >= needsVolume) {
      const stop = atr > 0
        ? Math.min(recentHigh, context.bar.close + (atr * 1.25))
        : recentHigh;
      const risk = stop - context.bar.close;
      if (risk <= 0) {
        return null;
      }
      return buildSignal({
        context,
        side: "short",
        stop,
        target: context.bar.close - (risk * targetRr),
        confidence: 0.71
      });
    }

    return null;
  }
}
