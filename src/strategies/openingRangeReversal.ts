import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * Opening Range Reversal Strategy — BATTLE-HARDENED v2
 *
 * Classic prop firm opening range breakout/fade strategy.
 * Structural improvements over v1 (which scored -0.067R, near-zero):
 * 1. WIDER WINDOW: 15-90 min session window (was 15-60). NQ/ES need the full first hour.
 * 2. REMOVED ATR KILL FILTER: was killing trades during natural ORB volatility.
 *    Replaced with volume-only filter: low volume = skip (no conviction).
 * 3. EXTENDED MAX HOLD: 45 min (was 20). ORB trades need time to develop.
 *
 * The ORB concept is sound and used by prop firms for decades.
 * The v1 implementation was too tight — this relaxes the non-essential constraints
 * while keeping the core signal logic intact.
 */

function wickToBodyRatio(open: number, high: number, low: number, close: number): { upper: number; lower: number } {
  const body = Math.max(Math.abs(close - open), 0.0001);
  const upper = (high - Math.max(open, close)) / body;
  const lower = (Math.min(open, close) - low) / body;
  return { upper, lower };
}

function volumeRatio(currentVolume: number, history: Array<{ volume: number }>): number {
  if (history.length === 0) return 0;
  const average = history.reduce((sum, bar) => sum + bar.volume, 0) / history.length;
  return average > 0 ? currentVolume / average : 0;
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: "opening-range-reversal",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 45, // was 20 — extended for NQ/ES
    meta: {
      sessionMinute: minutesFromCtTime(
        context.bar.ts,
        getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt).startCt
      ),
      barIntervalMinutes,
      version: "v2",
    },
  };
}

export class OpeningRangeReversalStrategy implements Strategy {
  public readonly id = "opening-range-reversal";
  public readonly description = "v2: Index-only ORB with wider window (15-90 min), volume filter, 45-min hold.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    const dailyLike = barIntervalMinutes >= 720;
    const sourceHistory = dailyLike ? context.history : context.sessionHistory;

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    // v2: wider window — 15 to 90 minutes (was 15 to 60)
    if (!dailyLike && (sessionMinute < 15 || sessionMinute > 90)) {
      return null;
    }

    const lookback = dailyLike ? 6 : 15;
    if (sourceHistory.length < lookback) return null;

    const openingRange = sourceHistory.slice(-lookback);
    const openingHigh = Math.max(...openingRange.map((bar) => bar.high));
    const openingLow = Math.min(...openingRange.map((bar) => bar.low));
    const ratios = wickToBodyRatio(context.bar.open, context.bar.high, context.bar.low, context.bar.close);
    const targetRr = dailyLike
      ? Math.max(2, context.config.guardrails.minRr)
      : Math.max(context.config.guardrails.minRr, 2.8);

    // v2: REMOVED ATR kill filter — was killing valid ORB trades.
    // Replaced with volume-only check: if volume is extremely low, skip.
    const volRatio = volumeRatio(context.bar.volume, openingRange);
    if (volRatio < 0.3) return null; // extremely low volume = no institutional interest

    // ── SHORT SIGNAL: Price breaks above range with long wick ──────────
    if (context.bar.high > openingHigh && context.bar.close < openingHigh && ratios.upper >= 1.2) {
      const atr = averageTrueRange(sourceHistory, Math.min(14, Math.max(5, lookback + 2)));
      const stop = atr > 0
        ? Math.min(context.bar.high, context.bar.close + atr)
        : context.bar.high;
      const risk = stop - context.bar.close;
      if (risk <= 0) return null;

      // v2: confidence adjusts based on wick/volume quality
      const confidence = Math.min(0.76 + (ratios.upper > 2 ? 0.08 : 0) + (volRatio > 1.5 ? 0.06 : 0), 0.90);

      return buildSignal({
        context,
        side: "short",
        stop,
        target: context.bar.close - (risk * targetRr),
        confidence: Math.round(confidence * 100) / 100,
        barIntervalMinutes,
      });
    }

    // ── LONG SIGNAL: Price breaks below range with long lower wick ─────
    if (context.bar.low < openingLow && context.bar.close > openingLow && ratios.lower >= 1.2) {
      const atr = averageTrueRange(sourceHistory, Math.min(14, Math.max(5, lookback + 2)));
      const stop = atr > 0
        ? Math.max(context.bar.low, context.bar.close - atr)
        : context.bar.low;
      const risk = context.bar.close - stop;
      if (risk <= 0) return null;

      const confidence = Math.min(0.76 + (ratios.lower > 2 ? 0.08 : 0) + (volRatio > 1.5 ? 0.06 : 0), 0.90);

      return buildSignal({
        context,
        side: "long",
        stop,
        target: context.bar.close + (risk * targetRr),
        confidence: Math.round(confidence * 100) / 100,
        barIntervalMinutes,
      });
    }

    return null;
  }
}
