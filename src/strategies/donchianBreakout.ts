import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

// Local helpers (not exported from indicators.ts)
function highest(history: Array<{ high: number }>, period: number): number {
  return Math.max(...history.slice(-period).map((b) => b.high));
}
function lowest(history: Array<{ low: number }>, period: number): number {
  return Math.min(...history.slice(-period).map((b) => b.low));
}

/**
 * Donchian Breakout Strategy — ported from Rust gold strategies
 *
 * Source: bill-core/src/gold_strategies.rs :: lw_donchian_breakout
 * Proven concept: Larry Williams Donchian breakout with 20-bar lookback.
 *
 * Current market context (May 2026):
 * - VIX 17.99 (low vol, trending up)
 * - S&P 500 near ATH (7,400)
 * - Donchian breakouts work in trending markets with low vol
 *
 * The Rust gold implementation was isolated. This TS wrapper connects it to
 * the existing pipeline so it can be backtested, OOS-validated, and promoted.
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ", "CL", "GC"]);
const STRATEGY_ID = "donchian-breakout";
const PATTERN = "donchian-breakout-gold-v1";
const DEFAULT_LOOKBACK = 20;
const MIN_RR = 2.0;

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  entry: number;
  stop: number;
  target: number;
  confidence: number;
  lookback: number;
}): StrategySignal | null {
  const { context, side, entry, stop, target, confidence, lookback } = args;
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
      lookback,
      source: "gold-strategies-rust",
    },
  };
}

export class DonchianBreakoutStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Donchian breakout (gold) — 20-bar channel breakout with ATR-based stop and 2R target.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    const { bar, history } = context;
    if (history.length < DEFAULT_LOOKBACK + 2) return null;

    // Donchian channel: highest high and lowest low over lookback
    const lookbackHigh = highest(history, DEFAULT_LOOKBACK);
    const lookbackLow = lowest(history, DEFAULT_LOOKBACK);
    const atr = averageTrueRange(history, 14);
    if (atr <= 0) return null;

    // Breakout above the channel = long
    if (bar.close > lookbackHigh && bar.high > lookbackHigh) {
      const stop = lookbackLow - atr * 0.5;
      const risk = bar.close - stop;
      const target = bar.close + (risk * MIN_RR);
      if (risk <= 0) return null;

      return buildSignal({
        context,
        side: "long",
        entry: bar.close,
        stop,
        target,
        confidence: 0.55 + (atr > 0 ? 0.05 : 0),
        lookback: DEFAULT_LOOKBACK,
      });
    }

    // Breakdown below the channel = short
    if (bar.close < lookbackLow && bar.low < lookbackLow) {
      const stop = lookbackHigh + atr * 0.5;
      const risk = stop - bar.close;
      const target = bar.close - (risk * MIN_RR);
      if (risk <= 0) return null;

      return buildSignal({
        context,
        side: "short",
        entry: bar.close,
        stop,
        target,
        confidence: 0.55 + (atr > 0 ? 0.05 : 0),
        lookback: DEFAULT_LOOKBACK,
      });
    }

    return null;
  }
}
