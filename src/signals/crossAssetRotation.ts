import type { Bar, StrategySignal, TradeSide } from "../domain.js";

/**
 * Cross-Asset Rotation Signals
 * Generates mean-reversion signals when inter-market ratios hit extremes.
 * Based on research from DE Shaw / AQR multi-asset rotation frameworks.
 * Adapted for 6-market futures: ES, NQ, CL, GC, 6E, ZB
 */

export interface RatioSignal {
  ratio: string;
  numerator: string;
  denominator: string;
  value: number;
  zScore: number;
  signal: TradeSide | "flat";
  confidence: number;
  rationale: string;
}

interface RollingStats {
  sum: number;
  sumSq: number;
  count: number;
  window: number[];
}

function rollingZScore(
  values: number[],
  window: number = 20
): { zScores: number[]; means: number[]; stds: number[] } {
  const zScores: number[] = [];
  const means: number[] = [];
  const stds: number[] = [];

  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
    const variance =
      slice.reduce((sum, v) => sum + (v - mean) ** 2, 0) / slice.length;
    const std = Math.sqrt(variance);

    means.push(mean);
    stds.push(std);
    zScores.push(std > 0 ? (values[i] - mean) / std : 0);
  }

  return { zScores, means, stds };
}

const RATIO_CONFIGS = [
  {
    id: "nq-es",
    description: "Tech vs Broad Market",
    numerator: "NQ",
    denominator: "ES",
    longSignal: "Tech outperformance mean-reversion expected",
    shortSignal: "Tech underperformance mean-reversion expected",
    zThreshold: 2.0,
  },
  {
    id: "cl-gc",
    description: "Risk-On vs Risk-Off",
    numerator: "CL",
    denominator: "GC",
    longSignal: "Risk appetite extreme — mean-reversion to safety expected",
    shortSignal: "Risk aversion extreme — mean-reversion to risk-on expected",
    zThreshold: 2.0,
  },
  {
    id: "zb-es",
    description: "Bonds vs Equities",
    numerator: "ZB",
    denominator: "ES",
    longSignal: "Flight to safety extreme — equity recovery expected",
    shortSignal: "Risk appetite extreme — bond recovery expected",
    zThreshold: 2.0,
  },
  {
    id: "gc-es",
    description: "Gold vs Equities (Inflation/Fear Gauge)",
    numerator: "GC",
    denominator: "ES",
    longSignal: "Fear extreme — equity recovery expected",
    shortSignal: "Complacency extreme — gold recovery expected",
    zThreshold: 2.0,
  },
];

function getPriceCloses(barsBySymbol: Map<string, Bar[]>): Map<string, number[]> {
  const result = new Map<string, number[]>();
  for (const [sym, bars] of barsBySymbol) {
    result.set(
      sym,
      bars.map((b) => b.close)
    );
  }
  return result;
}

function alignByTimestamp(
  pricesA: number[],
  pricesB: number[],
  minLen: number
): { alignedA: number[]; alignedB: number[] } {
  const len = Math.min(pricesA.length, pricesB.length, minLen);
  return {
    alignedA: pricesA.slice(-len),
    alignedB: pricesB.slice(-len),
  };
}

export function computeCrossAssetRatios(
  barsBySymbol: Map<string, Bar[]>,
  lookbackBars: number = 1000
): Map<string, RatioSignal[]> {
  const prices = getPriceCloses(barsBySymbol);
  const results = new Map<string, RatioSignal[]>();

  for (const config of RATIO_CONFIGS) {
    const pricesA = prices.get(config.numerator);
    const pricesB = prices.get(config.denominator);

    if (!pricesA || !pricesB) {
      continue;
    }

    const { alignedA, alignedB } = alignByTimestamp(
      pricesA,
      pricesB,
      lookbackBars
    );

    if (alignedA.length < 20) {
      continue;
    }

    // Compute ratio time series
    const ratios = alignedA.map((a, i) => a / alignedB[i]);

    // Rolling Z-scores
    const { zScores } = rollingZScore(ratios, 20);

    const signals: RatioSignal[] = [];
    const lastIdx = ratios.length - 1;
    const currentZ = zScores[lastIdx];
    const currentRatio = ratios[lastIdx];

    let signal: TradeSide | "flat" = "flat";
    let confidence = 0;
    let rationale = "";

    if (currentZ > config.zThreshold) {
      // Ratio is extremely high → numerator overbought vs denominator
      // Mean-reversion: short the ratio (short numerator, long denominator proxy)
      signal = "short";
      confidence = Math.min(1, (currentZ - config.zThreshold) / 2);
      rationale = `${config.shortSignal} (z=${currentZ.toFixed(2)})`;
    } else if (currentZ < -config.zThreshold) {
      // Ratio is extremely low → numerator oversold vs denominator
      signal = "long";
      confidence = Math.min(1, (Math.abs(currentZ) - config.zThreshold) / 2);
      rationale = `${config.longSignal} (z=${currentZ.toFixed(2)})`;
    } else {
      rationale = `Ratio within normal range (z=${currentZ.toFixed(2)})`;
    }

    signals.push({
      ratio: config.id,
      numerator: config.numerator,
      denominator: config.denominator,
      value: currentRatio,
      zScore: currentZ,
      signal,
      confidence,
      rationale,
    });

    results.set(config.id, signals);
  }

  return results;
}

export function ratioSignalsToStrategySignals(
  ratioSignals: Map<string, RatioSignal[]>,
  currentBar: Bar,
  symbol: string
): StrategySignal[] {
  const results: StrategySignal[] = [];

  for (const [ratioId, signals] of ratioSignals) {
    const signal = signals[signals.length - 1];
    if (!signal || signal.signal === "flat" || signal.confidence < 0.4) {
      continue;
    }

    // Cross-asset signals only apply to certain symbols
    const applicableSymbols = new Set([
      signal.numerator,
      signal.denominator,
    ]);
    if (!applicableSymbols.has(symbol)) {
      continue;
    }

    const entry = currentBar.close;
    const atr = (currentBar.high - currentBar.low) * 1.5;
    const side = signal.signal as TradeSide;
    const stop = side === "long" ? entry - atr : entry + atr;
    const target = side === "long" ? entry + atr * 2.5 : entry - atr * 2.5;

    results.push({
      symbol,
      strategyId: "cross-asset-rotation",
      side,
      entry,
      stop,
      target,
      rr: side === "long" ? (target - entry) / (entry - stop) : (entry - target) / (stop - entry),
      confidence: signal.confidence * 0.6, // Lower confidence for cross-asset signals
      contracts: 1,
      maxHoldMinutes: 60,
      meta: {
        pattern: `cross-asset-${ratioId}`,
        ratioValue: signal.value,
        zScore: signal.zScore,
        rationale: signal.rationale,
      },
    });
  }

  return results;
}

/**
 * Sector rotation proxy: which regime are we in based on cross-asset ratios?
 */
export function assessRotationRegime(
  barsBySymbol: Map<string, Bar[]>,
  lookbackBars: number = 500
): {
  regime: "risk-on" | "risk-off" | "inflation-hedge" | "neutral";
  confidence: number;
  signals: string[];
} {
  const ratioSignals = computeCrossAssetRatios(barsBySymbol, lookbackBars);
  let riskOnScore = 0;
  let riskOffScore = 0;
  const signalNotes: string[] = [];

  // NQ/ES rising = tech strength = risk-on
  const nqes = ratioSignals.get("nq-es");
  if (nqes && nqes.length > 0) {
    const z = nqes[nqes.length - 1].zScore;
    if (z > 1) {
      riskOnScore += 1;
      signalNotes.push(`NQ/ES elevated (tech strong, z=${z.toFixed(1)})`);
    } else if (z < -1) {
      riskOffScore += 1;
      signalNotes.push(`NQ/ES depressed (tech weak, z=${z.toFixed(1)})`);
    }
  }

  // CL/GC rising = risk appetite = risk-on
  const clgc = ratioSignals.get("cl-gc");
  if (clgc && clgc.length > 0) {
    const z = clgc[clgc.length - 1].zScore;
    if (z > 1) {
      riskOnScore += 1;
      signalNotes.push(`CL/GC elevated (risk appetite, z=${z.toFixed(1)})`);
    } else if (z < -1) {
      riskOffScore += 1;
      signalNotes.push(`CL/GC depressed (risk aversion, z=${z.toFixed(1)})`);
    }
  }

  // ZB/ES rising = flight to safety = risk-off
  const zbes = ratioSignals.get("zb-es");
  if (zbes && zbes.length > 0) {
    const z = zbes[zbes.length - 1].zScore;
    if (z > 1) {
      riskOffScore += 2; // Strong risk-off signal
      signalNotes.push(`ZB/ES elevated (flight to safety, z=${z.toFixed(1)})`);
    } else if (z < -1) {
      riskOnScore += 1;
      signalNotes.push(`ZB/ES depressed (risk appetite, z=${z.toFixed(1)})`);
    }
  }

  // GC/ES rising = fear/inflation hedge
  const gces = ratioSignals.get("gc-es");
  if (gces && gces.length > 0) {
    const z = gces[gces.length - 1].zScore;
    if (z > 1.5) {
      riskOffScore += 1;
      signalNotes.push(`GC/ES elevated (inflation/fear hedge, z=${z.toFixed(1)})`);
    }
  }

  let regime: "risk-on" | "risk-off" | "inflation-hedge" | "neutral";
  let confidence: number;

  if (riskOffScore >= 3) {
    regime = "risk-off";
    confidence = Math.min(1, riskOffScore / 5);
  } else if (riskOnScore >= 3) {
    regime = "risk-on";
    confidence = Math.min(1, riskOnScore / 5);
  } else if (gces && gces.length > 0 && gces[gces.length - 1].zScore > 2) {
    regime = "inflation-hedge";
    confidence = 0.7;
  } else {
    regime = "neutral";
    confidence = 0.5;
  }

  return { regime, confidence, signals: signalNotes };
}
