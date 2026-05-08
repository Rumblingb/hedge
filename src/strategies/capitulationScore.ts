/**
 * Capitulation Score Strategy
 *
 * "Buy when everyone is selling." Combines 5 independent indicators
 * into a capitulation score (0–5). When score >= 3, enter aggressive
 * mean-reversion LONG. Fires rarely (6-12 times/year) but each signal
 * is high-quality.
 *
 * Score = sum of 5 binary indicators (0 or 1 each):
 *   1. COT dealer z52 < -1.5  (dealers extremely short → covering soon → price floor)
 *   2. Volatility expansion: current ATR > 2.5× average ATR (VIX > 30 proxy)
 *   3. Volume capitulation: volume > 3× 20-bar avg AND bar is red (close < open)
 *   4. Price extreme: close > 3 ATR below 20-bar SMA (oversold)
 *   5. HMM regime = high-vol (macro context, if available)
 *
 * Thresholds:
 *   Score 0–2 → no signal
 *   Score 3   → 1 contract, confidence 0.65, maxHold 30 min
 *   Score 4–5 → 2 contracts, confidence 0.75, maxHold 60 min
 *
 * Trade direction: Always LONG (capitulation = sellers exhausted = buy).
 * Stop: 2 ATR (wider than normal — capitulation is volatile).
 * Target: 3R (mean reversion after panic often retraces 50–80%).
 * Target instruments: ES, NQ only.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

// ── Constants ──────────────────────────────────────────────────────────
const TARGET_SYMBOLS = new Set(["ES", "NQ"]);
const FAST_ATR_PERIOD = 14;
const SLOW_ATR_PERIOD = 100; // proxy for "20-day average" ATR
const ATR_EXPANSION_THRESHOLD = 2.5;
const VOLUME_LOOKBACK = 20;
const VOLUME_CAPITULATION_MULTIPLIER = 3;
const SMA_PERIOD = 20;
const OVERSOLD_ATR_MULTIPLE = 3;
const STOP_ATR_MULTIPLE = 2;
const TARGET_R_MULTIPLE = 3;
const COT_EXTREME_THRESHOLD = -1.5;

// ── Helpers ────────────────────────────────────────────────────────────

/** Simple moving average of the last `period` values. */
function sma(values: number[], period: number): number {
  if (values.length < period) return 0;
  const window = values.slice(-period);
  return window.reduce((sum, value) => sum + value, 0) / window.length;
}

/** Average volume over the last `period` bars. */
function avgVolume(history: Bar[], period: number): number {
  if (history.length < period) return 0;
  const window = history.slice(-period);
  return window.reduce((sum, bar) => sum + bar.volume, 0) / window.length;
}

// ── Signal builder ─────────────────────────────────────────────────────

function buildSignal(args: {
  context: StrategyContext;
  score: number;
  atr: number;
}): StrategySignal | null {
  const { context, score, atr } = args;
  const entry = context.bar.close;
  const side: TradeSide = "long";

  // Wider stop for capitulation volatility
  const stop = entry - atr * STOP_ATR_MULTIPLE;
  const risk = entry - stop;
  if (risk <= 0) return null;

  // 3R target — mean reversion after panic
  const target = entry + risk * TARGET_R_MULTIPLE;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  const isStrong = score >= 4;

  const meta: Record<string, string | number | boolean> = {
    score,
    atr: Math.round(atr * 100) / 100,
  };

  if (context.macro?.cotDealerZ52 !== undefined) {
    meta.cotDealerZ52 = Math.round(context.macro.cotDealerZ52 * 100) / 100;
  }
  if (context.macro?.hmmRegime) {
    meta.hmmRegime = context.macro.hmmRegime;
  }

  return {
    symbol: context.symbol,
    strategyId: "capitulation-score",
    side,
    entry,
    stop,
    target,
    rr,
    confidence: isStrong ? 0.75 : 0.65,
    contracts: isStrong ? 2 : 1,
    maxHoldMinutes: isStrong ? 60 : 30,
    meta,
  };
}

// ── Strategy ───────────────────────────────────────────────────────────

export class CapitulationScoreStrategy implements Strategy {
  public readonly id = "capitulation-score";
  public readonly description =
    "Capitulation score (0–5): COT extreme + vol expansion + volume panic + " +
    "price oversold + HMM high-vol. Enter LONG when 3+ signals fire. " +
    "Rare (6–12/yr) but high-quality mean-reversion. ES/NQ only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // ── Symbol gate: ES / NQ only ──────────────────────────────────
    if (!TARGET_SYMBOLS.has(context.symbol)) return null;

    // ── Data requirement ───────────────────────────────────────────
    const minBars = Math.max(FAST_ATR_PERIOD, SLOW_ATR_PERIOD, SMA_PERIOD, VOLUME_LOOKBACK);
    if (context.history.length < minBars) return null;

    // ── ATR baseline ───────────────────────────────────────────────
    const atr = averageTrueRange(context.history, FAST_ATR_PERIOD);
    if (atr <= 0) return null;

    let score = 0;

    // ── Indicator 1: COT dealer z52 < -1.5 ─────────────────────────
    // Dealers extremely short → position covering soon → price floor.
    const cotZ = context.macro?.cotDealerZ52;
    if (cotZ !== undefined && cotZ < COT_EXTREME_THRESHOLD) {
      score += 1;
    }

    // ── Indicator 2: Volatility expansion (VIX > 30 proxy) ─────────
    // Current ATR > 2.5× average ATR → fear elevated.
    const slowAtr = averageTrueRange(context.history, SLOW_ATR_PERIOD);
    if (slowAtr > 0 && atr > slowAtr * ATR_EXPANSION_THRESHOLD) {
      score += 1;
    }

    // ── Indicator 3: Volume capitulation ───────────────────────────
    // Volume > 3× 20-bar average AND bar is red (close < open).
    const avgVol = avgVolume(context.history, VOLUME_LOOKBACK);
    const isRed = context.bar.close < context.bar.open;
    if (avgVol > 0 && context.bar.volume > avgVol * VOLUME_CAPITULATION_MULTIPLIER && isRed) {
      score += 1;
    }

    // ── Indicator 4: Price extreme (oversold) ──────────────────────
    // Close > 3 ATR below 20-bar SMA.
    const closes = context.history.map((bar) => bar.close);
    const sma20 = sma(closes, SMA_PERIOD);
    if (sma20 > 0 && (sma20 - context.bar.close) > atr * OVERSOLD_ATR_MULTIPLE) {
      score += 1;
    }

    // ── Indicator 5: HMM regime = high-vol ─────────────────────────
    if (context.macro?.hmmRegime === "high-vol") {
      score += 1;
    }

    // ── Gate: need at least 3 out of 5 ─────────────────────────────
    if (score < 3) return null;

    return buildSignal({ context, score, atr });
  }
}
