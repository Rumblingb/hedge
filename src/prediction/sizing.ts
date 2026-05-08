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

function executableAsk(market: PredictionMarketSnapshot): number {
  return typeof market.bestAsk === "number" && Number.isFinite(market.bestAsk) && market.bestAsk > 0
    ? market.bestAsk
    : market.price;
}

function executableBid(market: PredictionMarketSnapshot): number {
  return typeof market.bestBid === "number" && Number.isFinite(market.bestBid) && market.bestBid > 0
    ? market.bestBid
    : market.price;
}

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
  const leftAsk = executableAsk(left);
  const rightAsk = executableAsk(right);
  const buy = leftAsk <= rightAsk ? left : right;
  const reference = buy === left ? right : left;
  const buyEntryPrice = executableAsk(buy);
  const referenceExitPrice = executableBid(reference);
  const consensusPrice = clamp((buyEntryPrice + referenceExitPrice) / 2, 0.01, 0.99);
  const impliedEdgePct = Math.max(0, (referenceExitPrice - buyEntryPrice) * 100);
  const confidenceAdjustedProb = clamp(
    buyEntryPrice + ((referenceExitPrice - buyEntryPrice) * clamp(candidate.matchScore, 0, 1) * sizing.confidenceHaircut),
    buyEntryPrice,
    0.99
  );
  const confidenceAdjustedEdgePct = Math.max(0, (confidenceAdjustedProb - buyEntryPrice) * 100);
  const kellyFractionRaw = buyEntryPrice >= 0.999 ? 0 : (confidenceAdjustedProb - buyEntryPrice) / (1 - buyEntryPrice);
  const kellyFraction = clamp(kellyFractionRaw, 0, 1);
  const minDisplayedSize = Math.min(candidate.displayedSizeA ?? Number.POSITIVE_INFINITY, candidate.displayedSizeB ?? Number.POSITIVE_INFINITY);
  const liquidityCap = Number.isFinite(minDisplayedSize)
    ? Math.max(0, minDisplayedSize * sizing.liquidityCapPct)
    : Number.POSITIVE_INFINITY;
  const cappedStakePct = Math.min(kellyFraction, sizing.maxRiskPct, sizing.maxExposurePct);
  const riskCap = sizing.bankroll * Math.min(sizing.maxRiskPct, sizing.maxExposurePct);
  const uncappedStake = sizing.bankroll * cappedStakePct;
  const cappedStake = Math.max(0, Math.min(uncappedStake, liquidityCap));
  const minTicketAllowed = confidenceAdjustedEdgePct > 0 && sizing.minStake <= riskCap && sizing.minStake <= liquidityCap;
  const finalStake = cappedStake >= sizing.minStake
    ? cappedStake
    : minTicketAllowed && cappedStake > 0
      ? sizing.minStake
      : 0;
  const expectedValue = finalStake * ((confidenceAdjustedProb - buyEntryPrice) / Math.max(buyEntryPrice, 0.01));
  const rewardRiskRatio = finalStake <= 0 ? 0 : expectedValue / finalStake;
  const displayedSize = Number.isFinite(minDisplayedSize) ? minDisplayedSize : 0;
  const orderSizePctOfDisplayed = displayedSize > 0 ? finalStake / displayedSize : 0;
  const impactPenaltyPct = displayedSize > 0
    ? clamp(orderSizePctOfDisplayed * 100 * 0.5, 0, confidenceAdjustedEdgePct)
    : confidenceAdjustedEdgePct;
  const postImpactEdgePct = Math.max(0, confidenceAdjustedEdgePct - impactPenaltyPct);
  const fillQuality = displayedSize <= 0
    ? "unknown"
    : finalStake <= 0
      ? "thin"
      : orderSizePctOfDisplayed > sizing.liquidityCapPct
        ? "too-large"
        : orderSizePctOfDisplayed > sizing.liquidityCapPct * 0.75
          ? "thin"
          : "good";

  return {
    action: "buy-cheaper-venue",
    venue: buy.venue,
    entryPrice: round(buyEntryPrice),
    referenceVenue: reference.venue,
    referencePrice: round(referenceExitPrice),
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
    rewardRiskRatio: round(rewardRiskRatio),
    liquidity: {
      minDisplayedSize: round(displayedSize),
      liquidityCap: round(Number.isFinite(liquidityCap) ? liquidityCap : 0),
      orderSizePctOfDisplayed: round(orderSizePctOfDisplayed),
      impactPenaltyPct: round(impactPenaltyPct),
      postImpactEdgePct: round(postImpactEdgePct),
      fillQuality
    }
  };
}
