import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * News Spike Fade Strategy
 * Fades the initial spike on high-impact news events.
 * First move = overreaction → fade it for mean-reversion.
 * Ultra-short hold (2-10 min). High win-rate, small RR.
 * Adapted from Chinese/Korean quant overnight gap fade applied to intraday news spikes.
 */

function buildSignal(args: {
  context: StrategyContext; side: TradeSide; stop: number; target: number;
  confidence: number; spikePct: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, spikePct } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol, strategyId: "news-spike-fade", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 10,
    meta: { pattern: "news-spike-fade", spikePct: Number(spikePct.toFixed(4)) },
  };
}

export class NewsSpikeFadeStrategy implements Strategy {
  public readonly id = "news-spike-fade";
  public readonly description = "Fades initial overreaction on news events. First move is usually wrong. Ultra-short hold, high win-rate.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const history = context.history;
    if (history.length < 20) return null;

    const recent = history.slice(-20);
    const atr = averageTrueRange(recent, 14);
    if (atr <= 0) return null;

    // Detect spike: 3+ ATR move in single bar
    const currentBar = context.bar;
    const prevBar = history[history.length - 1];
    const currentRange = currentBar.high - currentBar.low;
    const spikeRatio = currentRange / atr;

    if (spikeRatio < 3) return null;

    const prevVol = recent.slice(0, -1).reduce((s, b) => s + b.volume, 0) / 19;
    const volSpike = currentBar.volume > prevVol * 2;

    if (!volSpike) return null;

    // Fade the spike
    const barMove = currentBar.close - prevBar.close;
    const spikePct = barMove / prevBar.close;

    // Spike up fade: short
    if (spikePct > 0.003 && currentBar.close < currentBar.open * 1.001) {
      // Candle showing rejection (upper wick or close below open)
      const stop = currentBar.high + atr * 0.3;
      const target = prevBar.close + atr * 0.5; // Fade back toward pre-spike level
      if (stop <= currentBar.close) return null;
      return buildSignal({ context, side: "short", stop, target,
        confidence: 0.55, spikePct });
    }

    // Spike down fade: long
    if (spikePct < -0.003 && currentBar.close > currentBar.open * 0.999) {
      const stop = currentBar.low - atr * 0.3;
      const target = prevBar.close - atr * 0.5;
      if (stop >= currentBar.close) return null;
      return buildSignal({ context, side: "long", stop, target,
        confidence: 0.55, spikePct });
    }

    return null;
  }
}
