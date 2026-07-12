import type { Bar } from "../domain.js";

/** Market Cycle Detection — valuation, rate, vol, correlation regime overlay.
 *  4-cycle framework: expansion, peak, contraction, trough.
 *  Gates strategy selection based on macro regime. */
export type CyclePhase = "expansion" | "peak" | "contraction" | "trough";

export interface CycleAssessment {
  phase: CyclePhase;
  confidence: number;
  metrics: {
    trendScore: number;
    volScore: number;
    momentumScore: number;
    breadthScore: number;
  };
  recommendedStrategies: string[];
  restrictedStrategies: string[];
}

export function assessMarketCycle(bars: Bar[], lookback: number = 60): CycleAssessment {
  const n = Math.min(bars.length, lookback);
  const recent = bars.slice(-n);
  const closes = recent.map((b) => b.close);
  const highs = recent.map((b) => b.high);
  const lows = recent.map((b) => b.low);
  const volumes = recent.map((b) => b.volume);

  // 1. Trend score: slope of 20-bar regression
  const mid = Math.floor(closes.length / 2);
  const firstHalf = closes.slice(0, mid);
  const secondHalf = closes.slice(-mid);
  const avg1 = firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length;
  const avg2 = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length;
  const trendScore = (avg2 - avg1) / avg1;

  // 2. Vol score: recent vs historical range
  const ranges = recent.map((b, i) => (b.high - b.low) / closes[i]);
  const recentVol = ranges.slice(-10).reduce((a, b) => a + b, 0) / 10;
  const histVol = ranges.reduce((a, b) => a + b, 0) / ranges.length;
  const volScore = recentVol / (histVol + 0.0001);

  // 3. Momentum score: consecutive up/down days
  let upDays = 0;
  for (let i = 1; i < closes.length; i++)
    if (closes[i] > closes[i - 1]) upDays++;
  const momentumScore = upDays / (closes.length - 1);

  // 4. Breadth score: volume-weighted direction
  const volUp = recent
    .filter((b) => b.close > b.open)
    .reduce((s, b) => s + b.volume, 0);
  const volTotal = volumes.reduce((a, b) => a + b, 0);
  const breadthScore = volUp / (volTotal + 0.0001);

  // Phase classification
  let phase: CyclePhase;
  if (trendScore > 0.005 && momentumScore > 0.55) {
    phase = "expansion";
  } else if (trendScore > 0.005 && volScore > 1.3) {
    phase = "peak";
  } else if (trendScore < -0.005 && volScore > 1.2) {
    phase = "contraction";
  } else if (trendScore < -0.005 && momentumScore < 0.45) {
    phase = "trough";
  } else if (Math.abs(trendScore) < 0.003 && volScore < 0.9) {
    phase = "trough";
  } else {
    phase = trendScore > 0 ? "expansion" : "contraction";
  }

  const confidence = Math.min(
    1,
    (Math.abs(trendScore) * 80 + Math.abs(momentumScore - 0.5) * 2 + Math.abs(volScore - 1) * 0.5) / 2
  );

  return {
    phase,
    confidence: Number(confidence.toFixed(2)),
    metrics: {
      trendScore: Number(trendScore.toFixed(4)),
      volScore: Number(volScore.toFixed(2)),
      momentumScore: Number(momentumScore.toFixed(2)),
      breadthScore: Number(breadthScore.toFixed(2)),
    },
    recommendedStrategies:
      phase === "expansion"
        ? ["momentum-ignition", "session-momentum", "adx-trend", "breakout-retest", "donchian-breakout"]
        : phase === "peak"
        ? ["vol-premium", "gamma-scalp", "tail-risk", "vwap-reversion", "bollinger-squeeze"]
        : phase === "contraction"
        ? ["volatility-regime", "tail-risk", "false-breakout", "implied-correlation", "volatility-of-vol"]
        : ["liquidity-reversion", "supply-demand", "opening-range-reversal", "vwap-reversion", "seasonality"],
    restrictedStrategies:
      phase === "expansion"
        ? ["vol-premium", "gamma-scalp"]
        : phase === "peak"
        ? ["session-momentum", "adx-trend"]
        : phase === "contraction"
        ? ["session-momentum", "donchian-breakout", "momentum-ignition"]
        : ["adx-trend", "momentum-ignition", "session-momentum"],
  };
}
