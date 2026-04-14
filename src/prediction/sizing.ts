import type { PredictionCandidate, PredictionMarketSnapshot, PredictionSizingConfig, PredictionSizingRecommendation } from "./types.js";

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function round(value: number): number {
  return Number(value.toFixed(4));
}

export const DEFAULT_PREDICTION_SIZING: PredictionSizingConfig = {
  bankroll: 100,
  bankrollCurrency: "GBP",
  maxRiskPct: 0.01,
  maxExposurePct: 0.05,
  minStake: 1,
  confidenceHaircut: 0.5,
  liquidityCapPct: 0.02
};

export function buildPredictionSizingConfigFromEnv(env: NodeJS.ProcessEnv = process.env): PredictionSizingConfig {
  const read = (key: string, fallback: number): number => {
    const raw = env[key];
    if (!raw) return fallback;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  return {
    bankroll: read("BILL_PREDICTION_BANKROLL", DEFAULT_PREDICTION_SIZING.bankroll),
    bankrollCurrency: env.BILL_PREDICTION_BANKROLL_CURRENCY ?? DEFAULT_PREDICTION_SIZING.bankrollCurrency,
    maxRiskPct: read("BILL_PREDICTION_MAX_RISK_PCT", DEFAULT_PREDICTION_SIZING.maxRiskPct),
    maxExposurePct: read("BILL_PREDICTION_MAX_EXPOSURE_PCT", DEFAULT_PREDICTION_SIZING.maxExposurePct),
    minStake: read("BILL_PREDICTION_MIN_STAKE", DEFAULT_PREDICTION_SIZING.minStake),
    confidenceHaircut: read("BILL_PREDICTION_CONFIDENCE_HAIRCUT", DEFAULT_PREDICTION_SIZING.confidenceHaircut),
    liquidityCapPct: read("BILL_PREDICTION_LIQUIDITY_CAP_PCT", DEFAULT_PREDICTION_SIZING.liquidityCapPct)
  };
}

export function recommendPredictionStake(args: {
  candidate: Pick<PredictionCandidate, "matchScore" | "netEdgePct" | "displayedSizeA" | "displayedSizeB">;
  left: PredictionMarketSnapshot;
  right: PredictionMarketSnapshot;
  sizing: PredictionSizingConfig;
}): PredictionSizingRecommendation {
  const { candidate, left, right, sizing } = args;
  const buy = left.price <= right.price ? left : right;
  const reference = buy === left ? right : left;
  const consensusPrice = clamp((left.price + right.price) / 2, 0.01, 0.99);
  const impliedEdgePct = Math.max(0, (consensusPrice - buy.price) * 100);
  const confidenceAdjustedProb = clamp(
    buy.price + ((consensusPrice - buy.price) * clamp(candidate.matchScore, 0, 1) * sizing.confidenceHaircut),
    buy.price,
    0.99
  );
  const confidenceAdjustedEdgePct = Math.max(0, (confidenceAdjustedProb - buy.price) * 100);
  const kellyFractionRaw = buy.price >= 0.999 ? 0 : (confidenceAdjustedProb - buy.price) / (1 - buy.price);
  const kellyFraction = clamp(kellyFractionRaw, 0, 1);
  const minDisplayedSize = Math.min(candidate.displayedSizeA ?? Number.POSITIVE_INFINITY, candidate.displayedSizeB ?? Number.POSITIVE_INFINITY);
  const liquidityCap = Number.isFinite(minDisplayedSize)
    ? Math.max(0, minDisplayedSize * sizing.liquidityCapPct)
    : Number.POSITIVE_INFINITY;
  const cappedStakePct = Math.min(kellyFraction, sizing.maxRiskPct, sizing.maxExposurePct);
  const uncappedStake = sizing.bankroll * cappedStakePct;
  const recommendedStake = Math.max(0, Math.min(uncappedStake, liquidityCap));
  const finalStake = recommendedStake >= sizing.minStake ? recommendedStake : 0;
  const expectedValue = finalStake * ((confidenceAdjustedProb - buy.price) / Math.max(buy.price, 0.01));
  const rewardRiskRatio = finalStake <= 0 ? 0 : expectedValue / finalStake;

  return {
    action: "buy-cheaper-venue",
    venue: buy.venue,
    entryPrice: round(buy.price),
    referenceVenue: reference.venue,
    referencePrice: round(reference.price),
    consensusPrice: round(consensusPrice),
    bankroll: round(sizing.bankroll),
    bankrollCurrency: sizing.bankrollCurrency,
    impliedEdgePct: round(impliedEdgePct),
    confidenceAdjustedEdgePct: round(confidenceAdjustedEdgePct),
    kellyFraction: round(kellyFraction),
    cappedStakePct: round(finalStake > 0 ? cappedStakePct : 0),
    recommendedStake: round(finalStake),
    maxLoss: round(finalStake),
    expectedValue: round(expectedValue),
    rewardRiskRatio: round(rewardRiskRatio)
  };
}
