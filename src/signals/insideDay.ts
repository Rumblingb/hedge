import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { resolve } from "node:path";

export interface InsideDayPrediction {
  insideDayProbability: number;
  isInsideDay: boolean;
  isCompressed: boolean;
  timestamp: string;
  latestBar: { high: number; low: number; close: number } | null;
}

const PRED_PATH = resolve(homedir(), ".rumbling-hedge/state/inside_day_prediction.json");

/**
 * Load inside-day prediction from XGBoost model output.
 * Returns null if no prediction file exists or parse fails.
 */
export function loadInsideDayPrediction(): InsideDayPrediction | null {
  try {
    const raw = readFileSync(PRED_PATH, "utf8");
    const data = JSON.parse(raw);
    return {
      insideDayProbability: data.inside_day_probability,
      isInsideDay: data.is_inside_day,
      isCompressed: data.is_compressed,
      timestamp: data.timestamp,
      latestBar: data.latest_bar ?? null,
    };
  } catch {
    return null;
  }
}

/**
 * Get confidence adjustment for breakout strategies based on inside-day probability.
 * High inside-day probability → suppress breakout entries (range compression → false breakouts).
 */
export function getInsideDayAdjustment(prediction: InsideDayPrediction | null): {
  confidenceMultiplier: number;
  suppressBreakouts: boolean;
} {
  if (!prediction) {
    return { confidenceMultiplier: 1.0, suppressBreakouts: false };
  }

  const prob = prediction.insideDayProbability;

  // Probabilistic suppression: higher inside-day prob = lower breakout confidence
  if (prob > 0.7) {
    return { confidenceMultiplier: 0.1, suppressBreakouts: true };   // Strong inside day → near-total suppress
  } else if (prob > 0.5) {
    return { confidenceMultiplier: 0.4, suppressBreakouts: true };   // Moderate inside day → partial suppress
  } else if (prob > 0.35) {
    return { confidenceMultiplier: 0.7, suppressBreakouts: false };  // Slightly compressed → reduce size
  }
  return { confidenceMultiplier: 1.0, suppressBreakouts: false };    // Normal range → no adjustment
}
