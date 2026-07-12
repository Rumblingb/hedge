import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { minutesFromCtTime } from "../utils/time.js";

/**
 * Intraday Momentum Strategy
 *
 * Implements the "first half-hour predicts last half-hour" anomaly
 * (Gao, Han, Li, and Zhou, 2018).
 *
 * At 10:30 CT, compute the return over the first 30 minutes of the session
 * (bar 0 open → bar 29 close). If that return exceeds ±0.3%, fire a
 * momentum-continuation trade:
 *
 * - First-30-min return > +0.3%  → long  (upside momentum)
 * - First-30-min return < -0.3%  → short (downside momentum)
 *
 * - Stop:  1.0× ATR(14) from entry
 * - Target: 1.5× ATR(14) from entry
 * - Confidence: scaled 0.45–0.60 by abs(return) magnitude
 * - Contracts: 1, max hold: 120 minutes (until ~14:30 CT)
 * - One signal per day only
 * - ES and NQ only
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const STRATEGY_ID = "intraday-momentum";
const PATTERN = "intraday-momentum-anomaly";

const RETURN_THRESHOLD = 0.003;    // 0.3%
const MIN_CONFIDENCE = 0.45;
const MAX_CONFIDENCE = 0.60;
const MAX_ABS_RETURN = 0.015;      // cap for confidence scaling at 1.5%
const STOP_ATR_MULT = 1.0;
const TARGET_ATR_MULT = 1.5;
const CONTRACTS = 1;
const MAX_HOLD_MINUTES = 120;

function computeFirst30MinReturn(sessionHistory: Bar[]): number | null {
  if (sessionHistory.length < 30) return null;
  const openBar = sessionHistory[0]!;
  const closeBar = sessionHistory[29]!;
  if (openBar.open <= 0) return null;
  return (closeBar.close - openBar.open) / openBar.open;
}

function scaleConfidence(absReturn: number): number {
  if (absReturn >= MAX_ABS_RETURN) return MAX_CONFIDENCE;
  const t = (absReturn - RETURN_THRESHOLD) / (MAX_ABS_RETURN - RETURN_THRESHOLD);
  const clamped = Math.max(0, Math.min(1, t));
  return MIN_CONFIDENCE + clamped * (MAX_CONFIDENCE - MIN_CONFIDENCE);
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  first30MinReturn: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, first30MinReturn } = args;
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
    contracts: CONTRACTS,
    maxHoldMinutes: MAX_HOLD_MINUTES,
    meta: {
      pattern: PATTERN,
      first30MinReturn: Math.round(first30MinReturn * 10000) / 100, // bp
    },
  };
}

export class IntradayMomentumStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Intraday Momentum: first-30-min return predicts session-direction momentum. Fire at 10:30 CT, hold up to 120 min. ES/NQ only. (Gao, Han, Li, Zhou 2018)";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Only ES and NQ
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    // One signal per day max
    if (context.dailyTradeCount > 0) return null;

    const sessionWindow = getMarketSessionWindow(
      context.symbol,
      context.config.guardrails.sessionStartCt,
    );
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);

    // Fire at exactly 10:30 CT (120 minutes into session when startCt is 08:30)
    // sessionMinute 119 = bar closing at 10:29:59, sessionMinute 120 = bar closing at 10:30:59
    // We fire on the bar that covers 10:30 CT (sessionMinute 120)
    if (sessionMinute !== 120) return null;

    const sessionBars = context.sessionHistory;
    if (sessionBars.length < 30) return null;

    // Compute first-30-min return from bar[0].open to bar[29].close
    const first30MinReturn = computeFirst30MinReturn(sessionBars);
    if (first30MinReturn === null) return null;

    // ATR for stop/target sizing
    const atr = averageTrueRange([...context.history.slice(-20), context.bar], 14);
    if (atr <= 0) return null;

    const bar = context.bar;

    if (first30MinReturn > RETURN_THRESHOLD) {
      // Upside momentum → long
      const stop = bar.close - atr * STOP_ATR_MULT;
      const target = bar.close + atr * TARGET_ATR_MULT;
      if (stop >= bar.close) return null;
      return buildSignal({
        context,
        side: "long",
        stop,
        target,
        confidence: scaleConfidence(first30MinReturn),
        first30MinReturn,
      });
    }

    if (first30MinReturn < -RETURN_THRESHOLD) {
      // Downside momentum → short
      const stop = bar.close + atr * STOP_ATR_MULT;
      const target = bar.close - atr * TARGET_ATR_MULT;
      if (stop <= bar.close) return null;
      return buildSignal({
        context,
        side: "short",
        stop,
        target,
        confidence: scaleConfidence(Math.abs(first30MinReturn)),
        first30MinReturn,
      });
    }

    return null;
  }
}
