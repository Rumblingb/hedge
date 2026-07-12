/**
 * #29 LLM-Guided Evolutionary Strategy Generation
 * Source: Zhang, D. et al. (2025). "LLM-Guided Evolutionary Strategy Generation
 *   for Quantitative Trading." SciSpace Journal Article.
 *
 * Key finding: LLM-GA framework integrating LLMs with genetic algorithms for
 * automated trading strategy generation. Three modules:
 *   1. Signal generator: technical, fundamental, sentiment indicators
 *   2. LLM-enhanced GA core: semantically-aware crossover/mutation
 *   3. Execution module: closed-loop adaptive system
 *
 * Results: AER=12.3%, MDD=35.2% on Chinese stocks 2020-2024.
 * LLM-guided init: +215% starting quality. Semantic crossover: -83.5% invalid.
 *
 * Our implementation for Bill/Hedge:
 * Instead of random signal combination, this strategy uses semantic coherence
 * rules derived from market logic to combine multiple indicators. The "LLM"
 * component is replaced with predefined semantic rules that encode financial
 * domain knowledge about which indicators work together and why.
 *
 * The strategy evaluates three complementary signal families:
 *   - Momentum (trend strength, ADX, MACD)
 *   - Mean-reversion (z-score, RSI, Bollinger)
 *   - Volume/flow (volume ratio, VWAP divergence, delta proxy)
 *
 * Each family produces a sub-signal. The "genetic" combination:
 *   - Crossover: only combine signals that are semantically compatible
 *     (e.g., momentum + volume = good, momentum + mean-reversion = conflict)
 *   - Mutation: slight perturbation of thresholds based on recent performance
 *
 * Market logic: LLM-GA's key insight is that random GA crossover produces
 * nonsensical strategy combinations (83.5% invalid). Semantic constraints
 * from financial domain knowledge are the moat.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";
import { getMarketSessionWindow } from "../utils/sessions.js";

const TARGET_SYMBOLS = ["ES", "NQ", "CL", "GC"];
const SIGNAL_LOOKBACK = 20;
const VOLUME_LOOKBACK = 10;

// === SIGNAL FAMILIES ===

interface SubSignal {
  direction: TradeSide;
  strength: number; // 0-1, how strong the signal is
  family: "momentum" | "mean-reversion" | "volume-flow";
  description: string;
}

/**
 * Family 1: Momentum signals
 * - Trend strength (ADX proxy via directional consistency)
 * - MACD crossover proxy (fast vs slow EMA)
 */
function computeMomentumSignals(history: Bar[]): SubSignal[] {
  const signals: SubSignal[] = [];
  if (history.length < SIGNAL_LOOKBACK) return signals;

  const closes = history.map((b) => b.close);
  const recent = closes.slice(-SIGNAL_LOOKBACK);

  // Trend strength: ratio of directional consistency
  let upBars = 0;
  let downBars = 0;
  for (let i = 1; i < recent.length; i++) {
    if (recent[i]! > recent[i - 1]!) upBars++;
    else if (recent[i]! < recent[i - 1]!) downBars++;
  }
  const dirConsistency = Math.max(upBars, downBars) / Math.max(1, upBars + downBars);

  if (dirConsistency > 0.65 && upBars + downBars >= 8) {
    signals.push({
      direction: upBars > downBars ? "long" : "short",
      strength: dirConsistency,
      family: "momentum",
      description: `trend-consistency=${Math.round(dirConsistency * 100)}%`,
    });
  }

  // MACD proxy: fast EMA (5) vs slow EMA (20)
  const fastEma = ema(recent, 5);
  const slowEma = ema(recent, 20);
  if (fastEma !== null && slowEma !== null && Math.abs(fastEma - slowEma) / slowEma > 0.002) {
    const crossStrength = Math.min(1, Math.abs(fastEma - slowEma) / slowEma * 50);
    signals.push({
      direction: fastEma > slowEma ? "long" : "short",
      strength: crossStrength * 0.7,
      family: "momentum",
      description: `macd-cross=${fastEma > slowEma ? "bullish" : "bearish"}`,
    });
  }

  return signals;
}

/**
 * Family 2: Mean-reversion signals
 * - Z-score from rolling mean
 * - RSI proxy (normalized net change)
 * - Bollinger position
 */
function computeMeanReversionSignals(history: Bar[]): SubSignal[] {
  const signals: SubSignal[] = [];
  if (history.length < SIGNAL_LOOKBACK) return signals;

  const closes = history.map((b) => b.close);
  const recent = closes.slice(-SIGNAL_LOOKBACK);
  const currentPrice = recent[recent.length - 1]!;
  const mean = recent.reduce((a, b) => a + b, 0) / recent.length;
  const variance = recent.reduce((s, v) => s + (v - mean) ** 2, 0) / recent.length;
  const std = Math.sqrt(variance);

  if (std <= 0) return signals;

  // Z-score
  const zScore = (currentPrice - mean) / std;
  const absZ = Math.abs(zScore);

  if (absZ > 1.5) {
    signals.push({
      direction: zScore > 0 ? "short" : "long", // Fade the extreme
      strength: Math.min(1, (absZ - 1.5) / 2),
      family: "mean-reversion",
      description: `zscore=${Math.round(zScore * 100) / 100}`,
    });
  }

  // RSI proxy: normalized sum of up vs down moves
  let upSum = 0;
  let downSum = 0;
  for (let i = 1; i < recent.length; i++) {
    const change = recent[i]! - recent[i - 1]!;
    if (change > 0) upSum += change;
    else downSum += Math.abs(change);
  }
  const rsiProxy = upSum / Math.max(0.0001, upSum + downSum);

  if (rsiProxy > 0.75) {
    signals.push({
      direction: "short",
      strength: (rsiProxy - 0.7) / 0.3,
      family: "mean-reversion",
      description: `rsi-overbought=${Math.round(rsiProxy * 100)}%`,
    });
  } else if (rsiProxy < 0.25) {
    signals.push({
      direction: "long",
      strength: (0.3 - rsiProxy) / 0.3,
      family: "mean-reversion",
      description: `rsi-oversold=${Math.round(rsiProxy * 100)}%`,
    });
  }

  return signals;
}

/**
 * Family 3: Volume/flow signals
 * - Volume ratio (recent vs average)
 * - VWAP divergence proxy
 * - Delta proxy (buy vs sell pressure from OHLCV)
 */
function computeVolumeFlowSignals(history: Bar[], atr: number): SubSignal[] {
  const signals: SubSignal[] = [];
  if (history.length < VOLUME_LOOKBACK + 5) return signals;

  const recent = history.slice(-VOLUME_LOOKBACK);
  const older = history.slice(-VOLUME_LOOKBACK * 2, -VOLUME_LOOKBACK);

  const recentVolAvg = recent.reduce((s, b) => s + b.volume, 0) / recent.length;
  const olderVolAvg = older.reduce((s, b) => s + b.volume, 0) / older.length;

  if (olderVolAvg <= 0) return signals;

  const volRatio = recentVolAvg / olderVolAvg;

  // High volume with directional bias = informed flow
  if (volRatio > 1.5) {
    const recentCloses = recent.map((b) => b.close);
    const priceChange = (recentCloses[recentCloses.length - 1]! - recentCloses[0]!) / recentCloses[0]!;

    if (Math.abs(priceChange) > atr / recent[0]!.close * 0.5) {
      signals.push({
        direction: priceChange > 0 ? "long" : "short",
        strength: Math.min(1, (volRatio - 1.3) / 2),
        family: "volume-flow",
        description: `vol-surge=${Math.round(volRatio * 100) / 100}x trend=${priceChange > 0 ? "up" : "down"}`,
      });
    }
  }

  // Delta proxy: close position within bar range
  const lastBar = recent[recent.length - 1]!;
  const barRange = lastBar.high - lastBar.low;
  if (barRange > 0) {
    const closePosition = (lastBar.close - lastBar.low) / barRange;
    if (closePosition > 0.8 && volRatio > 1.2) {
      signals.push({
        direction: "long",
        strength: 0.6,
        family: "volume-flow",
        description: `buy-pressure=${Math.round(closePosition * 100)}%`,
      });
    } else if (closePosition < 0.2 && volRatio > 1.2) {
      signals.push({
        direction: "short",
        strength: 0.6,
        family: "volume-flow",
        description: `sell-pressure=${Math.round((1 - closePosition) * 100)}%`,
      });
    }
  }

  return signals;
}

// === SEMANTIC COMPATIBILITY RULES ===

/**
 * LLM-inspired semantic compatibility: which signal families can combine.
 * Momentum + Volume-Flow = GOOD (trend confirmed by volume)
 * Momentum + Mean-Reversion = CONFLICT (opposing logics)
 * Mean-Reversion + Volume-Flow = CONDITIONAL (only at extremes)
 * All three together = only if one is dominant
 */
function computeSemanticScore(signals: SubSignal[]): {
  direction: TradeSide | null;
  confidence: number;
  dominatingFamily: string;
} {
  if (signals.length === 0) {
    return { direction: null, confidence: 0, dominatingFamily: "none" };
  }

  // Count signals by direction
  let longSignals = 0;
  let shortSignals = 0;
  let longStrength = 0;
  let shortStrength = 0;

  for (const s of signals) {
    if (s.direction === "long") {
      longSignals++;
      longStrength += s.strength;
    } else {
      shortSignals++;
      shortStrength += s.strength;
    }
  }

  // Determine dominant direction
  const totalStrength = longStrength + shortStrength;
  if (totalStrength <= 0) return { direction: null, confidence: 0, dominatingFamily: "none" };

  const longRatio = longStrength / totalStrength;

  // Need clear directional consensus (>60% one direction)
  if (longRatio > 0.6) {
    // Check for semantic conflicts: momentum + mean-reversion in same direction
    const families = new Set(signals.filter((s) => s.direction === "long").map((s) => s.family));
    const hasMomentum = families.has("momentum");
    const hasMeanRev = families.has("mean-reversion");

    if (hasMomentum && hasMeanRev) {
      // Conflict: momentum and mean-reversion disagree on logic
      // Only proceed if one family is clearly dominant
      const momStrength = signals
        .filter((s) => s.family === "momentum" && s.direction === "long")
        .reduce((a, s) => a + s.strength, 0);
      const mrStrength = signals
        .filter((s) => s.family === "mean-reversion" && s.direction === "long")
        .reduce((a, s) => a + s.strength, 0);

      if (momStrength > mrStrength * 2) {
        return { direction: "long", confidence: 0.55, dominatingFamily: "momentum" };
      }
      if (mrStrength > momStrength * 2) {
        return { direction: "long", confidence: 0.55, dominatingFamily: "mean-reversion" };
      }
      // Too balanced = conflict, skip
      return { direction: null, confidence: 0, dominatingFamily: "conflict" };
    }

    // No conflict: good signal
    const confidence = Math.min(0.75, 0.45 + longStrength * 0.15);
    return {
      direction: "long",
      confidence,
      dominatingFamily: families.values().next().value ?? "mixed",
    };
  } else if (longRatio < 0.4) {
    const families = new Set(signals.filter((s) => s.direction === "short").map((s) => s.family));
    const hasMomentum = families.has("momentum");
    const hasMeanRev = families.has("mean-reversion");

    if (hasMomentum && hasMeanRev) {
      const momStrength = signals
        .filter((s) => s.family === "momentum" && s.direction === "short")
        .reduce((a, s) => a + s.strength, 0);
      const mrStrength = signals
        .filter((s) => s.family === "mean-reversion" && s.direction === "short")
        .reduce((a, s) => a + s.strength, 0);

      if (momStrength > mrStrength * 2) {
        return { direction: "short", confidence: 0.55, dominatingFamily: "momentum" };
      }
      if (mrStrength > momStrength * 2) {
        return { direction: "short", confidence: 0.55, dominatingFamily: "mean-reversion" };
      }
      return { direction: null, confidence: 0, dominatingFamily: "conflict" };
    }

    const confidence = Math.min(0.75, 0.45 + shortStrength * 0.15);
    return {
      direction: "short",
      confidence,
      dominatingFamily: families.values().next().value ?? "mixed",
    };
  }

  // Too balanced between long/short
  return { direction: null, confidence: 0, dominatingFamily: "balanced" };
}

// === UTILS ===

function ema(values: number[], period: number): number | null {
  if (values.length < period) return null;
  const alpha = 2 / (period + 1);
  let ema = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < values.length; i++) {
    ema = alpha * values[i]! + (1 - alpha) * ema;
  }
  return ema;
}

// === STRATEGY ===

export class LlmGaEvolutionaryStrategy implements Strategy {
  public readonly id = "llm-ga-evolutionary";
  public readonly description =
    "LLM-Guided Evolutionary Strategy: combines momentum, mean-reversion, and volume-flow " +
    "signal families using semantic compatibility rules (GA crossover proxy). " +
    "Prevents nonsensical signal combinations via financial domain knowledge. " +
    "Source: Zhang et al. 2025 — LLM-GA for Quantitative Trading.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.includes(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null;

    const sessionWindow = getMarketSessionWindow(
      context.symbol,
      context.config.guardrails.sessionStartCt,
    );
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 15) return null;

    // Internal history
    let history = this.symbolHistory.get(context.symbol) ?? [];
    history = [...history, context.bar];
    if (history.length > 300) history = history.slice(-300);
    this.symbolHistory.set(context.symbol, history);

    if (history.length < SIGNAL_LOOKBACK + 10) return null;

    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    // === EVOLUTIONARY SIGNAL GENERATION ===

    // Generate all sub-signals from three families
    const momentumSignals = computeMomentumSignals(history);
    const meanRevSignals = computeMeanReversionSignals(history);
    const volFlowSignals = computeVolumeFlowSignals(history, atr);

    const allSignals = [...momentumSignals, ...meanRevSignals, ...volFlowSignals];

    // Semantic compatibility scoring (LLM-inspired crossover)
    const { direction, confidence, dominatingFamily } = computeSemanticScore(allSignals);

    if (direction === null || confidence < 0.5) return null;

    // Build trade signal
    const risk = atr * 1.2;
    const targetRr = Math.max(context.config.guardrails.minRr, 2.0);

    const entry = context.bar.close;
    const stop = direction === "long" ? entry - risk : entry + risk;
    const target = direction === "long" ? entry + risk * targetRr : entry - risk * targetRr;

    const rr = calculateRr(entry, stop, target, direction);
    if (rr <= 0) return null;

    // Collect descriptions for meta
    const signalDesc = allSignals
      .filter((s) => s.direction === direction)
      .map((s) => s.description)
      .join("; ");

    return {
      symbol: context.symbol,
      strategyId: "llm-ga-evolutionary",
      side: direction,
      entry,
      stop,
      target,
      rr,
      confidence,
      contracts: 1,
      maxHoldMinutes: 25,
      meta: {
        dominatingFamily,
        signalCount: allSignals.filter((s) => s.direction === direction).length,
        totalSignals: allSignals.length,
        semanticScore: Math.round(confidence * 100) / 100,
        signalDesc: signalDesc.slice(0, 200),
        paper: "LLM-GA Zhang 2025",
      },
    };
  }
}
