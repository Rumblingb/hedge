import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Event-Driven Strategy
 * Trades predictable patterns around economic events.
 * FOMC, NFP, CPI: initial spike → fade OR momentum continuation depending on magnitude.
 * Uses simple statistical pattern recognition from historical event reactions.
 */

function buildSignal(args: {
  context: StrategyContext; side: TradeSide; stop: number; target: number;
  confidence: number; eventType: string; volSpike: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, eventType, volSpike } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol, strategyId: "event-driven", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 15,
    meta: { pattern: `event-${eventType}`, volSpike: Number(volSpike.toFixed(4)) },
  };
}

export class EventDrivenStrategy implements Strategy {
  public readonly id = "event-driven";
  public readonly description = "Trades predictable patterns around high-impact economic events: spike fade for moderate vol, momentum for extreme vol.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const history = context.history;
    if (history.length < 20) return null;

    const recent = history.slice(-20);
    const atr = averageTrueRange(recent, 14);
    if (atr <= 0) return null;

    const currentBar = context.bar;
    const currentRange = currentBar.high - currentBar.low;
    const normalRange = atr;

    // Event detection: bar range is 2.5x+ normal ATR = potential event
    const volSpike = currentRange / normalRange;
    if (volSpike < 2.5) return null;

    const closeLoc = (currentBar.close - currentBar.low) / currentRange;
    const bodySize = Math.abs(currentBar.close - currentBar.open);
    const isLargeBody = bodySize > currentRange * 0.6;

    // Pattern 1: Moderate vol spike (2.5-4x ATR) + large body = continuation momentum
    if (volSpike < 4 && isLargeBody) {
      if (closeLoc > 0.6) {
        const stop = currentBar.low - atr * 0.3;
        const target = currentBar.close + currentRange * 1.5;
        if (stop >= currentBar.close) return null;
        return buildSignal({ context, side: "long", stop, target,
          confidence: 0.62, eventType: "momentum-up", volSpike });
      }
      if (closeLoc < 0.4) {
        const stop = currentBar.high + atr * 0.3;
        const target = currentBar.close - currentRange * 1.5;
        if (stop <= currentBar.close) return null;
        return buildSignal({ context, side: "short", stop, target,
          confidence: 0.62, eventType: "momentum-down", volSpike });
      }
    }

    // Pattern 2: Extreme vol spike (4x+ ATR) = fade the spike (exhaustion)
    if (volSpike >= 4) {
      if (closeLoc < 0.5 && currentBar.close < currentBar.open) {
        // Selloff exhaustion: buy
        const stop = currentBar.low - atr * 0.5;
        const target = currentBar.close + currentRange * 0.8;
        if (stop >= currentBar.close) return null;
        return buildSignal({ context, side: "long", stop, target,
          confidence: 0.58, eventType: "exhaustion-up", volSpike });
      }
      if (closeLoc > 0.5 && currentBar.close > currentBar.open) {
        // Rally exhaustion: sell
        const stop = currentBar.high + atr * 0.5;
        const target = currentBar.close - currentRange * 0.8;
        if (stop <= currentBar.close) return null;
        return buildSignal({ context, side: "short", stop, target,
          confidence: 0.58, eventType: "exhaustion-down", volSpike });
      }
    }

    return null;
  }
}
