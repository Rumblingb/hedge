import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/**
 * Regime-Locked Momentum Strategy
 *
 * Only fires when three macro conditions align:
 * 1. HMM regime = "trending" (momentum works in trends, not chop)
 * 2. COT dealers NOT fading (positioning aligned with trade direction)
 * 3. Session: RTH morning kill zone (8:30-10:30 CT) — highest volume
 *
 * Signal: Simple 20-bar momentum — if close > SMA(20) by 0.5×ATR → long,
 * if close < SMA(20) by 0.5×ATR → short.
 *
 * This is the highest-filtered strategy in the system — fires rarely but
 * each signal has three-layer macro confirmation.
 *
 * Symbols: ES, NQ (best HMM coverage, deepest COT data)
 */

const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const STRATEGY_ID = "regime-locked-momentum";
const PATTERN = "regime-locked-momentum";

const MOMENTUM_BARS = 20;
const MOMENTUM_ATR_MULTIPLE = 0.5;
const BASE_CONFIDENCE = 0.55;
const MAX_CONFIDENCE = 0.70;

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  sma: number;
  atr: number;
  hmmRegime?: string;
  cotZ?: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, sma, atr, hmmRegime, cotZ } = args;
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
    maxHoldMinutes: 45,
    meta: {
      pattern: PATTERN,
      sma: Math.round(sma * 100) / 100,
      atr: Math.round(atr * 100) / 100,
      ...(hmmRegime ? { hmmRegime } : {}),
      ...(cotZ !== undefined ? { cotDealerZ52: Math.round(cotZ * 100) / 100 } : {}),
    },
  };
}

export class RegimeLockedMomentumStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Regime-locked momentum — only fires when HMM=trending, COT aligned, and in RTH kill zone. " +
    "SMA(20) crossover with 0.5×ATR confirmation. ES, NQ only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // ── Symbol gate ───────────────────────────────────────────────────
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;

    // ── Session gate: only RTH morning (08:30-10:30 CT) ───────────────
    const bar = context.bar;
    const barHour = new Date(bar.ts).getUTCHours();
    const barMin = new Date(bar.ts).getUTCMinutes();
    // CT = UTC-5 (standard) or UTC-6 (daylight). Approximate: UTC 13:30-15:30 ≈ CT 08:30-10:30
    const barCtHour = barHour >= 5 ? barHour - 5 : barHour + 19;
    if (barCtHour < 8 || (barCtHour === 10 && barMin > 30) || barCtHour > 10) return null;

    // ── Need enough history ───────────────────────────────────────────
    const history = context.history;
    if (history.length < MOMENTUM_BARS + 1) return null;

    // ── Session gate: don't fire late in session ──────────────────────
    const sessionBars = context.sessionHistory;
    if (sessionBars.length > 60) return null; // ~first hour only

    // ── Regime gate: must be trending ─────────────────────────────────
    const hmmRegime = context.macro?.hmmRegime;
    if (hmmRegime !== "trending") return null;

    // ── ATR ──────────────────────────────────────────────────────────
    const atr = averageTrueRange(history, 14);
    if (atr <= 0) return null;

    // ── SMA(20) ──────────────────────────────────────────────────────
    let sma = 0;
    const smaSlice = history.slice(-MOMENTUM_BARS);
    for (const b of smaSlice) sma += b.close;
    sma /= MOMENTUM_BARS;

    // ── Momentum signal ──────────────────────────────────────────────
    const deviation = bar.close - sma;
    const absDev = Math.abs(deviation);

    if (absDev < MOMENTUM_ATR_MULTIPLE * atr) return null;

    const side: TradeSide = deviation > 0 ? "long" : "short";

    // ── COT gate: dealer positioning must be aligned ─────────────────
    const cotZ = context.macro?.cotDealerZ52;
    if (side === "long" && cotZ !== undefined && cotZ < 0) {
      // Dealers net short — don't long against them in trending regime
      return null;
    }
    if (side === "short" && cotZ !== undefined && cotZ > 0) {
      // Dealers net long — don't short against them
      return null;
    }

    // ── One signal per day ────────────────────────────────────────────
    if (context.dailyTradeCount > 0) return null;

    // ── Stop/Target ──────────────────────────────────────────────────
    let stop: number;
    let target: number;
    if (side === "long") {
      stop = bar.close - atr * 1.0;
      target = bar.close + atr * 1.5;
    } else {
      stop = bar.close + atr * 1.0;
      target = bar.close - atr * 1.5;
    }

    if (side === "long" && (stop >= bar.close || target <= bar.close)) return null;
    if (side === "short" && (stop <= bar.close || target >= bar.close)) return null;

    // ── Confidence: regime-aligned bonus ──────────────────────────────
    let confidence = BASE_CONFIDENCE;
    // Stronger momentum → higher confidence
    const momStrength = absDev / atr;
    confidence += Math.min((momStrength - MOMENTUM_ATR_MULTIPLE) * 0.1, 0.10);
    // COT aligned → bonus
    if (cotZ !== undefined) {
      if ((side === "long" && cotZ > 0) || (side === "short" && cotZ < 0)) {
        confidence += 0.05;
      }
    }
    confidence = Math.round(Math.min(confidence, MAX_CONFIDENCE) * 100) / 100;

    return buildSignal({
      context,
      side,
      stop,
      target,
      confidence,
      sma,
      atr,
      hmmRegime,
      cotZ,
    });
  }
}
