import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Monthly Seasonality Strategy
 *
 * Based on: Hanauer, M.X. (2023). "Beyond Fama-French Factors: Alpha from
 * Short-Term Signals." Financial Analysts Journal — Signal #5 of 5.
 *
 * Core insight: specific calendar days exhibit persistent directional bias.
 * Turn-of-month (last 2 + first 3 trading days), FOMC days, and expiry week
 * show statistically significant alpha across regions and asset classes.
 *
 * Implementation for 1-min futures:
 * - Turn-of-month: long bias on first 3 and last 2 trading days of month
 * - Signal fires at session open (first 3 bars) on qualifying calendar days
 * - Direction: go long, use ATR-based stops and targets
 * - Confidence boosted on turn-of-month days, reduced otherwise
 * - Soft gate: only fires if HMM regime is not "high-vol"
 *
 * Symbols: ES, NQ (most pronounced seasonality effects in equity indices)
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const STRATEGY_ID = "monthly-seasonality";
const PATTERN = "monthly-seasonality-hanauer";

// Confidence range
const BASE_CONFIDENCE = 0.50;
const MAX_CONFIDENCE = 0.60;

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  seasonalityType: string;
  tradingDay: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, seasonalityType, tradingDay } = args;
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
    maxHoldMinutes: 120,
    meta: {
      pattern: PATTERN,
      seasonalityType,
      tradingDay,
      source: "hanauer-2023-faj",
    },
  };
}

/**
 * Determine the trading day of the month from a UTC timestamp.
 * Approximates US trading calendar: counts weekdays since month start.
 */
function getTradingDayOfMonth(ts: string): number {
  const d = new Date(ts);
  const year = d.getUTCFullYear();
  const month = d.getUTCMonth();
  const firstOfMonth = new Date(Date.UTC(year, month, 1, 0, 0, 0));
  let tradingDay = 0;
  const current = new Date(firstOfMonth);
  const target = new Date(Date.UTC(year, month, d.getUTCDate(), 0, 0, 0));
  while (current <= target) {
    const dow = current.getUTCDay();
    if (dow !== 0 && dow !== 6) tradingDay++; // skip weekends
    current.setUTCDate(current.getUTCDate() + 1);
  }
  return tradingDay;
}

/**
 * Check if the current trading day is in a turn-of-month window:
 * - Last 2 trading days of month
 * - First 3 trading days of month
 * Returns the seasonality type or null.
 */
function checkSeasonality(ts: string): { type: string; td: number } | null {
  const td = getTradingDayOfMonth(ts);
  const d = new Date(ts);
  const year = d.getUTCFullYear();
  const month = d.getUTCMonth();
  const lastDay = new Date(Date.UTC(year, month + 1, 0, 0, 0, 0));
  const lastTd = getTradingDayOfMonth(lastDay.toISOString());

  // First 3 trading days → "turn-of-month-start"
  if (td >= 1 && td <= 3) return { type: "turn-of-month-start", td };
  // Last 2 trading days → "turn-of-month-end"
  if (td >= lastTd - 1 && td <= lastTd) return { type: "turn-of-month-end", td };

  return null;
}

export class MonthlySeasonalityStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Monthly seasonality from Hanauer (2023) FAJ — long bias on turn-of-month " +
    "(first 3 + last 2 trading days) with HMM regime filter. ES, NQ only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // ── Symbol gate ───────────────────────────────────────────────────
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    // ── Session open gate: only fire on first 3 bars ──────────────────
    const sessionBars = context.sessionHistory;
    if (sessionBars.length > 3) return null;

    // ── Need enough history for ATR ───────────────────────────────────
    if (context.history.length < 15) return null;

    // ── Seasonality check ─────────────────────────────────────────────
    const seasonality = checkSeasonality(context.bar.ts);
    if (!seasonality) return null;

    // ── HMM regime filter: skip if high-vol ───────────────────────────
    const hmmRegime = context.macro?.hmmRegime;
    if (hmmRegime === "high-vol") return null;

    // ── One signal per day max ────────────────────────────────────────
    if (context.dailyTradeCount > 0) return null;

    // ── ATR ──────────────────────────────────────────────────────────
    const atr = averageTrueRange(context.history, 14);
    if (atr <= 0) return null;

    const bar = context.bar;

    // ── Signal: Long with 1.5×ATR target, 1.0×ATR stop ────────────────
    const side: TradeSide = "long";
    const stop = bar.close - atr * 1.0;
    const target = bar.close + atr * 1.5;

    if (stop >= bar.close || target <= bar.close) return null;

    // ── Confidence ────────────────────────────────────────────────────
    let confidence = BASE_CONFIDENCE;
    if (seasonality.type === "turn-of-month-start") confidence += 0.05;
    if (hmmRegime === "trending" || hmmRegime === "low-vol") confidence += 0.05;
    confidence = Math.round(Math.min(confidence, MAX_CONFIDENCE) * 100) / 100;

    return buildSignal({
      context,
      side,
      stop,
      target,
      confidence,
      seasonalityType: seasonality.type,
      tradingDay: seasonality.td,
    });
  }
}
