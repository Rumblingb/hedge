import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";

/**
 * Overnight Hold Strategy
 * Gap-and-go continuation: strong overnight gap → hold for continuation into regular session.
 * Works when gap is backed by volume and news catalyst.
 * Retail edge: small accounts can hold overnight without institutional constraints.
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
    symbol: context.symbol, strategyId: "overnight-hold", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 120,
    meta: { pattern: "gap-and-go", gapPct: Number(gapPct.toFixed(4)), barIntervalMinutes },
  };
}

export class OvernightHoldStrategy implements Strategy {
  public readonly id = "overnight-hold";
  public readonly description = "Gap-and-go continuation: hold overnight gaps with volume confirmation into regular session. Retail edge on small accounts.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;

    const lookback = Math.min(60, context.history.length);
    const recent = context.history.slice(-lookback);
    const atr = averageTrueRange(recent, 14);
    if (atr <= 0) return null;

    // Need previous day's close
    const sessionBars = context.sessionHistory;
    if (sessionBars.length < 3) return null;

    const prevDayClose = context.history[context.history.length - sessionBars.length - 1]?.close;
    if (!prevDayClose) return null;

    const currentPrice = context.bar.close;
    const gapPct = (currentPrice - prevDayClose) / prevDayClose;
    const minGap = 0.005; // 0.5% minimum gap for continuation

    // Volume confirmation
    const avgVol = recent.reduce((sum, b) => sum + b.volume, 0) / recent.length;
    const currentVol = context.bar.volume;
    const volConfirmation = currentVol > avgVol * 1.3;

    if (!volConfirmation) return null;

    // Gap up continuation
    if (gapPct > minGap && currentPrice > prevDayClose) {
      const stop = prevDayClose; // Gap fill = stop
      const target = currentPrice + atr * 3; // Wider target for overnight hold
      if (stop >= currentPrice) return null;
      return buildSignal({ context, side: "long", stop, target,
        confidence: Math.min(0.6, gapPct * 60), gapPct, barIntervalMinutes: 60 });
    }

    // Gap down continuation
    if (gapPct < -minGap && currentPrice < prevDayClose) {
      const stop = prevDayClose;
      const target = currentPrice - atr * 3;
      if (stop <= currentPrice) return null;
      return buildSignal({ context, side: "short", stop, target,
        confidence: Math.min(0.6, Math.abs(gapPct) * 60), gapPct, barIntervalMinutes: 60 });
    }

    return null;
  }
}
