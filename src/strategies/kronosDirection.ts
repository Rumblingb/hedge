import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Kronos Direction Strategy
 *
 * Wires Kronos 24h forecasts to directional trading signals. Kronos produces
 * a scalar direction (-1 bearish to +1 bullish) and confidence (0–1) per symbol.
 * This strategy fires a single signal per day when direction conviction exceeds
 * the threshold and Kronos confidence is high enough.
 *
 * - kronosDirection > 0.3 → long  (confidence 0.45 + |dir|×0.2)
 * - kronosDirection < -0.3 → short (confidence 0.45 + |dir|×0.2)
 * - Target: entry + (side × 2.0 × ATR14)
 * - Stop:   entry − (side × 1.0 × ATR14)
 * - 1 contract, 60-min max hold, one signal per day
 * - ES and NQ only
 *
 * Requires kronosConfidence > 0.4 and dailyTradeCount === 0.
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const DIRECTION_THRESHOLD = 0.02;
const CONFIDENCE_BASE = 0.40;
const CONFIDENCE_SLOPE = 0.15;
const MIN_KRONOS_CONFIDENCE = 0.35;

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
  if (rr <= 0) return null;
  return {
    symbol: context.symbol,
    strategyId: "kronos-direction",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 60,
    meta: {
      pattern: "kronos-forecast",
      kronosDirection: Math.round(context.macro!.kronosDirection! * 1000) / 1000,
      kronosConfidence: Math.round(context.macro!.kronosConfidence! * 1000) / 1000,
    },
  };
}

export class KronosDirectionStrategy implements Strategy {
  public readonly id = "kronos-direction";
  public readonly description =
    "Kronos Direction: directional signals from Kronos 24h forecasts. Long above +0.3, short below -0.3. ES/NQ only, one signal per day.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Only ES and NQ
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    // One signal per day
    if (context.dailyTradeCount > 0) return null;

    // Require Kronos macro data
    const dir = context.macro?.kronosDirection;
    const conf = context.macro?.kronosConfidence;
    if (dir === undefined || conf === undefined) return null;

    // Kronos confidence must exceed threshold
    if (conf <= MIN_KRONOS_CONFIDENCE) return null;

    // Determine side from direction
    const absDir = Math.abs(dir);
    let side: TradeSide;
    if (dir > DIRECTION_THRESHOLD) {
      side = "long";
    } else if (dir < -DIRECTION_THRESHOLD) {
      side = "short";
    } else {
      return null; // neutral zone
    }

    // Compute confidence: 0.45 + |dir| × 0.2, capped at 0.65 for |dir|=1.0
    const signalConfidence = CONFIDENCE_BASE + absDir * CONFIDENCE_SLOPE;

    // ATR for stop/target sizing
    const atr = averageTrueRange([...context.history.slice(-20), context.bar], 14);
    if (atr <= 0) return null;

    // Target = entry + (side × 2.0 × ATR), Stop = entry − (side × 1.0 × ATR)
    // long: sideNum=+1 → target above, stop below
    // short: sideNum=−1 → target below, stop above
    const sideNum = side === "long" ? 1 : -1;
    const target = context.bar.close + sideNum * 2.0 * atr;
    const stop = context.bar.close - sideNum * 1.0 * atr;

    return buildSignal({ context, side, stop, target, confidence: signalConfidence });
  }
}
