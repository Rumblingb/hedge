/**
 * #45 Drift-Regime Conditional Cross-Sectional Momentum
 * Source: Singha, M. (Nov 2025). "Discovery of a 13-Sharpe OOS Factor."
 *   arXiv:2511.12490
 *
 * Key finding: Cross-sectional signals are worthless outside "drift regimes."
 * Only rank/signal when >60% of trailing 63 days are positive.
 * Under drift regime: 158.6% annualized, 12.0% vol, ~12% max DD.
 *
 * Implementation: Compute positive-day ratio from daily closes.
 * Gate CSM ranking: only rank assets with positive-day ratio > 0.60.
 * This is NOT a separate strategy — it's a regime filter on CSM signals.
 *
 * Market logic: Stocks/assets in sustained uptrends exhibit predictable
 * cross-sectional momentum because institutional flows cluster in winners.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";
import { getMarketSessionWindow } from "../utils/sessions.js";

const TARGET_SYMBOLS = ["ES", "NQ", "RTY"];
const DRIFT_LOOKBACK_DAYS = 63;
const DRIFT_THRESHOLD = 0.60; // >60% positive days = drift regime
const SPREAD_THRESHOLD = 0.002; // minimum return spread between best/worst

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  rank: number;
  driftRatio: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, rank, driftRatio } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: "drift-regime-csm",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 20,
    meta: {
      rank,
      driftRatio: Math.round(driftRatio * 100) / 100,
      lookbackDays: DRIFT_LOOKBACK_DAYS,
      barIntervalMinutes,
      paper: "arXiv:2511.12490",
    },
  };
}

/**
 * Compute positive-day ratio from daily close history.
 * positiveDayRatio = count(days where close > prev_close) / totalDays
 */
function computePositiveDayRatio(dailyCloses: number[]): number | null {
  if (dailyCloses.length < DRIFT_LOOKBACK_DAYS) return null;
  const window = dailyCloses.slice(-DRIFT_LOOKBACK_DAYS);
  let positiveDays = 0;
  for (let i = 1; i < window.length; i++) {
    if (window[i]! > window[i - 1]!) positiveDays++;
  }
  return positiveDays / (window.length - 1);
}

/**
 * Compute cumulative return from history over a lookback.
 */
function computeReturn(history: Bar[], lookback: number): number | null {
  if (history.length < lookback + 1) return null;
  const oldestClose = history[history.length - lookback - 1]!.close;
  const latestClose = history[history.length - 1]!.close;
  if (oldestClose <= 0) return null;
  return (latestClose - oldestClose) / oldestClose;
}

/**
 * Extract daily closes from intraday bars.
 * Takes the last bar of each day (approximation via close price).
 */
function extractDailyCloses(history: Bar[]): number[] {
  const dailyCloses: number[] = [];
  let lastDate = "";
  for (const bar of history) {
    const date = bar.ts.slice(0, 10); // YYYY-MM-DD
    if (date !== lastDate) {
      if (lastDate !== "") {
        dailyCloses.push(bar.close);
      }
      lastDate = date;
    }
  }
  // Include current partial day
  if (history.length > 0) {
    dailyCloses.push(history[history.length - 1]!.close);
  }
  return dailyCloses;
}

export class DriftRegimeCSMStrategy implements Strategy {
  public readonly id = "drift-regime-csm";
  public readonly description =
    "Cross-sectional momentum gated by drift regime (>60% positive days in 63d). " +
    "Source: Singha 2025 — 13-Sharpe OOS factor. Only ranks when drift regime active.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null; // Daily bars only, intraday needed

    // Session window: wait 30 min into session
    const sessionWindow = getMarketSessionWindow(
      context.symbol,
      context.config.guardrails.sessionStartCt,
    );
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 30) return null;

    // Update internal symbol history
    let internalHistory = this.symbolHistory.get(context.symbol) ?? [];
    internalHistory = [...internalHistory, context.bar];
    if (internalHistory.length > 500) internalHistory = internalHistory.slice(-500);
    this.symbolHistory.set(context.symbol, internalHistory);

    // === DRIFT REGIME CHECK ===
    const dailyCloses = extractDailyCloses(internalHistory);
    const driftRatio = computePositiveDayRatio(dailyCloses);
    if (driftRatio === null || driftRatio < DRIFT_THRESHOLD) {
      return null; // Not in drift regime — don't trade
    }

    const lookback = context.config.tuning.momentumLookbackBars;

    // Compute returns for all target symbols
    const returns: Array<{ symbol: string; ret: number; driftRatio: number }> = [];
    for (const sym of TARGET_SYMBOLS) {
      const hist = sym === context.symbol ? internalHistory : this.symbolHistory.get(sym) ?? [];
      const ret = computeReturn(hist, lookback);
      if (ret !== null) {
        // Also check drift regime for each symbol
        const symCloses = extractDailyCloses(hist);
        const symDrift = computePositiveDayRatio(symCloses) ?? 0;
        // Only include symbols also in drift regime
        if (symDrift >= DRIFT_THRESHOLD) {
          returns.push({ symbol: sym, ret, driftRatio: symDrift });
        }
      }
    }

    if (returns.length < 2) return null;

    // Sort by return descending
    returns.sort((a, b) => b.ret - a.ret);

    const best = returns[0]!;
    const worst = returns[returns.length - 1]!;

    const spread = best.ret - worst.ret;
    if (spread < SPREAD_THRESHOLD) return null;

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
        confidence: 0.68, // Higher confidence due to drift regime filter
        barIntervalMinutes,
        rank: 1,
        driftRatio: best.driftRatio,
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
        confidence: 0.62,
        barIntervalMinutes,
        rank: returns.length,
        driftRatio: worst.driftRatio,
      });
    }

    return null;
  }
}
