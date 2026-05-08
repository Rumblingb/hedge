/**
 * #46 Two-Level Uncertainty for Safe Cross-Sectional Strategy Deployment
 * Source: Sanderink, U. (Feb 2026). "When Alpha Breaks: Two-Level
 *   Uncertainty for Safe Deployment of Cross-Sectional Stock Rankers."
 *   arXiv:2603.13252.
 *
 * Key finding: CS rankers fail silently under non-stationarity.
 * Two-level uncertainty decomposition:
 *   1. Ranking uncertainty (epistemic): "is the rank order correct?"
 *      → High when asset returns are tightly clustered (hard to distinguish)
 *   2. Regime uncertainty (distribution shift): "is the model still valid?"
 *      → High when recent vol/correlation structure differs from historical
 *
 * Implementation: Compute both uncertainty levels per bar.
 * Only deploy signals when both uncertainties are low.
 * This is NOT a standalone strategy — it's a deployment gate that
 * adjusts confidence for any CSM-based strategy.
 *
 * Market logic: In 2024, LightGBM rankers broke during AI rally/sector
 * rotation because they didn't detect the regime shift. This gate
 * explicitly quantifies when the model should be turned off.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";
import { getMarketSessionWindow } from "../utils/sessions.js";

const RANK_LOOKBACK = 20;
const REGIME_LOOKBACK = 50;
const RANK_UNCERTAINTY_THRESHOLD = 0.7; // Below this = too uncertain to rank
const REGIME_UNCERTAINTY_THRESHOLD = 0.4; // Above this = regime shifted, don't deploy
const TARGET_SYMBOLS = ["ES", "NQ", "RTY"];

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  rankUncertainty: number;
  regimeUncertainty: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, rankUncertainty, regimeUncertainty } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  // Confidence penalized by both uncertainties
  const adjustedConfidence = confidence * (1 - regimeUncertainty) * rankUncertainty;

  return {
    symbol: context.symbol,
    strategyId: "two-level-uncertainty",
    side,
    entry,
    stop,
    target,
    rr,
    confidence: adjustedConfidence,
    contracts: 1,
    maxHoldMinutes: 20,
    meta: {
      rankUncertainty: Math.round(rankUncertainty * 100) / 100,
      regimeUncertainty: Math.round(regimeUncertainty * 100) / 100,
      adjustedConfidence: Math.round(adjustedConfidence * 100) / 100,
      paper: "arXiv:2603.13252",
    },
  };
}

/**
 * Ranking uncertainty: how distinguishable are the top/bottom ranks?
 * Computed as: 1 - (spread between best and worst) / (average spread)
 * High spread = low uncertainty (assets clearly separated)
 * Low spread = high uncertainty (assets clustered, ranking fragile)
 */
function computeRankUncertainty(returns: Array<{ symbol: string; ret: number }>): number {
  if (returns.length < 3) return 0;

  const sorted = [...returns].sort((a, b) => b.ret - a.ret);
  const best = sorted[0]!.ret;
  const worst = sorted[sorted.length - 1]!.ret;
  const spread = best - worst;

  // Average pairwise spread
  let totalSpread = 0;
  let count = 0;
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      totalSpread += Math.abs(sorted[i]!.ret - sorted[j]!.ret);
      count++;
    }
  }
  const avgSpread = count > 0 ? totalSpread / count : 0;

  if (avgSpread <= 0) return 0;

  // Uncertainty = 1 - (max spread / avg spread), normalized
  const ratio = spread / avgSpread;
  return Math.max(0, Math.min(1, (ratio - 1) / 3)); // ratio=1 → 0, ratio=4+ → 1
}

/**
 * Regime uncertainty: has the vol/correlation structure shifted?
 * Compare recent vol structure vs longer-term vol structure.
 * Large deviation = regime shift = high uncertainty.
 */
function computeRegimeUncertainty(history: Bar[]): number {
  if (history.length < REGIME_LOOKBACK + 10) return 0.5; // Insufficient data

  // Recent vol (last 10 bars) vs longer vol (last 50 bars)
  const recentReturns: number[] = [];
  const longReturns: number[] = [];

  for (let i = 1; i < history.length; i++) {
    const ret = Math.log(history[i]!.close / history[i - 1]!.close);
    if (i >= history.length - 10) {
      recentReturns.push(ret);
    }
    if (i >= history.length - REGIME_LOOKBACK) {
      longReturns.push(ret);
    }
  }

  if (recentReturns.length < 5 || longReturns.length < 10) return 0.5;

  const recentVol = stdDev(recentReturns);
  const longVol = stdDev(longReturns);

  if (longVol <= 0) return 0;

  // Vol ratio deviation from 1.0
  const volRatio = recentVol / longVol;
  const volShift = Math.abs(volRatio - 1.0);

  // Also check skew: recent returns consistently one-sided?
  const recentMean = recentReturns.reduce((a, b) => a + b, 0) / recentReturns.length;
  const longMean = longReturns.reduce((a, b) => a + b, 0) / longReturns.length;
  const meanShift =
    longVol > 0 ? Math.abs(recentMean - longMean) / longVol : 0;

  // Combined regime uncertainty
  return Math.min(1, volShift * 2 + meanShift);
}

function stdDev(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function computeReturn(history: Bar[], lookback: number): number | null {
  if (history.length < lookback + 1) return null;
  const oldestClose = history[history.length - lookback - 1]!.close;
  const latestClose = history[history.length - 1]!.close;
  if (oldestClose <= 0) return null;
  return (latestClose - oldestClose) / oldestClose;
}

export class TwoLevelUncertaintyStrategy implements Strategy {
  public readonly id = "two-level-uncertainty";
  public readonly description =
    "Two-level uncertainty-gated cross-sectional momentum. " +
    "Decomposes uncertainty into ranking (epistemic) and regime (distribution shift). " +
    "Only deploys when both uncertainties are low. Source: Sanderink 2026 arXiv:2603.13252.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null;

    const sessionWindow = getMarketSessionWindow(
      context.symbol,
      context.config.guardrails.sessionStartCt,
    );
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 30) return null;

    // Internal history
    let history = this.symbolHistory.get(context.symbol) ?? [];
    history = [...history, context.bar];
    if (history.length > 300) history = history.slice(-300);
    this.symbolHistory.set(context.symbol, history);

    // LEVEL 2: Regime uncertainty check FIRST (cheaper to compute)
    const regimeUncertainty = computeRegimeUncertainty(history);
    if (regimeUncertainty > REGIME_UNCERTAINTY_THRESHOLD) {
      return null; // Regime shifted — don't deploy
    }

    // LEVEL 1: Ranking uncertainty
    const lookback = context.config.tuning.momentumLookbackBars;
    const returns: Array<{ symbol: string; ret: number }> = [];

    for (const sym of TARGET_SYMBOLS) {
      const hist = sym === context.symbol ? history : this.symbolHistory.get(sym) ?? [];
      const ret = computeReturn(hist, lookback);
      if (ret !== null) {
        returns.push({ symbol: sym, ret });
      }
    }

    if (returns.length < 2) return null;

    const rankUncertainty = computeRankUncertainty(returns);
    if (rankUncertainty < RANK_UNCERTAINTY_THRESHOLD) {
      return null; // Rankings too uncertain to trust
    }

    // Proceed with CSM logic (same as cross-sectional-momentum but uncertainty-gated)
    returns.sort((a, b) => b.ret - a.ret);
    const best = returns[0]!;
    const worst = returns[returns.length - 1]!;

    const spread = best.ret - worst.ret;
    if (spread < 0.001) return null;

    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    const barRange = context.bar.high - context.bar.low;
    if (barRange > atr * context.config.tuning.volatilityKillAtrMultiple) return null;

    const targetRr = Math.max(context.config.guardrails.minRr, 2.5);

    if (context.symbol === best.symbol) {
      const stop = context.bar.close - atr * 1.0;
      const risk = context.bar.close - stop;
      if (risk <= 0) return null;
      return buildSignal({
        context,
        side: "long",
        stop,
        target: context.bar.close + risk * targetRr,
        confidence: 0.66,
        barIntervalMinutes,
        rankUncertainty,
        regimeUncertainty,
      });
    }

    if (context.symbol === worst.symbol) {
      const stop = context.bar.close + atr * 1.0;
      const risk = stop - context.bar.close;
      if (risk <= 0) return null;
      return buildSignal({
        context,
        side: "short",
        stop,
        target: context.bar.close - risk * targetRr,
        confidence: 0.64,
        barIntervalMinutes,
        rankUncertainty,
        regimeUncertainty,
      });
    }

    return null;
  }
}
