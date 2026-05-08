import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { chicagoDateKey } from "../utils/time.js";

/**
 * Gap Fade with Regime & COT Filter
 *
 * Fades overnight gaps when macro conditions support mean-reversion:
 * - HMM regime must be "range-chop" or "low-vol" (trending markets don't fade)
 * - COT dealer positioning must not be extreme against the fade direction
 *
 * Signal logic:
 * 1. Compute overnight gap: bar.open - previous session close
 * 2. Find prior close via sessionHistory with different chicagoDateKey
 * 3. Fire if gapPct > 0.5% AND gap >= 1.0*ATR
 * 4. Target: 50% gap fill. Stop: 1.0*ATR beyond gap extreme
 * 5. Confidence: 0.50–0.60 based on gap magnitude and regime alignment
 * 6. Contracts: 1, maxHoldMinutes: 120
 *
 * Symbols: ES, NQ, CL, GC
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ", "CL", "GC"]);
const STRATEGY_ID = "gap-fade-regime";
const PATTERN = "overnight-gap-fade";

// Regime: only fade in mean-reverting / quiet conditions
const FADE_REGIMES = new Set(["range-chop", "low-vol"]);

// Gap thresholds
const MIN_GAP_PCT = 0.005; // 0.5%
const MIN_GAP_ATR_MULTIPLE = 1.0;

// COT extreme thresholds
const COT_EXTREME_SHORT = -1.0; // Dealers net short — don't short into this
const COT_EXTREME_LONG = 1.0;   // Dealers net long — don't long into this

// Confidence range
const BASE_CONFIDENCE = 0.50;
const MAX_CONFIDENCE = 0.60;

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  overnightGap: number;
  gapPct: number;
  priorClose: number;
  atr: number;
  hmmRegime?: string;
  cotDealerZ52?: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, overnightGap, gapPct, priorClose, atr, hmmRegime, cotDealerZ52 } = args;
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
    maxHoldMinutes: 120,
    meta: {
      pattern: PATTERN,
      overnightGap: Math.round(overnightGap * 100) / 100,
      gapPct: Math.round(gapPct * 10000) / 100, // basis points
      priorClose: Math.round(priorClose * 100) / 100,
      atr: Math.round(atr * 100) / 100,
      ...(hmmRegime ? { hmmRegime } : {}),
      ...(cotDealerZ52 !== undefined ? { cotDealerZ52: Math.round(cotDealerZ52 * 100) / 100 } : {}),
    },
  };
}

/**
 * Find the closing price from a prior session (different chicagoDateKey).
 * Searches sessionHistory for the last bar with a different date key.
 */
function findPriorSessionClose(bar: Bar, allHistory: Bar[]): number | null {
  const todayKey = chicagoDateKey(bar.ts);

  // Walk backwards through allHistory to find last bar from a prior session
  for (let i = allHistory.length - 1; i >= 0; i--) {
    const b = allHistory[i]!;
    if (chicagoDateKey(b.ts) !== todayKey) {
      return b.close;
    }
  }

  return null;
}

export class GapFadeRegimeStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Overnight gap fade gated by HMM regime (range-chop/low-vol only) and COT dealer positioning. " +
    "Fades gaps ≥0.5% and ≥1.0×ATR toward 50% fill. ES, NQ, CL, GC.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // ── Symbol gate ───────────────────────────────────────────────────
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    // ── Session open gate: only fire on first 2 bars of session ─────
    // Overnight gap is only meaningful at session open
    const sessionBars = context.sessionHistory;
    if (sessionBars.length > 2) return null;

    const bar = context.bar;

    // ── Prior session close ───────────────────────────────────────────
    // At session open, history's last bar is prior session close
    const history = context.history;
    if (history.length < 2) return null;
    const priorClose = history[history.length - 2]!.close;
    if (priorClose <= 0) return null;

    // ── Overnight gap ─────────────────────────────────────────────────
    const overnightGap = bar.open - priorClose;
    const overnightGapAbs = Math.abs(overnightGap);

    // ── Gap % and magnitude check ─────────────────────────────────────
    const gapPct = overnightGapAbs / priorClose;
    if (gapPct < MIN_GAP_PCT) return null;

    // ── ATR ────────────────────────────────────────────────────────────
    const atr = averageTrueRange(context.history, 14);
    if (atr <= 0) return null;

    if (overnightGapAbs < MIN_GAP_ATR_MULTIPLE * atr) return null;

    // ── HMM regime gate: only fade in range-chop or low-vol ───────────
    const hmmRegime = context.macro?.hmmRegime;
    if (hmmRegime && !FADE_REGIMES.has(hmmRegime)) {
      // trending or high-vol — don't fade
      return null;
    }

    // ── Direction: fade the gap ────────────────────────────────────────
    // gap up → short, gap down → long
    const side: TradeSide = overnightGap > 0 ? "short" : "long";

    // ── COT gate: dealer positioning must not be extreme against fade ──
    const cotDealerZ52 = context.macro?.cotDealerZ52;
    if (cotDealerZ52 !== undefined) {
      if (side === "short" && cotDealerZ52 < COT_EXTREME_SHORT) {
        // Dealers net short — fading a gap-up (shorting) is dangerous
        return null;
      }
      if (side === "long" && cotDealerZ52 > COT_EXTREME_LONG) {
        // Dealers net long — fading a gap-down (longing) is dangerous
        return null;
      }
    }

    // ── Stop: 1.0×ATR beyond gap extreme ──────────────────────────────
    // gap extreme = the open (which is the extreme end of the gap)
    let stop: number;
    let target: number;

    if (side === "short") {
      // Gap up: extreme is bar.open (high side)
      stop = bar.open + atr * 1.0;
      // Target: 50% of gap fill — half way back to priorClose
      target = priorClose + 0.5 * overnightGapAbs;
    } else {
      // Gap down: extreme is bar.open (low side)
      stop = bar.open - atr * 1.0;
      // Target: 50% of gap fill — half way back to priorClose
      target = priorClose - 0.5 * overnightGapAbs;
    }

    // Validate stop is on the correct side of entry
    if (side === "short" && stop <= bar.close) return null;
    if (side === "long" && stop >= bar.close) return null;

    // ── Confidence: 0.50–0.60 based on gap magnitude and regime ────────
    // Higher gap → higher confidence (mean-reversion more likely)
    // Regime aligned → boost
    let confidence = BASE_CONFIDENCE;

    // Gap magnitude bonus: scale with gap size relative to ATR
    // gap/ATR of 1.0 → +0.0, gap/ATR of 3.0+ → +0.05
    const gapAtrRatio = overnightGapAbs / atr;
    const magnitudeBonus = Math.min((gapAtrRatio - 1.0) / 40, 0.05); // max 0.05
    confidence += magnitudeBonus;

    // Regime alignment bonus
    if (hmmRegime && FADE_REGIMES.has(hmmRegime)) {
      confidence += 0.05;
    }

    confidence = Math.min(confidence, MAX_CONFIDENCE);
    confidence = Math.max(confidence, BASE_CONFIDENCE);
    confidence = Math.round(confidence * 100) / 100;

    return buildSignal({
      context,
      side,
      stop,
      target,
      confidence,
      overnightGap,
      gapPct,
      priorClose,
      atr,
      hmmRegime,
      cotDealerZ52,
    });
  }
}
