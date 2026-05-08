import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * Market Open Drive Strategy
 * Trades the directional bias established in the first 5 minutes of regular session.
 * If first 5-min bar is strongly directional, follow it for continuation.
 * Simple but effective on index futures.
 */

function buildSignal(args: {
  context: StrategyContext; side: TradeSide; stop: number; target: number;
  confidence: number; openDrivePct: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, openDrivePct } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol, strategyId: "market-open-drive", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 30,
    meta: { pattern: "open-drive-continuation", openDrivePct: Number(openDrivePct.toFixed(4)) },
  };
}

export class MarketOpenDriveStrategy implements Strategy {
  public readonly id = "market-open-drive";
  public readonly description = "Follows first 5-min directional bias at market open. Continuation pattern on index futures.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 5 || sessionMinute > 30) return null; // Only in first 30 min

    const sessionBars = context.sessionHistory;
    if (sessionBars.length < 2) return null;

    // First bar determines direction
    const firstBar = sessionBars[0];
    const firstBarRange = firstBar.high - firstBar.low;
    const firstBarBody = Math.abs(firstBar.close - firstBar.open);
    const firstBarDirection = firstBar.close > firstBar.open ? "up" : "down";
    const driveStrength = firstBarBody / Math.max(firstBarRange, 0.0001);

    // Need strong directional conviction (>70% body/range)
    if (driveStrength < 0.7) return null;

    const recent = sessionBars.slice(-5).length >= 3 ? sessionBars.slice(-5) : sessionBars;
    const atr = averageTrueRange([...context.history.slice(-20), context.bar], 14);
    if (atr <= 0) return null;

    const currentPrice = context.bar.close;

    if (firstBarDirection === "up" && currentPrice > firstBar.high) {
      const stop = firstBar.low;
      const target = currentPrice + atr * 1.5;
      if (stop >= currentPrice) return null;
      return buildSignal({ context, side: "long", stop, target,
        confidence: Math.min(0.66, driveStrength), openDrivePct: driveStrength });
    }

    if (firstBarDirection === "down" && currentPrice < firstBar.low) {
      const stop = firstBar.high;
      const target = currentPrice - atr * 1.5;
      if (stop <= currentPrice) return null;
      return buildSignal({ context, side: "short", stop, target,
        confidence: Math.min(0.66, driveStrength), openDrivePct: driveStrength });
    }

    return null;
  }
}
