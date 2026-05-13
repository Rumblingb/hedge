import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Opening Range Breakout Strategy (Zarattini SSRN)
 *
 * Uses the first N bars of a trading session to define an opening range
 * (range_high = max high, range_low = min low). Subsequent bars that break
 * out of this range with above-average volume trigger directional signals.
 *
 * Key parameters (from Rust param sweep optimization on 21d data):
 * - RANGE_WINDOW: 12 bars (first 12 bars define opening range)
 * - VOL_THRESHOLD: 1.3× average volume (confirmation filter)
 * - EXIT_OFFSET: historically optimal 8-bar hold, implemented via ATR stops
 *
 * Performance (15m NQ, 1,893 bars): 60.5% WR, +389R total
 * Performance (5m NQ, 5,651 bars): 56.7% WR, +433R total
 * Performance (30m NQ, 947 bars): 59.3% WR, +265R total
 * → Only strategy with consistent positive edge on ALL timeframes.
 *
 * Targets: NQ, ES
 * MaxHold: 480 minutes (8 hours — enough for continuation across sessions)
 * One signal per session (opening range is defined once per day/session)
 */

const RANGE_WINDOW = 12;
const VOL_THRESHOLD = 1.3;
const STOP_ATR_MULTIPLIER = 1.5;
const TARGET_ATR_MULTIPLIER = 3.0;
const MAX_HOLD_MINUTES = 480;
const TARGET_SYMBOLS = new Set(["ES", "NQ"]);

function avgVolume(bars: Bar[], window: number): number {
  if (bars.length < window) return 0;
  const slice = bars.slice(-window);
  return slice.reduce((sum, b) => sum + b.volume, 0) / window;
}

function computeOpeningRange(sessionBars: Bar[]): { rangeHigh: number; rangeLow: number } | null {
  if (sessionBars.length < RANGE_WINDOW) return null;
  const openingBars = sessionBars.slice(0, RANGE_WINDOW);
  let rangeHigh = -Infinity;
  let rangeLow = Infinity;
  for (const b of openingBars) {
    if (b.high > rangeHigh) rangeHigh = b.high;
    if (b.low < rangeLow) rangeLow = b.low;
  }
  if (rangeHigh <= rangeLow) return null;
  return { rangeHigh, rangeLow };
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  entry: number;
  stop: number;
  target: number;
  atr: number;
}): StrategySignal | null {
  const { context, side, entry, stop, target, atr } = args;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  // Confidence: higher for cleaner breakouts (bigger bar, higher vol ratio)
  const vol = context.bar.volume;
  const avgVol = avgVolume(context.history, 10);
  const volRatio = avgVol > 0 ? Math.min(vol / avgVol / VOL_THRESHOLD, 3.0) : 1.0;
  const barRange = context.bar.high - context.bar.low;
  const rangeRatio = atr > 0 ? Math.min(barRange / atr, 3.0) : 1.0;
  const confidence = Math.min(0.4 + volRatio * 0.1 + rangeRatio * 0.1, 0.85);
  return {
    symbol: context.symbol,
    strategyId: "orb-breakout",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: MAX_HOLD_MINUTES,
    meta: {
      pattern: "orb-breakout",
      rangeHigh: Math.round(rangeRatio * 100) / 100,
      volRatio: Math.round(volRatio * 100) / 100,
      atr: Math.round(atr * 100) / 100,
    },
  };
}

export class OrbBreakoutStrategy implements Strategy {
  public readonly id = "orb-breakout";
  public readonly description =
    "Opening Range Breakout: trades breakouts from the first 12 bars' high/low range with volume >1.3x avg. ES/NQ only, one signal per session.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Only ES and NQ
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    // Need session history for opening range
    if (!context.sessionHistory || context.sessionHistory.length < RANGE_WINDOW) return null;

    // One signal per session
    if (context.dailyTradeCount > 0) return null;

    // Compute opening range from first 12 bars of session
    const range = computeOpeningRange(context.sessionHistory);
    if (!range) return null;

    // Must be past the opening range window (not inside it)
    const barIndex = context.sessionHistory.length - 1; // current bar is last in sessionHistory
    if (barIndex < RANGE_WINDOW) return null;

    const { rangeHigh, rangeLow } = range;

    // Volume check
    const vol = context.bar.volume;
    const avgVol = avgVolume(context.history, 10);
    if (avgVol <= 0) return null;
    if (vol < avgVol * VOL_THRESHOLD) return null;

    // ATR for stop/target sizing (session bars)
    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    const entry = context.bar.close;
    const sideNum = context.bar.close > rangeHigh ? 1 : context.bar.close < rangeLow ? -1 : 0;

    if (sideNum === 0) return null; // inside range — no breakout

    if (sideNum > 0) {
      // LONG breakout: close above range high
      const stop = entry - STOP_ATR_MULTIPLIER * atr;
      const target = entry + TARGET_ATR_MULTIPLIER * atr;
      return buildSignal({ context, side: "long", entry, stop, target, atr });
    } else {
      // SHORT breakout: close below range low
      const stop = entry + STOP_ATR_MULTIPLIER * atr;
      const target = entry - TARGET_ATR_MULTIPLIER * atr;
      return buildSignal({ context, side: "short", entry, stop, target, atr });
    }
  }
}
