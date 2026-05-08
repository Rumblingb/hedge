import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Short-Term Reversal Strategy
 *
 * Based on: Hanauer, M.X. (2023). "Beyond Fama-French Factors: Alpha from
 * Short-Term Signals." Financial Analysts Journal.
 *
 * Core insight: assets with extreme short-term returns (1-5 day/bar horizon)
 * tend to reverse. This is one of 5 short-term alpha signals shown to generate
 * significant net alpha out-of-sample and post-publication, across regions,
 * on a liquid global universe.
 *
 * Implementation for 1-min futures:
 * - Compute return over lookback (default 60 bars = 1 hour on 1-min)
 * - If return < -1.5×ATR: oversold → long reversal
 * - If return > +1.5×ATR: overbought → short reversal
 * - Volume confirmation: volume must be > 1.5× average volume
 * - Confidence: scales with return magnitude relative to ATR
 * - Target: 50% mean-reversion (halfway back to VWAP of lookback)
 * - Stop: 1.0×ATR beyond extreme
 *
 * Symbols: ES, NQ, CL, GC (liquid futures)
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ", "CL", "GC"]);
const STRATEGY_ID = "short-term-reversal";
const PATTERN = "short-term-reversal-hanauer";

// Reversal thresholds
const REVERSAL_ATR_MULTIPLE = 1.5;   // Return must exceed 1.5×ATR for reversal signal
const VOLUME_MULTIPLIER = 1.5;         // Volume confirmation multiplier
const LOOKBACK_BARS = 60;              // 60 bars ≈ 1 hour on 1-min data

// Confidence range
const BASE_CONFIDENCE = 0.50;
const MAX_CONFIDENCE = 0.65;

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  lookbackReturn: number;
  atr: number;
  avgVolume: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, lookbackReturn, atr, avgVolume } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: STRATEGY_ID,
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 60,
    meta: {
      pattern: PATTERN,
      lookbackReturn: Math.round(lookbackReturn * 10000) / 100, // basis points
      atr: Math.round(atr * 100) / 100,
      avgVolume: Math.round(avgVolume),
      source: "hanauer-2023-faj",
    },
  };
}

export class ShortTermReversalStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Short-term reversal based on Hanauer (2023) FAJ — extreme returns over 60-bar lookback " +
    "reverse toward VWAP. Volume-confirmed. ES, NQ, CL, GC.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // ── Symbol gate ───────────────────────────────────────────────────
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    const { bar, history } = context;

    // ── Need enough history for lookback ──────────────────────────────
    if (history.length < LOOKBACK_BARS + 2) return null;

    // ── Filter: skip if we already have a trade today ──────────────────
    if (context.dailyTradeCount > 0) return null;

    // ── Compute lookback return ────────────────────────────────────────
    const lookbackStart = history[history.length - LOOKBACK_BARS - 1]!;
    const lookbackEnd = bar;
    const lookbackReturn = lookbackEnd.close - lookbackStart.close;

    // ── ATR (14-bar) ──────────────────────────────────────────────────
    const atr = averageTrueRange(history, 14);
    if (atr <= 0) return null;

    // ── Trigger: return must exceed REVERSAL_ATR_MULTIPLE × ATR ─────────
    const absReturn = Math.abs(lookbackReturn);
    if (absReturn < REVERSAL_ATR_MULTIPLE * atr) return null;

    // ── Volume confirmation: current bar volume vs lookback average ────
    let avgVolume = 0;
    const volSlice = history.slice(-LOOKBACK_BARS);
    for (const b of volSlice) avgVolume += b.volume;
    avgVolume /= volSlice.length;
    if (bar.volume < VOLUME_MULTIPLIER * avgVolume) return null;

    // ── Direction: fade the extreme move ──────────────────────────────
    // Big drop → oversold → long. Big rally → overbought → short.
    const side: TradeSide = lookbackReturn < 0 ? "long" : "short";

    // ── Compute lookback VWAP as target ────────────────────────────────
    let sumCv = 0;
    let sumV = 0;
    for (const b of volSlice) {
      sumCv += b.close * b.volume;
      sumV += b.volume;
    }
    const lookbackVwap = sumV > 0 ? sumCv / sumV : lookbackEnd.close;

    let stop: number;
    let target: number;

    if (side === "long") {
      // Stop: 1.0×ATR below the lowest point of the move
      let moveLow = bar.low;
      for (let i = history.length - 1; i >= history.length - LOOKBACK_BARS; i--) {
        if (history[i]!.low < moveLow) moveLow = history[i]!.low;
      }
      stop = moveLow - atr * 1.0;
      // Target: 50% retracement toward lookback VWAP
      target = bar.close + (lookbackVwap - bar.close) * 0.5;
    } else {
      // Short
      let moveHigh = bar.high;
      for (let i = history.length - 1; i >= history.length - LOOKBACK_BARS; i--) {
        if (history[i]!.high > moveHigh) moveHigh = history[i]!.high;
      }
      stop = moveHigh + atr * 1.0;
      target = bar.close + (lookbackVwap - bar.close) * 0.5;
    }

    // Validate
    if (side === "long" && (stop >= bar.close || target <= bar.close)) return null;
    if (side === "short" && (stop <= bar.close || target >= bar.close)) return null;

    // ── Confidence: scales with return magnitude relative to ATR ────────
    const retAtrRatio = absReturn / atr;
    let confidence = BASE_CONFIDENCE + Math.min((retAtrRatio - REVERSAL_ATR_MULTIPLE) / 10, 0.15);
    confidence = Math.round(Math.min(confidence, MAX_CONFIDENCE) * 100) / 100;

    return buildSignal({
      context,
      side,
      stop,
      target,
      confidence,
      lookbackReturn,
      atr,
      avgVolume,
    });
  }
}
