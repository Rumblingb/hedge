import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * RSI(2) Mean-Reversion Strategy
 *
 * Based on: Larry Connors' "Short-Term Trading Strategies That Work"
 * and Connors & Alvarez "High Probability ETF Trading."
 *
 * Core insight: A 2-period RSI is extremely sensitive — when it reaches
 * single digits (<5) or high 90s (>95), the market is temporarily
 * exhausted and mean-reverts within 1-5 bars.
 *
 * This is one of the most widely backtested short-term strategies across
 * asset classes. Published Sharpe ratios range from 0.8-1.5 depending on
 * the market and exit rules.
 *
 * Implementation for 1-min futures:
 * - RSI(2) < 5: oversold → long (mean-reversion up)
 * - RSI(2) > 95: overbought → short (mean-reversion down)
 * - Exit: target at 0.5×ATR profit, stop at 1.5×ATR loss
 * - Max hold: 10 bars (10 minutes on 1-min)
 * - Two signals per day max (frequent scalps)
 *
 * Symbols: ES, NQ, CL, GC (liquid, high-volume futures)
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ", "CL", "GC", "6E", "ZN"]);
const STRATEGY_ID = "rsi2-mean-reversion";
const PATTERN = "rsi2-connors";

const RSI_OVERSOLD = 10;
const RSI_OVERBOUGHT = 90;
const RSI_PERIOD = 2;
const MAX_HOLD_BARS = 15;

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  rsiValue: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, rsiValue } = args;
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
    maxHoldMinutes: MAX_HOLD_BARS, // 10 bars on 1-min = 10 min
    meta: {
      pattern: PATTERN,
      rsi2: Math.round(rsiValue * 100) / 100,
      source: "connors-rsi2",
    },
  };
}

function computeRsi2(prices: number[]): number {
  if (prices.length < RSI_PERIOD + 1) return 50;

  let avgGain = 0;
  let avgLoss = 0;

  for (let i = prices.length - RSI_PERIOD; i < prices.length; i++) {
    const change = prices[i]! - prices[i - 1]!;
    if (change > 0) avgGain += change;
    else avgLoss += Math.abs(change);
  }

  avgGain /= RSI_PERIOD;
  avgLoss /= RSI_PERIOD;

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

export class Rsi2MeanReversionStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "RSI(2) mean-reversion from Larry Connors — fires when RSI(2)<5 (long) or >95 (short). " +
    "10-bar max hold, 0.5ATR target, 1.5ATR stop. High-frequency scalp. ES, NQ, CL, GC.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // ── Symbol gate ───────────────────────────────────────────────────
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    const { bar, history } = context;

    // ── Need enough history for RSI(2) + ATR ──────────────────────────
    if (history.length < 20) return null;

    // ── RSI(2) computation ────────────────────────────────────────────
    const closes = history.slice(-10).map(b => b.close);
    closes.push(bar.close);
    const rsi2 = computeRsi2(closes);

    // ── Trigger ──────────────────────────────────────────────────────
    let side: TradeSide;
    let confidence: number;

    if (rsi2 <= RSI_OVERSOLD) {
      side = "long";
      // Lower RSI → higher conviction
      confidence = 0.55 + (RSI_OVERSOLD - rsi2) * 0.03;
    } else if (rsi2 >= RSI_OVERBOUGHT) {
      side = "short";
      confidence = 0.55 + (rsi2 - RSI_OVERBOUGHT) * 0.03;
    } else {
      return null;
    }

    confidence = Math.round(Math.min(confidence, 0.70) * 100) / 100;

    // ── ATR for stops/targets ────────────────────────────────────────
    const atr = averageTrueRange(history, 14);
    if (atr <= 0) return null;

    // ── Stop/Target ──────────────────────────────────────────────────
    let stop: number;
    let target: number;
    if (side === "long") {
      stop = bar.close - atr * 1.5;
      target = bar.close + atr * 0.5;
    } else {
      stop = bar.close + atr * 1.5;
      target = bar.close - atr * 0.5;
    }

    if (side === "long" && (stop >= bar.close || target <= bar.close)) return null;
    if (side === "short" && (stop <= bar.close || target >= bar.close)) return null;

    // ── Max 2 signals per day ────────────────────────────────────────
    if (context.dailyTradeCount >= 2) return null;

    return buildSignal({ context, side, stop, target, confidence, rsiValue: rsi2 });
  }
}
