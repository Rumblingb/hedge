import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * Gap Fade Strategy
 * Fades overnight gaps based on mean-reversion tendency.
 * Korean/Japanese quant pattern: buy gap downs, sell gap ups.
 * Works best on index futures (ES, NQ) in range/consolidation regimes.
 */

function buildSignal(args: {
  context: StrategyContext; side: TradeSide; stop: number; target: number;
  confidence: number; gapPct: number; barIntervalMinutes: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, gapPct, barIntervalMinutes } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol, strategyId: "gap-fade", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 30,
    meta: { pattern: "overnight-gap-fade", gapPct: Number(gapPct.toFixed(4)), barIntervalMinutes },
  };
}

export class GapFadeStrategy implements Strategy {
  public readonly id = "gap-fade";
  public readonly description = "Fades overnight gaps: buy gap downs, sell gap ups. Mean-reversion based on Korean quant patterns.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes < 5 || barIntervalMinutes > 1440) return null;

    const lookback = Math.min(20, context.history.length);
    const recent = context.history.slice(-lookback);
    const atr = averageTrueRange(recent, 14);
    if (atr <= 0) return null;

    // Find session open (first bar after gap)
    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute > 120) return null; // Only fade in first 2 hours

    // Compare current bar to previous session close
    const prevClose = context.history[context.history.length - 2]?.close;
    if (!prevClose) return null;
    const gapPct = (context.bar.close - prevClose) / prevClose;
    const minGap = 0.003; // 0.3% minimum gap

    if (gapPct > minGap) {
      // Gap up: fade with short
      const stop = context.bar.high + atr * 0.5;
      const target = prevClose - atr * 0.25;
      return buildSignal({ context, side: "short", stop, target,
        confidence: Math.min(0.7, gapPct * 80), gapPct, barIntervalMinutes });
    }

    if (gapPct < -minGap) {
      // Gap down: fade with long
      const stop = context.bar.low - atr * 0.5;
      const target = prevClose + atr * 0.25;
      return buildSignal({ context, side: "long", stop, target,
        confidence: Math.min(0.7, Math.abs(gapPct) * 80), gapPct, barIntervalMinutes });
    }

    return null;
  }
}
