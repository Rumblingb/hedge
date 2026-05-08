import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Scalping Strategy
 * 1-3 tick scalps on high-vol micro-moves. Ultra-short hold (1-5 min).
 * Targets small quick profits on momentum bursts.
 * Retail edge: no market impact, can enter/exit instantly on small size.
 */

function buildSignal(args: {
  context: StrategyContext; side: TradeSide; stop: number; target: number;
  confidence: number; momentum: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, momentum } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol, strategyId: "scalping", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 5,
    meta: { pattern: "micro-momentum-scalp", momentum: Number(momentum.toFixed(4)) },
  };
}

export class ScalpingStrategy implements Strategy {
  public readonly id = "scalping";
  public readonly description = "1-3 tick micro-scalps on momentum bursts. Ultra-short hold, high win-rate, small RR.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const history = context.history;
    if (history.length < 10) return null;

    const recent = history.slice(-10);
    const atr = averageTrueRange(recent, 5);
    if (atr <= 0) return null;

    const currentBar = context.bar;
    const prevBar = history[history.length - 1];

    // Calculate micro-momentum: 3-bar acceleration
    if (history.length < 4) return null;
    const bar1 = history[history.length - 3];
    const bar2 = history[history.length - 2];
    const bar3 = history[history.length - 1];

    const momentum = (bar3.close - bar1.close) / Math.max(bar1.close, 0.0001);
    const accel = Math.abs(bar3.close - bar2.close) - Math.abs(bar2.close - bar1.close);

    // Need acceleration AND volume spike
    const avgVol = recent.slice(0, -1).reduce((s, b) => s + b.volume, 0) / 9;
    const volSpike = currentBar.volume > avgVol * 1.5;

    if (!volSpike) return null;

    // Scalp long: positive momentum with acceleration, close near high
    const closeLoc = (currentBar.close - currentBar.low) / Math.max(currentBar.high - currentBar.low, 0.0001);
    if (momentum > 0.0005 && accel > 0 && closeLoc > 0.7) {
      const stop = currentBar.low - atr * 0.2;
      const target = currentBar.close + atr * 0.5; // Small target for scalp
      if (stop >= currentBar.close) return null;
      return buildSignal({ context, side: "long", stop, target, confidence: 0.58, momentum });
    }

    // Scalp short: negative momentum with acceleration, close near low
    if (momentum < -0.0005 && accel > 0 && closeLoc < 0.3) {
      const stop = currentBar.high + atr * 0.2;
      const target = currentBar.close - atr * 0.5;
      if (stop <= currentBar.close) return null;
      return buildSignal({ context, side: "short", stop, target, confidence: 0.58, momentum });
    }

    return null;
  }
}
