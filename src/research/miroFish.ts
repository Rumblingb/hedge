import type { StrategySignal, TradeSide } from "../domain.js";

/**
 * MiroFish Research Edge Detection
 * Separate research track for cross-market anomaly detection.
 * Identifies microstructure anomalies, unusual flows, and edge patterns.
 * Runs as a parallel research lane, not an execution strategy.
 */

export interface MiroFishAnomaly {
  symbol: string;
  anomalyType: "unusual-volume" | "price-divergence" | "correlation-break" | "vol-spike" | "order-flow" | "gamma-event";
  severity: number; // 0-1
  direction: TradeSide | "flat";
  confidence: number;
  timestamp: string;
  details: Record<string, number>;
}

export interface MiroFishReport {
  generatedAt: string;
  anomalies: MiroFishAnomaly[];
  summary: {
    totalAnomalies: number;
    highSeverity: number;
    dominantDirection: TradeSide | "flat";
    marketRegime: string;
  };
}

export function detectMiroFishAnomalies(args: {
  symbol: string;
  prices: number[];
  volumes: number[];
  highs: number[];
  lows: number[];
  timestamps: string[];
  lookback: number;
}): MiroFishAnomaly[] {
  const { symbol, prices, volumes, highs, lows, timestamps, lookback } = args;
  const anomalies: MiroFishAnomaly[] = [];
  const n = prices.length;
  if (n < lookback) return anomalies;

  const recentPrices = prices.slice(-lookback);
  const recentVols = volumes.slice(-lookback);
  const recentHighs = highs.slice(-lookback);
  const recentLows = lows.slice(-lookback);

  // 1. Unusual volume detection (3x normal)
  const avgVol = recentVols.reduce((a, b) => a + b, 0) / recentVols.length;
  const latestVol = volumes[n - 1];
  if (latestVol > avgVol * 3) {
    anomalies.push({
      symbol,
      anomalyType: "unusual-volume",
      severity: Math.min(1, (latestVol / avgVol - 2) / 4),
      direction: prices[n - 1] > prices[n - 2] ? "long" : "short",
      confidence: 0.7,
      timestamp: timestamps[n - 1],
      details: { volumeRatio: latestVol / avgVol },
    });
  }

  // 2. Price divergence (price vs volume direction)
  const priceMove = (prices[n - 1] - prices[n - 5]) / prices[n - 5];
  const volTrend =
    recentVols.slice(-5).reduce((a, b) => a + b, 0) /
    recentVols.slice(0, 5).reduce((a, b) => a + b, 0);
  if (Math.abs(priceMove) > 0.005 && volTrend < 0.7) {
    anomalies.push({
      symbol,
      anomalyType: "price-divergence",
      severity: Math.min(1, Math.abs(priceMove) * 100),
      direction: priceMove > 0 ? "short" : "long", // Divergence = fade
      confidence: 0.65,
      timestamp: timestamps[n - 1],
      details: { priceMove, volTrend },
    });
  }

  // 3. Vol spike (range > 3x normal)
  const ranges = recentHighs.map((h, i) => (h - recentLows[i]) / recentPrices[i]);
  const avgRange = ranges.reduce((a, b) => a + b, 0) / ranges.length;
  const latestRange = (highs[n - 1] - lows[n - 1]) / prices[n - 1];
  if (latestRange > avgRange * 3) {
    anomalies.push({
      symbol,
      anomalyType: "vol-spike",
      severity: Math.min(1, (latestRange / avgRange - 2) / 4),
      direction: prices[n - 1] > prices[n - 2] ? "long" : "short",
      confidence: 0.6,
      timestamp: timestamps[n - 1],
      details: { volRatio: latestRange / avgRange },
    });
  }

  return anomalies;
}

export function generateMiroFishReport(
  allAnomalies: MiroFishAnomaly[]
): MiroFishReport {
  const highSev = allAnomalies.filter((a) => a.severity > 0.7);
  const dirs = allAnomalies
    .filter((a) => a.direction !== "flat")
    .map((a) => a.direction);
  const dominant =
    dirs.filter((d) => d === "long").length > dirs.filter((d) => d === "short").length
      ? "long"
      : dirs.filter((d) => d === "short").length > 0
      ? "short"
      : "flat";

  return {
    generatedAt: new Date().toISOString(),
    anomalies: allAnomalies,
    summary: {
      totalAnomalies: allAnomalies.length,
      highSeverity: highSev.length,
      dominantDirection: dominant as TradeSide | "flat",
      marketRegime: highSev.length > 3 ? "active" : "quiet",
    },
  };
}
