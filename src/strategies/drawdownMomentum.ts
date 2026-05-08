/**
 * #41 Max Drawdown & Recovery Momentum
 * Source: Choi, J. (Mar 2014). "Maximum drawdown, recovery, and momentum."
 *   arXiv:1403.8125.
 *
 * Key finding: Max drawdown-based stock selection OUTPERFORMS cumulative-return
 * momentum. Monthly momentum + weekly contrarian from same framework.
 * Carhart 4-factor alphas confirm drawdown signal is orthogonal to standard factors.
 * Improved Sortino/Calmar ratios from drawdown-awareness in ranking.
 *
 * Implementation for Bill/Hedge:
 * Replace cumulative return ranking with drawdown/recovery scores:
 *   - Prefer assets with SMALL max drawdowns (stronger trend)
 *   - Prefer assets with FAST recovery from drawdowns
 *   - Rank by: (recovery_speed / max_drawdown_depth)
 *
 * Market logic: Assets that recover quickly from drawdowns have stronger
 * institutional support. Deep drawdowns indicate weak hands / distribution.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";
import { getMarketSessionWindow } from "../utils/sessions.js";

const TARGET_SYMBOLS = ["ES", "NQ", "RTY"];
const LOOKBACK = 50; // bars for drawdown computation
const MIN_RECOVERY_RATIO = 1.5; // recovery must be 1.5x faster than decline

function buildSignal(args: {
  context: StrategyContext; side: TradeSide; stop: number; target: number;
  confidence: number; barIntervalMinutes: number;
  drawdownDepth: number; recoverySpeed: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, drawdownDepth, recoverySpeed } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol, strategyId: "drawdown-momentum", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 20,
    meta: {
      drawdownDepth: Math.round(drawdownDepth * 10000) / 100,
      recoverySpeed: Math.round(recoverySpeed * 100) / 100,
      paper: "arXiv:1403.8125",
    },
  };
}

interface DrawdownMetrics {
  maxDrawdownPct: number;
  recoveryBars: number;
  declineBars: number;
  recoveryRatio: number; // recovery_speed / decline_speed
  currentInDrawdown: boolean;
}

function computeDrawdownMetrics(history: Bar[]): DrawdownMetrics | null {
  if (history.length < LOOKBACK) return null;
  const closes = history.slice(-LOOKBACK).map((b) => b.close);
  let peak = closes[0]!;
  let maxDrawdownPct = 0;
  let declineBars = 0;
  let recoveryBars = 0;
  let currentDecline = 0;
  let currentRecovery = 0;
  let inDecline = false;
  let inRecovery = false;
  let currentInDrawdown = false;

  for (let i = 1; i < closes.length; i++) {
    const price = closes[i]!;
    if (price > peak) {
      peak = price;
      if (inDecline) {
        declineBars += currentDecline;
        currentDecline = 0;
        inDecline = false;
      }
      if (inRecovery) {
        recoveryBars += currentRecovery;
        currentRecovery = 0;
        inRecovery = false;
      }
    }
    const drawdown = (peak - price) / peak;
    if (drawdown > maxDrawdownPct) maxDrawdownPct = drawdown;

    if (drawdown > 0.01) {
      if (!inDecline && !inRecovery) { inDecline = true; currentDecline = 1; }
      else if (inDecline) currentDecline++;
    } else if (price >= peak * 0.99 && (inDecline || inRecovery)) {
      if (inDecline) { declineBars += currentDecline; currentDecline = 0; inDecline = false; }
      if (inRecovery) { recoveryBars += currentRecovery; currentRecovery = 0; inRecovery = false; }
    }
  }

  currentInDrawdown = closes[closes.length - 1]! < peak * 0.98;
  if (inDecline) declineBars += currentDecline;
  if (inRecovery) recoveryBars += currentRecovery;

  const recoveryRatio = declineBars > 0 ? recoveryBars / declineBars : 0;
  return { maxDrawdownPct, recoveryBars, declineBars, recoveryRatio, currentInDrawdown };
}

export class DrawdownMomentumStrategy implements Strategy {
  public readonly id = "drawdown-momentum";
  public readonly description =
    "Max drawdown + recovery momentum. Ranks by recovery speed / drawdown depth. " +
    "Prefers assets with shallow drawdowns and fast recoveries. Source: Choi 2014 arXiv:1403.8125.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;
    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null;
    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    if (minutesFromCtTime(context.bar.ts, sessionWindow.startCt) < 30) return null;

    let history = this.symbolHistory.get(context.symbol) ?? [];
    history = [...history, context.bar];
    if (history.length > 300) history = history.slice(-300);
    this.symbolHistory.set(context.symbol, history);

    const metrics = computeDrawdownMetrics(history);
    if (!metrics) return null;

    // Gate: only trade when recovery ratio is favorable
    if (metrics.recoveryRatio < MIN_RECOVERY_RATIO) return null;
    // Gate: must be in recovery phase (not still declining)
    if (metrics.currentInDrawdown) return null;

    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    // Direction: go long on assets showing strong recovery
    const side: TradeSide = "long";
    const risk = atr * 1.0;
    const targetRr = Math.max(context.config.guardrails.minRr, 2.0);
    const entry = context.bar.close;
    const stop = entry - risk;
    const target = entry + risk * targetRr;

    // Confidence: higher when recovery is strong relative to drawdown
    const confidence = Math.min(0.75, 0.45 + (metrics.recoveryRatio / 4) * 0.3);

    return buildSignal({
      context, side, stop, target, confidence, barIntervalMinutes,
      drawdownDepth: metrics.maxDrawdownPct, recoverySpeed: metrics.recoveryRatio,
    });
  }
}
