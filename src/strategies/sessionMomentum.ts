import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

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
      lookbackBars: context.config.tuning.momentumLookbackBars,
      barIntervalMinutes
    }
  };
}

export class SessionMomentumStrategy implements Strategy {
  public readonly id = "session-momentum";
  public readonly description = "Winner-inspired session breakout continuation with volume confirmation.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    const dailyLike = barIntervalMinutes >= 720;
    const sourceHistory = dailyLike ? context.history : context.sessionHistory;
    const configuredLookback = context.config.tuning.momentumLookbackBars;
    const lookback = dailyLike
      ? Math.max(3, Math.min(configuredLookback, 4))
      : configuredLookback;

    if (sourceHistory.length < lookback) {
      return null;
    }

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (!dailyLike && isIndexSymbol(context.symbol) && sessionMinute < 30) {
      return null;
    }

    const recent = sourceHistory.slice(-lookback);
    const recentHigh = Math.max(...recent.map((bar) => bar.high));
    const recentLow = Math.min(...recent.map((bar) => bar.low));
    const avgVolume = recent.reduce((sum, bar) => sum + bar.volume, 0) / recent.length;
    const volumeMultiplier = dailyLike
      ? Math.min(1.05, context.config.tuning.momentumVolumeMultiplier)
      : context.config.tuning.momentumVolumeMultiplier;
    const needsVolume = avgVolume * volumeMultiplier;
    const targetRr = dailyLike
      ? Math.max(2, Math.min(context.config.guardrails.minRr, context.config.tuning.measuredMoveRr - 0.4))
      : Math.max(context.config.guardrails.minRr, context.config.tuning.measuredMoveRr);
    const atr = averageTrueRange(sourceHistory, Math.min(14, Math.max(4, lookback + 2)));
    const barRange = context.bar.high - context.bar.low;
    if (atr > 0 && barRange > (atr * context.config.tuning.volatilityKillAtrMultiple)) {
      return null;
    }

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
        confidence: 0.73,
        barIntervalMinutes
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
        confidence: 0.71,
        barIntervalMinutes
      });
    }

    return null;
  }
}
