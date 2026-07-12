/**
 * Enhanced ORB with Volatility Filter
 *
 * Sources:
 *   - "Assessing the Profitability of Timely Opening Range Breakout on Index Futures Markets" (ResearchGate)
 *   - "Evolutionary ORB-based model with protective closing strategies" (Knowledge-Based Systems, 2021)
 *
 * Core concept: Opening Range Breakout with volatility filter.
 * Only trade ORB when the opening range is sufficiently wide (ATR-based) and volume confirms.
 *
 * Rules:
 *   - ORB = high / low of first 5 bars (5 min) of session
 *   - ORB width must be > 0.3 * ATR (wide enough to matter)
 *   - Buffer = 0.1 * ATR outside the ORB boundary
 *   - Breakout entry: price > ORB_high + buffer AND volume spike (vol > 1.5× ORB avg vol)
 *   - Breakdown entry: price < ORB_low  - buffer AND volume spike
 *   - Protective stop: placed at 50% retracement back into the ORB range
 *   - Targets: ES, NQ only
 *   - Only within first 60 min of session (after ORB period ends)
 */

import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketCategory } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { minutesFromCtTime } from "../utils/time.js";

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const ORB_BARS = 5;
const MIN_ORB_WIDTH_ATR_MULT = 0.3;
const BUFFER_ATR_MULT = 0.1;
const VOLUME_SPIKE_MULT = 1.5;
const MAX_SESSION_MINUTE = 60;
const PROTECTIVE_RETRACE = 0.5;

interface OrbRange {
  high: number;
  low: number;
  width: number;
  avgVolume: number;
}

function computeOrb(bars: Bar[]): OrbRange | null {
  if (bars.length < ORB_BARS) return null;

  const orbBars = bars.slice(0, ORB_BARS);
  const high = Math.max(...orbBars.map((b) => b.high));
  const low = Math.min(...orbBars.map((b) => b.low));
  const width = high - low;
  const totalVol = orbBars.reduce((sum, b) => sum + b.volume, 0);
  const avgVolume = totalVol / orbBars.length;

  return { high, low, width, avgVolume };
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  orbHigh: number;
  orbLow: number;
  orbWidth: number;
  atr: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, orbHigh, orbLow, orbWidth, atr } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);

  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: "enhanced-orb",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 20,
    meta: {
      orbHigh: Number(orbHigh.toFixed(4)),
      orbLow: Number(orbLow.toFixed(4)),
      orbWidth: Number(orbWidth.toFixed(4)),
      atr: Number(atr.toFixed(4)),
      protectiveRetrace: PROTECTIVE_RETRACE,
      sources: "ResearchGate + Knowledge-Based Systems 2021",
    },
  };
}

export class EnhancedOrbStrategy implements Strategy {
  public readonly id = "enhanced-orb";
  public readonly description =
    "Enhanced ORB with volatility filter. Only trades when ORB width > 0.3× ATR " +
    "and volume confirms the breakout. Protective stop at 50% retrace into range. " +
    "Targets ES/NQ within first 60 min. Sources: ResearchGate + KBS 2021.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Market gate: only ES and NQ
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) {
      return null;
    }

    // Category gate: must be index futures
    const category = getMarketCategory(context.symbol);
    if (category !== "index") {
      return null;
    }

    // Must have enough session bars to form ORB
    if (context.sessionHistory.length < ORB_BARS) {
      return null;
    }

    // Time gate: only within first 60 min of session, and after ORB period
    const sessionWindow = getMarketSessionWindow(
      context.symbol,
      context.config.guardrails.sessionStartCt,
    );
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);

    // Must be after ORB formation (bar 5+) and within first 60 min
    if (sessionMinute < ORB_BARS || sessionMinute > MAX_SESSION_MINUTE) {
      return null;
    }

    // Compute ORB from the first 5 bars of the session
    const orb = computeOrb(context.sessionHistory);
    if (!orb) return null;

    // Compute ATR using session history for volatility context
    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    // Volatility gate: ORB width must be wide enough to matter
    const minOrbWidth = MIN_ORB_WIDTH_ATR_MULT * atr;
    if (orb.width <= minOrbWidth) {
      return null;
    }

    // Volume gate: current bar must show a volume spike vs ORB average
    const currentVolume = context.bar.volume;
    if (currentVolume <= orb.avgVolume * VOLUME_SPIKE_MULT) {
      return null;
    }

    // Buffer outside ORB boundaries
    const buffer = BUFFER_ATR_MULT * atr;

    const targetRr = Math.max(
      context.config.guardrails.minRr,
      context.config.tuning.measuredMoveRr,
    );

    // === Bullish breakout ===
    if (context.bar.close > orb.high + buffer) {
      // Protective stop: 50% retracement back into the ORB range
      // i.e., orb.high + buffer - half the distance from entry to orb.high
      const entry = context.bar.close;
      const breakoutDistance = entry - orb.high;
      const stop = orb.high + breakoutDistance * (1 - PROTECTIVE_RETRACE);
      const risk = entry - stop;

      if (risk <= 0) return null;

      const target = entry + risk * targetRr;

      return buildSignal({
        context,
        side: "long",
        stop,
        target,
        confidence: 0.72,
        orbHigh: orb.high,
        orbLow: orb.low,
        orbWidth: orb.width,
        atr,
      });
    }

    // === Bearish breakdown ===
    if (context.bar.close < orb.low - buffer) {
      const entry = context.bar.close;
      const breakdownDistance = orb.low - entry;
      const stop = orb.low - breakdownDistance * (1 - PROTECTIVE_RETRACE);
      const risk = stop - entry;

      if (risk <= 0) return null;

      const target = entry - risk * targetRr;

      return buildSignal({
        context,
        side: "short",
        stop,
        target,
        confidence: 0.72,
        orbHigh: orb.high,
        orbLow: orb.low,
        orbWidth: orb.width,
        atr,
      });
    }

    return null;
  }
}
