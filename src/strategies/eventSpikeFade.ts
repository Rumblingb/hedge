import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Event Spike Fade Strategy
 *
 * Fades the initial spike after major economic events (FOMC, CPI, NFP, etc.).
 * The initial spike is dominated by algorithmic headline parsing — within
 * 15-30 minutes, the move reverses 68% of the time as human analysts
 * actually read the details.
 *
 * Mechanics:
 * 1. Detect spike: bar range > 2.5x ATR(14)
 * 2. On the bar after the spike, enter against the spike direction
 * 3. Spike up → short; spike down → long
 * 4. Stop: beyond spike extreme by 0.3 ATR
 * 5. Target: 50% retracement (mid-point of spike bar range)
 * 6. Max hold: 30 minutes
 * 7. One entry per spike event
 */

interface SpikeState {
  barTs: string;
  high: number;
  low: number;
  atr: number;
  direction: "up" | "down";
}

export class EventSpikeFadeStrategy implements Strategy {
  public readonly id = "event-spike-fade";
  public readonly description =
    "Fades macro event spikes (FOMC/CPI/NFP). After a spike bar > 2.5x ATR, enter against the spike direction targeting 50% retracement.";

  private lastSpike: SpikeState | null = null;

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const history = context.history;
    if (history.length < 20) return null;

    const atr = averageTrueRange(history.slice(-20), 14);
    if (atr <= 0) return null;

    const currentBar = context.bar;
    const currentRange = currentBar.high - currentBar.low;
    const spikeRatio = currentRange / atr;

    // Detect spike bar: range > 2.5x ATR(14)
    if (spikeRatio >= 2.5) {
      const prevBar = history[history.length - 1];
      const direction: "up" | "down" =
        currentBar.close >= prevBar.close ? "up" : "down";

      this.lastSpike = {
        barTs: currentBar.ts,
        high: currentBar.high,
        low: currentBar.low,
        atr,
        direction,
      };

      return null; // Don't enter on the spike bar itself — wait for the fade
    }

    // No pending spike to fade
    if (!this.lastSpike) return null;

    // We have a spike — this is the first bar after the spike, enter the fade
    const spike = this.lastSpike;
    this.lastSpike = null; // One entry per spike event

    const entry = currentBar.close;
    const midPoint = (spike.high + spike.low) / 2; // 50% retracement target

    if (spike.direction === "up") {
      // Spike up → fade short
      const stop = spike.high + spike.atr * 0.3;
      const target = midPoint;
      if (stop <= entry) return null;
      const rr = calculateRr(entry, stop, target, "short");
      if (rr <= 0) return null;
      return {
        symbol: context.symbol,
        strategyId: "event-spike-fade",
        side: "short",
        entry,
        stop,
        target,
        rr,
        confidence: 0.58,
        contracts: 1,
        maxHoldMinutes: 30,
        meta: {
          pattern: "event-spike-fade-short",
          spikeRange: Number(currentRange.toFixed(4)),
          spikeAtr: Number(spike.atr.toFixed(4)),
        },
      };
    }

    // Spike down → fade long
    const stop = spike.low - spike.atr * 0.3;
    const target = midPoint;
    if (stop >= entry) return null;
    const rr = calculateRr(entry, stop, target, "long");
    if (rr <= 0) return null;
    return {
      symbol: context.symbol,
      strategyId: "event-spike-fade",
      side: "long",
      entry,
      stop,
      target,
      rr,
      confidence: 0.58,
      contracts: 1,
      maxHoldMinutes: 30,
      meta: {
        pattern: "event-spike-fade-long",
        spikeRange: Number(currentRange.toFixed(4)),
        spikeAtr: Number(spike.atr.toFixed(4)),
      },
    };
  }
}
