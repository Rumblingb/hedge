import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * Opening Range Breakout Strategy (Zarattini SSRN)
 *
 * Uses the first N bars of a trading session to define an opening range
 * (range_high = max high, range_low = min low). Subsequent bars that break
 * out of this range with above-average volume trigger directional signals.
 *
 * Key parameters (from Rust param sweep optimization on NQ 15m/30m):
 * - RANGE_WINDOW: 12 bars (rw=12 — one of the 3 tied winners: rw=8/10/12)
 * - VOL_THRESHOLD: 1.3× average volume (vt=1.3 — best in all sweeps)
 * - EXIT_OFFSET: historically optimal 8-bar hold, implemented via ATR stops
 *
 * Rust param_sweep results (NQ):
 * - 15m: 60.6% WR, +385.21R total (rw=8/10/12, vt=1.3, eo=8) — best edge in portfolio
 * - 30m: 59.6% WR, +280.94R total (rw=8, vt=1.3, eo=8)
 *
 * Older full-sample/parameter-sweep rows looked positive on multiple
 * timeframes. Current promotion is stricter: purged OOS, walk-forward,
 * cost/slippage, broker/current parity, and daily approval must clear before
 * this becomes a demo/live candidate. Research-only until those gates clear.
 *
 * Targets: NQ, ES
 * MaxHold: capped at 120 min (HARD_GUARDRAIL_BOUNDS.maxHoldMinutes) so signals
 * survive the guardrail gate. Breakouts fire only inside the first 2h of the
 * 08:30 CT session, matching the prop-firm ORB window. One signal per session.
 */

const RANGE_WINDOW = 12;
const VOL_THRESHOLD = 1.3;
const STOP_ATR_MULTIPLIER = 1.5;
const TARGET_ATR_MULTIPLIER = 3.0;
const MAX_HOLD_MINUTES = 120;
const SESSION_WINDOW_START = 15; // earliest bar (min after 08:30 CT) to consider breakout
const SESSION_WINDOW_END = 120; // latest bar (min after 08:30 CT) to consider breakout
const TARGET_SYMBOLS = new Set(["ES", "NQ"]);

function avgVolume(bars: Bar[], window: number): number {
  if (bars.length < window) return 0;
  const slice = bars.slice(-window);
  return slice.reduce((sum, b) => sum + b.volume, 0) / window;
}

function computeOpeningRange(sessionBars: Bar[], sessionStartCt: string): { rangeHigh: number; rangeLow: number; rangeEndIdx: number } | null {
  if (sessionBars.length < RANGE_WINDOW) return null;
  // Anchor the opening range to the FIRST RANGE_WINDOW bars AFTER the market open
  // (08:30 CT), not the first bars of the calendar day (which start overnight).
  const window = getMarketSessionWindow(sessionBars[0]?.symbol ?? "NQ", sessionStartCt);
  const openMin = minutesFromCtTime(sessionBars[0]?.ts ?? "1970-01-01T00:00:00Z", window.startCt);
  let startIdx = 0;
  for (let i = 0; i < sessionBars.length; i += 1) {
    const m = minutesFromCtTime(sessionBars[i].ts, window.startCt) - openMin;
    if (m >= 0) {
      startIdx = i;
      break;
    }
  }
  const openingBars = sessionBars.slice(startIdx, startIdx + RANGE_WINDOW);
  if (openingBars.length < RANGE_WINDOW) return null;
  let rangeHigh = -Infinity;
  let rangeLow = Infinity;
  for (const b of openingBars) {
    if (b.high > rangeHigh) rangeHigh = b.high;
    if (b.low < rangeLow) rangeLow = b.low;
  }
  // Only valid if the range completed before the current bar fires
  const rangeEndIdx = startIdx + RANGE_WINDOW - 1;
  if (rangeHigh <= rangeLow) return null;
  return { rangeHigh, rangeLow, rangeEndIdx };
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  entry: number;
  stop: number;
  target: number;
  atr: number;
  rangeHigh: number;
  rangeLow: number;
}): StrategySignal | null {
  const { context, side, entry, stop, target, atr, rangeHigh, rangeLow } = args;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  // Confidence: higher for cleaner breakouts (bigger bar, higher vol ratio)
  const vol = context.bar.volume;
  const avgVol = avgVolume(context.history, 10);
  const volRatio = avgVol > 0 ? Math.min(vol / avgVol / VOL_THRESHOLD, 3.0) : 1.0;
  const barRange = context.bar.high - context.bar.low;
  const rangeRatio = atr > 0 ? Math.min(barRange / atr, 3.0) : 1.0;
  const confidence = Math.min(0.4 + volRatio * 0.1 + rangeRatio * 0.1, 0.85);
  return {
    symbol: context.symbol,
    strategyId: "orb-breakout",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: MAX_HOLD_MINUTES,
    meta: {
      pattern: "orb-breakout",
      rangeHigh: Math.round(rangeHigh * 100) / 100,
      rangeLow: Math.round(rangeLow * 100) / 100,
      rangeRatio: Math.round(rangeRatio * 100) / 100,
      volRatio: Math.round(volRatio * 100) / 100,
      atr: Math.round(atr * 100) / 100,
      researchOnly: true,
    },
  };
}

export class OrbBreakoutStrategy implements Strategy {
  public readonly id = "orb-breakout";
  public readonly description =
    "Opening Range Breakout: trades breakouts from the first 12 bars' high/low range with volume >1.3x avg. ES/NQ only, one signal per session.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Only ES and NQ
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;
    if (!isIndexSymbol(context.symbol)) return null;

    // Need session history for opening range
    if (!context.sessionHistory || context.sessionHistory.length < RANGE_WINDOW) return null;

    // One signal per session
    if (context.dailyTradeCount > 0) return null;

    // Session-window gate: only fire breakouts inside the first SESSION_WINDOW_END
    // minutes after the market open (08:30 CT). Firing at arbitrary overnight/mid-session
    // bars gets rejected by the guardrails (entry outside session window / flat cutoff).
    const barIntervalMinutes = inferBarIntervalMinutes(
      context.history[context.history.length - 1]?.ts,
      context.bar.ts
    );
    const dailyLike = barIntervalMinutes >= 720;
    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (!dailyLike && (sessionMinute < SESSION_WINDOW_START || sessionMinute > SESSION_WINDOW_END)) {
      return null;
    }

    // Compute opening range anchored to the market open (08:30 CT)
    const range = computeOpeningRange(context.sessionHistory, context.config.guardrails.sessionStartCt);
    if (!range) return null;

    // Must be past the opening range window (not inside it, and the range must be complete)
    const barIndex = context.sessionHistory.length - 1; // current bar is last in sessionHistory
    if (barIndex <= range.rangeEndIdx) return null;

    const { rangeHigh, rangeLow } = range;

    // Volume check
    const vol = context.bar.volume;
    const avgVol = avgVolume(context.history, 10);
    if (avgVol <= 0) return null;
    if (vol < avgVol * VOL_THRESHOLD) return null;

    // ATR for stop/target sizing (session bars)
    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    const entry = context.bar.close;
    const sideNum = context.bar.close > rangeHigh ? 1 : context.bar.close < rangeLow ? -1 : 0;

    if (sideNum === 0) return null; // inside range — no breakout

    if (sideNum > 0) {
      // LONG breakout: close above range high
      const stop = entry - STOP_ATR_MULTIPLIER * atr;
      const target = entry + TARGET_ATR_MULTIPLIER * atr;
      return buildSignal({ context, side: "long", entry, stop, target, atr, rangeHigh, rangeLow });
    } else {
      // SHORT breakout: close below range low
      const stop = entry + STOP_ATR_MULTIPLIER * atr;
      const target = entry - TARGET_ATR_MULTIPLIER * atr;
      return buildSignal({ context, side: "short", entry, stop, target, atr, rangeHigh, rangeLow });
    }
  }
}
