/**
 * Options Selling Framework Strategy
 *
 * Meta-strategy that determines WHEN to sell options on ES futures
 * based on HMM regime, volatility proxy (ATR ratio), COT positioning,
 * and calendar events. Does not require real options data — uses
 * futures-level signals to time option-selling entries.
 *
 * Each signal emits a meta.subSignal indicating the option type:
 *   "sell-straddle", "sell-itm-put", "sell-itm-call", "sell-0dte-straddle"
 *
 * Four sub-strategies in one file:
 *
 * Strategy A: ATM Straddle Sell (Range-Chop + Elevated Vol)
 *   When:  HMM=range-chop + ATR(14) > 1.3x ATR(100)
 *   Signal: "sell-straddle" — neutral (no directional bias), confidence 0.60
 *   Stop:  2 ATR (wide — straddle needs room)
 *   Target: 1.5R
 *   Max hold: 120 min
 *
 * Strategy B: ITM Put Sell — Synthetic Bullish (COT bullish + Range-Chop)
 *   When:  COT dealer z52 < -1.0 (dealers covering = floor) + HMM=range-chop
 *   Signal: "sell-itm-put" — LONG bias, confidence 0.62
 *   Stop:  1.5 ATR
 *   Target: 2R
 *
 * Strategy C: ITM Call Sell — Synthetic Bearish (COT bearish + Range-Chop)
 *   When:  COT dealer z52 > +1.0 (dealers distributing = ceiling) + HMM=range-chop
 *   Signal: "sell-itm-call" — SHORT bias, confidence 0.62
 *   Stop:  1.5 ATR
 *   Target: 2R
 *
 * Strategy D: 0DTE Theta Farm (Elevated Vol + Range-Chop + No Events)
 *   When:  ATR(14) > 1.2x ATR(100) + HMM=range-chop + no macro events
 *          (avoid 8:30–9:00 CT for macro data releases)
 *   Signal: "sell-0dte-straddle" — confidence 0.58
 *   Max hold: 45 min
 *
 * Safety gate: NEVER sell options when:
 *   - HMM = high-vol (market can move 4–5x normal)
 *   - VIX proxy > 2.0x ATR(100) (extreme vol — ATR(14) / ATR(100) > 2.0)
 *   - capitulationScore >= 3 (capitulation destroys option sellers)
 *
 * Target: ES only (most liquid options)
 */
import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { minutesSinceMidnightCt } from "../utils/time.js";

// ── Constants ──────────────────────────────────────────────────────────

const TARGET_SYMBOLS = new Set(["ES"]);
const STRATEGY_ID = "options-selling-framework";

// ATR periods
const FAST_ATR = 14;   // 1-hour-ish on 5-min bars
const SLOW_ATR = 100;  // ~1-week proxy for baseline vol

// Strategy A: ATM Straddle thresholds
const STRADDLE_ATR_RATIO = 1.3;       // ATR(14) > 1.3x ATR(100)
const STRADDLE_STOP_ATR = 2.0;        // 2 ATR stop
const STRADDLE_TARGET_R = 1.5;        // 1.5R target
const STRADDLE_MAX_HOLD = 120;        // 120 min
const STRADDLE_CONFIDENCE = 0.60;

// Strategy B: ITM Put thresholds
const PUT_COT_THRESHOLD = -1.0;       // COT dealer z52 < -1.0
const PUT_STOP_ATR = 1.5;
const PUT_TARGET_R = 2.0;
const PUT_MAX_HOLD = 90;
const PUT_CONFIDENCE = 0.62;

// Strategy C: ITM Call thresholds
const CALL_COT_THRESHOLD = 1.0;       // COT dealer z52 > +1.0
const CALL_STOP_ATR = 1.5;
const CALL_TARGET_R = 2.0;
const CALL_MAX_HOLD = 90;
const CALL_CONFIDENCE = 0.62;

// Strategy D: 0DTE Theta Farm thresholds
const THETA_ATR_RATIO = 1.2;         // ATR(14) > 1.2x ATR(100)
const THETA_STOP_ATR = 1.5;
const THETA_TARGET_R = 1.5;
const THETA_MAX_HOLD = 45;
const THETA_CONFIDENCE = 0.58;

// Macro event window: avoid 8:30–9:00 CT
const MACRO_EVENT_START_CT_MINUTES = 8 * 60 + 30;  // 510
const MACRO_EVENT_END_CT_MINUTES = 9 * 60;          // 540

// Safety gate thresholds
const SAFETY_ATR_EXTREME_RATIO = 2.0;  // ATR(14) > 2.0x ATR(100) = extreme vol
const SAFETY_CAPITULATION_MIN = 3;     // capitulationScore >= 3 = no selling

// ── Signal builder ─────────────────────────────────────────────────────

function buildSignal(args: {
  context: StrategyContext;
  subSignal: string;
  side: TradeSide;
  stopAtrMultiple: number;
  targetRMultiple: number;
  atr: number;
  confidence: number;
  maxHoldMinutes: number;
  metaExtras?: Record<string, string | number | boolean>;
}): StrategySignal | null {
  const { context, subSignal, side, stopAtrMultiple, targetRMultiple, atr, confidence, maxHoldMinutes, metaExtras } = args;

  const entry = context.bar.close;
  const risk = atr * stopAtrMultiple;
  if (risk <= 0) return null;

  const stop = side === "long" ? entry - risk : entry + risk;
  const target = side === "long" ? entry + risk * targetRMultiple : entry - risk * targetRMultiple;

  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  const meta: Record<string, string | number | boolean> = {
    subSignal,
    atr: Math.round(atr * 100) / 100,
    ...metaExtras,
  };

  if (context.macro?.hmmRegime) {
    meta.hmmRegime = context.macro.hmmRegime;
  }
  if (context.macro?.cotDealerZ52 !== undefined) {
    meta.cotDealerZ52 = Math.round(context.macro.cotDealerZ52 * 100) / 100;
  }
  if (context.macro?.capitulationScore !== undefined) {
    meta.capitulationScore = context.macro.capitulationScore;
  }

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
    maxHoldMinutes,
    meta,
  };
}

// ── Safety gate ────────────────────────────────────────────────────────

/**
 * Returns true if it is NOT safe to sell options.
 * NEVER sell options when:
 *   - HMM = high-vol
 *   - VIX proxy > 2.0x ATR(100) (ATR(14) / ATR(100) > 2.0)
 *   - capitulationScore >= 3
 */
function isBlockedBySafetyGate(context: StrategyContext, fastAtr: number, slowAtr: number): string[] {
  const reasons: string[] = [];

  // Gate 1: HMM high-vol regime
  if (context.macro?.hmmRegime === "high-vol") {
    reasons.push("hmm-high-vol");
  }

  // Gate 2: Extreme vol — ATR(14) > 2.0x ATR(100)
  if (slowAtr > 0 && fastAtr > slowAtr * SAFETY_ATR_EXTREME_RATIO) {
    reasons.push(`extreme-vol:atr14=${fastAtr.toFixed(2)};atr100=${slowAtr.toFixed(2)};ratio=${(fastAtr / slowAtr).toFixed(2)}`);
  }

  // Gate 3: Capitulation event
  if (context.macro?.capitulationScore !== undefined && context.macro.capitulationScore >= SAFETY_CAPITULATION_MIN) {
    reasons.push(`capitulation:score=${context.macro.capitulationScore}`);
  }

  return reasons;
}

// ── Event window check ─────────────────────────────────────────────────

/**
 * Returns true if the current bar falls in the 8:30–9:00 CT macro event window.
 * Major economic data releases (CPI, NFP, etc.) arrive at 8:30 ET / 7:30 CT.
 * We use 8:30–9:00 CT to give a buffer for the initial reaction.
 */
function inMacroEventWindow(barTs: string): boolean {
  const ctMinutes = minutesSinceMidnightCt(barTs);
  return ctMinutes >= MACRO_EVENT_START_CT_MINUTES && ctMinutes <= MACRO_EVENT_END_CT_MINUTES;
}

// ── Strategy ───────────────────────────────────────────────────────────

export class OptionsSellingFrameworkStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Options selling framework: times option sells (straddles, ITM puts/calls, 0DTE theta farm) " +
    "using HMM regime, COT positioning, ATR vol proxy, and calendar event awareness. " +
    "Safety-gated against high-vol, extreme vol, and capitulation events. ES only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // ── Symbol gate: ES only ──────────────────────────────────────────
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;

    // ── Data requirement ─────────────────────────────────────────────
    const minBars = Math.max(FAST_ATR, SLOW_ATR);
    if (context.history.length < minBars) return null;

    // ── Compute ATR baselines ────────────────────────────────────────
    const fastAtr = averageTrueRange(context.history, FAST_ATR);
    if (fastAtr <= 0) return null;

    const slowAtr = averageTrueRange(context.history, SLOW_ATR);
    if (slowAtr <= 0) return null;

    // ── Safety gate: NEVER sell options when these conditions fire ────
    const safetyBlockReasons = isBlockedBySafetyGate(context, fastAtr, slowAtr);
    if (safetyBlockReasons.length > 0) {
      // Safety gate engaged — explicitly block all signals.
      // We still return null, but log-worthy for debugging.
      if (context.macro?.hmmRegime && safetyBlockReasons.length > 0) {
        // Optional: could log, but for now just return null silently
      }
      return null;
    }

    const isRangeChop = context.macro?.hmmRegime === "range-chop";
    const cotZ = context.macro?.cotDealerZ52;

    // ── Strategy B: ITM Put Sell — Synthetic Bullish ──────────────────
    // COT dealers covering (floor) + range-chop → sell puts, buy underlying
    if (isRangeChop && cotZ !== undefined && cotZ < PUT_COT_THRESHOLD) {
      return buildSignal({
        context,
        subSignal: "sell-itm-put",
        side: "long", // Synthetic bullish: selling puts = bullish on underlying
        stopAtrMultiple: PUT_STOP_ATR,
        targetRMultiple: PUT_TARGET_R,
        atr: fastAtr,
        confidence: PUT_CONFIDENCE,
        maxHoldMinutes: PUT_MAX_HOLD,
        metaExtras: {
          cotDealerZ52: Math.round(cotZ * 100) / 100,
          thesis: "dealers-covering-floor",
        },
      });
    }

    // ── Strategy C: ITM Call Sell — Synthetic Bearish ─────────────────
    // COT dealers distributing (ceiling) + range-chop → sell calls, fade rally
    if (isRangeChop && cotZ !== undefined && cotZ > CALL_COT_THRESHOLD) {
      return buildSignal({
        context,
        subSignal: "sell-itm-call",
        side: "short", // Synthetic bearish: selling calls = bearish on underlying
        stopAtrMultiple: CALL_STOP_ATR,
        targetRMultiple: CALL_TARGET_R,
        atr: fastAtr,
        confidence: CALL_CONFIDENCE,
        maxHoldMinutes: CALL_MAX_HOLD,
        metaExtras: {
          cotDealerZ52: Math.round(cotZ * 100) / 100,
          thesis: "dealers-distributing-ceiling",
        },
      });
    }

    // ── Need range-chop for remaining strategies (A and D) ────────────
    if (!isRangeChop) return null;

    // ── Strategy A: ATM Straddle Sell (Range-Chop + Elevated Vol) ─────
    // Elevated vol in range-chop = expensive options, likely mean-reversion
    const atrRatio = slowAtr > 0 ? fastAtr / slowAtr : 0;

    if (atrRatio >= STRADDLE_ATR_RATIO) {
      return buildSignal({
        context,
        subSignal: "sell-straddle",
        side: "long", // Neutral placeholder — straddle is delta-neutral
        stopAtrMultiple: STRADDLE_STOP_ATR,
        targetRMultiple: STRADDLE_TARGET_R,
        atr: fastAtr,
        confidence: STRADDLE_CONFIDENCE,
        maxHoldMinutes: STRADDLE_MAX_HOLD,
        metaExtras: {
          atrRatio: Math.round(atrRatio * 100) / 100,
          thesis: "elevated-vol-range-chop",
        },
      });
    }

    // ── Strategy D: 0DTE Theta Farm ───────────────────────────────────
    // Elevated vol + range-chop + no macro events → sell 0DTE straddles
    // Avoid 8:30–9:00 CT — macro data releases spike vol unpredictably
    if (atrRatio >= THETA_ATR_RATIO && !inMacroEventWindow(context.bar.ts)) {
      return buildSignal({
        context,
        subSignal: "sell-0dte-straddle",
        side: "long", // Neutral placeholder — straddle is delta-neutral
        stopAtrMultiple: THETA_STOP_ATR,
        targetRMultiple: THETA_TARGET_R,
        atr: fastAtr,
        confidence: THETA_CONFIDENCE,
        maxHoldMinutes: THETA_MAX_HOLD,
        metaExtras: {
          atrRatio: Math.round(atrRatio * 100) / 100,
          thesis: "theta-farm-elevated-vol",
        },
      });
    }

    return null;
  }
}
