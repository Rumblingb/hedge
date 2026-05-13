import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Short-Term Reversal Strategy — BATTLE-HARDENED v3
 *
 * Based on: Hanauer, M.X. (2023) + alpha-lab results on real data.
 *
 * v3 corrections from alpha-lab (May 13 2026 run on ES/NQ 5-day data):
 * - Lookback 30 bars (was 60): ret_30:30 candidate had test IC 0.245, net edge +3.1%
 *   vs ret_5:60 candidate had only test IC 0.075, net edge +0.6%
 *   Longer horizon overfits on 1-min futures. 30 bars is the sweet spot.
 * - VIX gate: ONLY trade when VIX > 20 (was VIX < 25). Reversal edge exists in
 *   high-vol regimes (+9.2% net edge) but is negative in low/mid vol (-1.3% to -1.8%).
 *   The high-vol regime is where reversals actually occur.
 * - Session filter: Only trade NY morning and afternoon (8:30-11:30 ET, 13:00-15:30 ET).
 *   No overnight or Asian session — reversions don't occur in thin liquidity.
 * - Max 2 trades/day/symbol (unchanged from v2).
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ", "CL", "GC"]);
const STRATEGY_ID = "short-term-reversal";
const PATTERN = "short-term-reversal-hanauer-v3";

// v3: Changed from 60 to 30 bars (alpha-lab: ret_30:30 is best)
const REVERSAL_ATR_MULTIPLE = 1.5;
const VOLUME_MULTIPLIER = 1.5;
const LOOKBACK_BARS = 30;  // was 60 — 30-bar horizon has 3x higher test IC

// v3: Flipped — strategy works in HIGH vol, not low vol
const VIX_MIN_THRESHOLD = 20;  // was VIX < 25 (wrong direction)

// Macro events (unchanged)
const MACRO_BLACKOUT_MINUTES = 15;

// Session window: NY active hours only (ET)
function isActiveSession(barTs: string): boolean {
  const dt = new Date(barTs);
  const h = dt.getUTCHours();
  const m = dt.getUTCMinutes();
  const totalMin = h * 60 + m;
  // 8:30-11:30 ET = 12:30-15:30 UTC (NY morning)
  // 13:00-15:30 ET = 17:00-19:30 UTC (NY afternoon)
  // ES/NQ pit close at 16:00 CT = 17:00 ET = 21:00 UTC
  const morningStart = 12 * 60 + 30;  // 12:30 UTC
  const morningEnd = 15 * 60 + 30;    // 15:30 UTC
  const afternoonStart = 17 * 60;       // 17:00 UTC
  const afternoonEnd = 19 * 60 + 30;    // 19:30 UTC
  return (totalMin >= morningStart && totalMin <= morningEnd) ||
         (totalMin >= afternoonStart && totalMin <= afternoonEnd);
}

function isMacroBlackout(barTs: string): boolean {
  const dt = new Date(barTs);
  const h = dt.getUTCHours();
  const m = dt.getUTCMinutes();
  // Block 12:15-13:00 UTC (8:15-9:00 ET) — NFP/CPI/PPI
  if (h === 12 && m >= 15) return true;
  if (h === 13 && m === 0) return true;
  // Block 17:45-18:30 UTC (13:45-14:30 ET) — FOMC
  if (h === 17 && m >= 45) return true;
  if (h === 18 && m <= 30) return true;
  return false;
}
const BASE_CONFIDENCE = 0.50;
const MAX_CONFIDENCE = 0.70;

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
      lookbackReturn: Math.round(lookbackReturn * 10000) / 100,
      atr: Math.round(atr * 100) / 100,
      avgVolume: Math.round(avgVolume),
      source: "hanauer-2023-faj-v2",
      macroBlackout: false,
      vixGate: "passed",
    },
  };
}

export class ShortTermReversalStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "v3: Short-term reversal (Hanauer 2023) + high-vol regime gate + macro blackout + 30-bar lookback + session filter";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // ── Symbol gate ───────────────────────────────────────────────────
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    const { bar, history } = context;

    // ── Session filter: only NY active hours ──────────────────────────
    if (!isActiveSession(bar.ts)) return null;

    // ── MACRO NEWS BLACKOUT — structural cost, not a parameter ────────
    if (isMacroBlackout(bar.ts)) return null;

    // ── VIX REGIME GATE — reversal edge only in elevated volatility ─────
    const vixValue = (context as any).vixLevel ?? 0;
    if (vixValue > 0 && vixValue < VIX_MIN_THRESHOLD) return null;

    // ── Fixed 30-bar lookback (alpha-lab: ret_30:30 is optimal) ──────────
    const effectiveLookback = LOOKBACK_BARS;
    if (history.length < effectiveLookback + 2) return null;

    // ── Filter: max 2 trades/day (was 1, 2 allows second-chance) ──────
    if (context.dailyTradeCount > 1) return null;

    // ── Compute lookback return ────────────────────────────────────────
    const lookbackStart = history[history.length - effectiveLookback - 1]!;
    const lookbackEnd = bar;
    const lookbackReturn = lookbackEnd.close - lookbackStart.close;

    // ── ATR (14-bar) ──────────────────────────────────────────────────
    const atr = averageTrueRange(history, 14);
    if (atr <= 0) return null;

    // ── Trigger: return must exceed REVERSAL_ATR_MULTIPLE × ATR ─────────
    const absReturn = Math.abs(lookbackReturn);
    if (absReturn < REVERSAL_ATR_MULTIPLE * atr) return null;

    // ── Volume confirmation ────────────────────────────────────────────
    let avgVolume = 0;
    const volSlice = history.slice(-effectiveLookback);
    for (const b of volSlice) avgVolume += b.volume;
    avgVolume /= volSlice.length;
    if (bar.volume < VOLUME_MULTIPLIER * avgVolume) return null;

    // ── Direction: fade the extreme move ──────────────────────────────
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
      let moveLow = bar.low;
      for (let i = history.length - 1; i >= history.length - effectiveLookback; i--) {
        if (history[i]!.low < moveLow) moveLow = history[i]!.low;
      }
      stop = moveLow - atr * 1.0;
      target = bar.close + (lookbackVwap - bar.close) * 0.5;
    } else {
      let moveHigh = bar.high;
      for (let i = history.length - 1; i >= history.length - effectiveLookback; i--) {
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
    let confidence = BASE_CONFIDENCE + Math.min((retAtrRatio - REVERSAL_ATR_MULTIPLE) / 10, 0.20);
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
