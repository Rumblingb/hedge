import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { chicagoDateKey, minutesFromCtTime } from "../utils/time.js";

/**
 * Opening Stop Hunt Strategy
 *
 * In the first 5 bars of RTH (8:30-8:35 AM CT), algorithms run stops at obvious levels.
 * If a bar sweeps the prior session high/low but closes BACK inside the prior range,
 * it confirms the sweep was a hunt — not a genuine breakout.
 *
 * - Sweep of prior high + close back inside → short (fake breakout)
 * - Sweep of prior low + close back inside → long (fake breakdown)
 * - Stop: 0.5 ATR beyond the sweep extreme
 * - Target: current session VWAP (price tends to return mid-session)
 * - High-confidence pattern (0.64), 2 contracts, 30-min max hold
 * - ES and NQ only
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ", "GC"]);

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  sweepDirection: string;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, sweepDirection } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol,
    strategyId: "opening-stop-hunt",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 30,
    meta: { pattern: "opening-stop-hunt", sweepDirection },
  };
}

function computeSessionVwap(bars: Bar[]): number {
  if (bars.length === 0) return 0;
  let sumCv = 0;
  let sumV = 0;
  for (const b of bars) {
    sumCv += b.close * b.volume;
    sumV += b.volume;
  }
  return sumV > 0 ? sumCv / sumV : bars[bars.length - 1]!.close;
}

export class OpeningStopHuntStrategy implements Strategy {
  public readonly id = "opening-stop-hunt";
  public readonly description =
    "Opening Stop Hunt: first 5 bars sweep prior session high/low that closes back inside — fade the fake breakout/breakdown. ES/NQ only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Only ES and NQ
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    // Only in first 30 bars of session (session minute 0-30 = full kill zone)
    const sessionWindow = getMarketSessionWindow(
      context.symbol,
      context.config.guardrails.sessionStartCt,
    );
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 0 || sessionMinute > 30) return null;

    const sessionBars = context.sessionHistory;
    if (sessionBars.length < 1) return null;

    // Compute prior session high/low from context.history (non-today bars)
    const todayKey = chicagoDateKey(context.bar.ts);
    const priorBars = context.history.filter((b) => chicagoDateKey(b.ts) !== todayKey);

    let priorHigh: number;
    let priorLow: number;

    if (priorBars.length > 0) {
      priorHigh = Math.max(...priorBars.map((b) => b.high));
      priorLow = Math.min(...priorBars.map((b) => b.low));
    } else {
      // Fall back to first bar of the session as reference
      const firstBar = sessionBars[0]!;
      priorHigh = firstBar.high;
      priorLow = firstBar.low;
    }

    const priorRange = priorHigh - priorLow;
    if (priorRange <= 0) return null;

    // ATR for stop sizing (0.5 ATR beyond sweep extreme)
    const atr = averageTrueRange([...context.history.slice(-20), context.bar], 14);
    if (atr <= 0) return null;

    const bar = context.bar;

    // Detect sweep: high > prior high OR low < prior low
    // Confirmation: close must be BACK INSIDE prior session range
    const sweptHigh = bar.high > priorHigh && bar.close < priorHigh;
    const sweptLow = bar.low < priorLow && bar.close > priorLow;

    // Compute current session VWAP as target (mid-session proxy)
    const vwap = computeSessionVwap(sessionBars);

    if (sweptHigh) {
      // Fake breakout → short
      const stop = bar.high + atr * 0.5;
      if (stop <= bar.close) return null;
      return buildSignal({
        context,
        side: "short",
        stop,
        target: vwap,
        confidence: 0.64,
        sweepDirection: "high-sweep",
      });
    }

    if (sweptLow) {
      // Fake breakdown → long
      const stop = bar.low - atr * 0.5;
      if (stop >= bar.close) return null;
      return buildSignal({
        context,
        side: "long",
        stop,
        target: vwap,
        confidence: 0.64,
        sweepDirection: "low-sweep",
      });
    }

    return null;
  }
}
