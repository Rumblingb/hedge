import type { PredictionSourcePolicy } from "./types.js";

export const DEFAULT_PREDICTION_SOURCE_POLICY: PredictionSourcePolicy = {
  enabledSources: ["polymarket", "kalshi", "manifold"],
  requiredSources: ["polymarket", "kalshi"],
  minHealthyVenues: 2,
  minRowsPerVenue: 5,
  minWatchCandidates: 1,
  minPaperCandidates: 1,
  preferredKalshiSeries: []
};

function parseCsv(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function readNumber(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const raw = env[key];
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function buildPredictionSourcePolicyFromEnv(env: NodeJS.ProcessEnv = process.env): PredictionSourcePolicy {
  const enabledSources = parseCsv(env.BILL_PREDICTION_SOURCES);
  const requiredSources = parseCsv(env.BILL_PREDICTION_REQUIRED_SOURCES);

  return {
    enabledSources: enabledSources.length > 0 ? enabledSources : DEFAULT_PREDICTION_SOURCE_POLICY.enabledSources,
    requiredSources: requiredSources.length > 0 ? requiredSources : DEFAULT_PREDICTION_SOURCE_POLICY.requiredSources,
    minHealthyVenues: readNumber(env, "BILL_PREDICTION_MIN_HEALTHY_VENUES", DEFAULT_PREDICTION_SOURCE_POLICY.minHealthyVenues),
    minRowsPerVenue: readNumber(env, "BILL_PREDICTION_MIN_ROWS_PER_VENUE", DEFAULT_PREDICTION_SOURCE_POLICY.minRowsPerVenue),
    minWatchCandidates: readNumber(env, "BILL_PREDICTION_MIN_WATCH_CANDIDATES", DEFAULT_PREDICTION_SOURCE_POLICY.minWatchCandidates),
    minPaperCandidates: readNumber(env, "BILL_PREDICTION_MIN_PAPER_CANDIDATES", DEFAULT_PREDICTION_SOURCE_POLICY.minPaperCandidates),
    preferredKalshiSeries: parseCsv(env.BILL_PREDICTION_KALSHI_SERIES_ALLOWLIST)
  };
}
