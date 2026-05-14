/**
 * regimeOrbBreakout.ts — Regime-aware Opening Range Breakout Strategy
 *
 * Detects market regime (FOMC, expiry, normal, high-vol) and adjusts
 * parameters dynamically for optimal edge.
 *
 * On FOMC days (like today, May 14, 2026):
 *   - Wider range window (16) → stronger breakout levels
 *   - Higher vol threshold (2.0) → filters noise
 *   - Tighter exit (5-bar) → FOMC reversals are violent
 *   - ATR stop (1.5) + target (3.0) → bounded risk/reward
 *
 * On Options Expiry (May 15, 2026 — tomorrow):
 *   - Tighter range (10) → max pain anchoring
 *   - Quick exits (5-bar) → gamma flips are violent
 *
 * On Normal days: standard orb-breakout (12/1.3/8)
 */

import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

// ====== REGIME DETECTION ======

/** Known FOMC release dates for 2026 */
const FOMC_DATES_2026 = new Set([
  "2026-05-07", "2026-05-14", // TODAY
  "2026-06-18", "2026-07-30", "2026-09-17", "2026-11-05", "2026-12-17",
]);

interface RegimeConfig {
  rangeWindow: number;
  volThreshold: number;
  exitOffset: number;     // bars to hold
  stopAtr: number;        // 0 = no stop
  targetAtr: number;      // 0 = no target
  maxHoldMinutes: number;
}

const REGIMES: Record<string, RegimeConfig> = {
  fomc: {
    rangeWindow: 16,
    volThreshold: 2.0,
    exitOffset: 5,
    stopAtr: 1.5,
    targetAtr: 3.0,
    maxHoldMinutes: 240, // Tighter hold on FOMC
  },
  prefomc: {
    rangeWindow: 10,
    volThreshold: 1.3,
    exitOffset: 8,
    stopAtr: 1.0,
    targetAtr: 0,
    maxHoldMinutes: 480,
  },
  postfomc: {
    rangeWindow: 14,
    volThreshold: 1.5,
    exitOffset: 10,
    stopAtr: 2.0,
    targetAtr: 0,
    maxHoldMinutes: 720, // Let trends run
  },
  expiry: {
    rangeWindow: 10,
    volThreshold: 1.5,
    exitOffset: 5,
    stopAtr: 1.0,
    targetAtr: 2.0,
    maxHoldMinutes: 240,
  },
  normal: {
    rangeWindow: 12,
    volThreshold: 1.3,
    exitOffset: 8,
    stopAtr: 0,
    targetAtr: 0,
    maxHoldMinutes: 480,
  },
  // Session-specific overrides (applied on top of base regime)
  ny: {
    rangeWindow: 12,
    volThreshold: 1.5,
    exitOffset: 8,
    stopAtr: 1.0,
    targetAtr: 3.0,
    maxHoldMinutes: 480,
  },
  asia: {
    rangeWindow: 8,
    volThreshold: 1.3,
    exitOffset: 3,
    stopAtr: 0.5,
    targetAtr: 2.0,
    maxHoldMinutes: 240,
  },
  afterhours: {
    rangeWindow: 8,
    volThreshold: 1.3,
    exitOffset: 3,
    stopAtr: 0.5,
    targetAtr: 2.0,
    maxHoldMinutes: 240,
  },
};

/** Get session from hour/minute */
function getSession(now: Date): string {
  const h = now.getUTCHours();
  const m = now.getUTCMinutes();
  const mins = h * 60 + m;
  // Convert to ET (UTC-4 during EDT)
  const etMins = (mins - 240 + 1440) % 1440;
  if (etMins < 180) return "asia";          // 00:00-03:00 ET
  if (etMins < 420) return "london_skip";   // 03:00-07:00 ET - NO EDGE
  if (etMins < 570) return "premarket_skip";// 07:00-09:30 ET - NO EDGE
  if (etMins < 960) return "ny";            // 09:30-16:00 ET
  if (etMins < 1140) return "afterhours";   // 16:00-19:00 ET
  return "asia";                            // 19:00-00:00 ET
}

/**
 * Detect current market regime from calendar + session + optional VIX.
 * Returns session-aware config: skips London/Premarket, uses session-specific params.
 */
function detectRegime(now: Date, vix?: number): { regime: string; config: RegimeConfig } {
  const dateStr = now.toISOString().slice(0, 10);
  const day = now.getDate();
  const dayOfWeek = now.getDay();
  const session = getSession(now);

  // SESSION GATE: skip sessions with no edge
  if (session === "london_skip" || session === "premarket_skip") {
    return { regime: session, config: { rangeWindow: 0, volThreshold: 0, exitOffset: 0, stopAtr: 0, targetAtr: 0, maxHoldMinutes: 0 } };
  }

  // 1. FOMC day → FOMC params override session
  if (FOMC_DATES_2026.has(dateStr)) {
    return { regime: "fomc", config: REGIMES.fomc };
  }

  // 2. Day before/after FOMC
  const nextDay = new Date(now);
  nextDay.setDate(nextDay.getDate() + 1);
  if (FOMC_DATES_2026.has(nextDay.toISOString().slice(0, 10))) {
    return { regime: "prefomc", config: REGIMES.prefomc };
  }
  const prevDay = new Date(now);
  prevDay.setDate(prevDay.getDate() - 1);
  if (FOMC_DATES_2026.has(prevDay.toISOString().slice(0, 10))) {
    return { regime: "postfomc", config: REGIMES.postfomc };
  }

  // 3. Monthly options expiry (3rd Friday + Thursday before)
  if ((dayOfWeek === 5 && day >= 15 && day <= 21) || (dayOfWeek === 4 && day >= 14 && day <= 20)) {
    return { regime: "expiry", config: REGIMES.expiry };
  }

  // 4. VIX-based high vol
  if (vix !== undefined && vix > 25) {
    return { regime: "highvol", config: REGIMES.fomc };
  }

  // 5. Session-specific normal trading
  if (session === "ny") return { regime: "ny", config: REGIMES.ny };
  if (session === "asia") return { regime: "asia", config: REGIMES.asia };
  if (session === "afterhours") return { regime: "afterhours", config: REGIMES.afterhours };

  return { regime: "normal", config: REGIMES.normal };
}

// ====== STRATEGY IMPLEMENTATION ======

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);

function avgVolume(bars: Bar[], window: number): number {
  if (bars.length < window) return 0;
  const slice = bars.slice(-window);
  return slice.reduce((sum, b) => sum + b.volume, 0) / window;
}

function computeOpeningRange(sessionBars: Bar[], rangeWindow: number): { rangeHigh: number; rangeLow: number } | null {
  if (sessionBars.length < rangeWindow) return null;
  const openingBars = sessionBars.slice(0, rangeWindow);
  let rangeHigh = -Infinity;
  let rangeLow = Infinity;
  for (const b of openingBars) {
    if (b.high > rangeHigh) rangeHigh = b.high;
    if (b.low < rangeLow) rangeLow = b.low;
  }
  if (rangeHigh <= rangeLow) return null;
  return { rangeHigh, rangeLow };
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  entry: number;
  stop: number;
  target: number;
  atr: number;
  regime: string;
}): StrategySignal | null {
  const { context, side, entry, stop, target, atr, regime } = args;
  if (!Number.isFinite(entry) || entry <= 0) return null;
  if (stop > 0 && !Number.isFinite(stop)) return null;
  if (target > 0 && !Number.isFinite(target)) return null;
  if (atr <= 0) return null;

  const rr = stop > 0 && target > 0
    ? Math.abs((target - entry) / (entry - stop))
    : 0.5;

  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: "regime-orb-breakout",
    side,
    entry,
    stop,
    target,
    rr,
    confidence: 0.6,
    contracts: 1,
    maxHoldMinutes: 480,
    meta: { regime, atr: Math.round(atr * 100) / 100 },
  };
}

export class RegimeOrbBreakoutStrategy implements Strategy {
  id = "regime-orb-breakout";
  description = "ORB with dynamic FOMC/expiry/normal parameters";

  generateSignal(context: StrategyContext): StrategySignal | null {
    const { symbol, bar, history, sessionHistory } = context;
    if (!TARGET_SYMBOLS.has(symbol)) return null;

    // Detect regime
    const now = new Date();
    const { regime, config } = detectRegime(now);

    // SESSION GATE: skip sessions with no edge
    if (config.rangeWindow === 0) return null;

    // Need enough session bars for opening range
    if (sessionHistory.length < config.rangeWindow) return null;

    const orb = computeOpeningRange(sessionHistory, config.rangeWindow);
    if (!orb) return null;

    const { rangeHigh, rangeLow } = orb;
    const entry = bar.close;

    // Volume check against history
    if (history.length < 20) return null;
    const avgVol = avgVolume(history, 20);
    if (avgVol <= 0) return null;
    if (bar.volume < avgVol * config.volThreshold) return null;

    // ATR for stop/target
    const atr = averageTrueRange(history, 14);
    if (!atr || atr <= 0) return null;

    const isBreakoutUp = entry > rangeHigh;
    const isBreakoutDown = entry < rangeLow;
    if (!isBreakoutUp && !isBreakoutDown) return null;

    const side: TradeSide = isBreakoutUp ? "long" : "short";

    const stop = config.stopAtr > 0
      ? (side === "long" ? entry - config.stopAtr * atr : entry + config.stopAtr * atr)
      : (isBreakoutUp ? rangeLow : rangeHigh);

    const target = config.targetAtr > 0
      ? (side === "long" ? entry + config.targetAtr * atr : entry - config.targetAtr * atr)
      : entry + (side === "long" ? 2 * atr : -2 * atr);

    return buildSignal({ context, side, entry, stop, target, atr, regime });
  }
}
