import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Carry Trade Strategy
 * Exploits yield differential / roll yield across futures.
 * Long contango markets with positive carry, short backwardation markets.
 * Based on the academic "Carry Trade" factor by Koijen, Moskowitz, Pedersen (2018).
 * Adapted for our 6-market futures universe.
 */

const CARRY_ROLL_PERIODS: Record<string, { frontMonth: number; nextMonth: number }> = {
  ES: { frontMonth: 3, nextMonth: 6 },   // Quarterly roll
  NQ: { frontMonth: 3, nextMonth: 6 },
  CL: { frontMonth: 1, nextMonth: 2 },    // Monthly roll
  GC: { frontMonth: 2, nextMonth: 4 },    // Bi-monthly
  "6E": { frontMonth: 3, nextMonth: 6 },
  ZB: { frontMonth: 3, nextMonth: 6 },
};

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  carrySignal: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, carrySignal } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: "carry-trade",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 480, // Longer hold for carry trades
    meta: {
      pattern: carrySignal > 0 ? "positive-carry" : "negative-carry",
      carrySignal: Number(carrySignal.toFixed(4)),
    },
  };
}

export class CarryTradeStrategy implements Strategy {
  public readonly id = "carry-trade";
  public readonly description =
    "Exploits futures roll yield: long positive carry (contango), short negative carry (backwardation). Trades held longer than intraday strategies.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const sourceHistory = context.sessionHistory.length >= 20 ? context.sessionHistory : context.history;
    if (sourceHistory.length < 20) return null;

    const recent = sourceHistory.slice(-20);
    const atr = averageTrueRange(recent, 14);
    if (atr <= 0) return null;

    // Estimate carry from recent price trend and contango/backwardation structure
    // Positive carry: price drifting up over 20 bars + close above 20-bar VWAP
    const closes = recent.map((b) => b.close);
    const volumes = recent.map((b) => b.volume);
    const vwap20 = closes.reduce((sum, c, i) => sum + c * volumes[i], 0) /
      volumes.reduce((sum, v) => sum + v, 0);

    const startPrice = recent[0].close;
    const endPrice = recent[recent.length - 1].close;
    const carrySignal = (endPrice - startPrice) / startPrice;

    // Only trade when carry signal is strong
    const threshold = 0.002; // 0.2% drift
    if (Math.abs(carrySignal) < threshold) return null;

    // Only trade when price is above VWAP for longs, below for shorts
    const currentPrice = context.bar.close;

    if (carrySignal > threshold && currentPrice > vwap20) {
      // Positive carry: go long
      const stop = currentPrice - atr * 1.5;
      const target = currentPrice + atr * 2.5;
      if (stop >= currentPrice) return null;

      return buildSignal({
        context,
        side: "long",
        stop,
        target,
        confidence: Math.min(0.65, Math.abs(carrySignal) * 150),
        carrySignal,
      });
    }

    if (carrySignal < -threshold && currentPrice < vwap20) {
      // Negative carry: go short
      const stop = currentPrice + atr * 1.5;
      const target = currentPrice - atr * 2.5;
      if (stop <= currentPrice) return null;

      return buildSignal({
        context,
        side: "short",
        stop,
        target,
        confidence: Math.min(0.65, Math.abs(carrySignal) * 150),
        carrySignal,
      });
    }

    return null;
  }
}
