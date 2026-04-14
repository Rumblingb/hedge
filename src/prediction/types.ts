export type PredictionVerdict = "reject" | "watch" | "paper-trade";

export interface PredictionMarketSnapshot {
  venue: string;
  externalId: string;
  eventTitle: string;
  marketQuestion: string;
  outcomeLabel: string;
  side: "yes" | "no";
  expiry?: string;
  settlementText?: string;
  price: number;
  displayedSize?: number;
}

export interface PredictionCandidate {
  ts: string;
  candidateId: string;
  venueA: string;
  venueB: string;
  marketType: string;
  normalizedEventKey: string;
  normalizedQuestionKey: string;
  normalizedOutcomeKey: string;
  eventTitleA: string;
  eventTitleB: string;
  outcomeA: string;
  outcomeB: string;
  expiryA?: string;
  expiryB?: string;
  settlementCompatible: boolean;
  matchScore: number;
  entityOverlap: number;
  questionOverlap: number;
  grossEdgePct: number;
  netEdgePct: number;
  displayedSizeA?: number;
  displayedSizeB?: number;
  sizeVerdict: string;
  verdict: PredictionVerdict;
  reasons: string[];
  sizing?: PredictionSizingRecommendation;
}

export interface PredictionFeeConfig {
  venueAFeePct: number;
  venueBFeePct: number;
  slippagePct: number;
  minDisplayedSize: number;
  watchThresholdPct: number;
}

export interface PredictionSizingConfig {
  bankroll: number;
  bankrollCurrency: string;
  maxRiskPct: number;
  maxExposurePct: number;
  minStake: number;
  confidenceHaircut: number;
  liquidityCapPct: number;
}

export interface PredictionSizingRecommendation {
  action: "buy-cheaper-venue";
  venue: string;
  entryPrice: number;
  referenceVenue: string;
  referencePrice: number;
  consensusPrice: number;
  bankroll: number;
  bankrollCurrency: string;
  impliedEdgePct: number;
  confidenceAdjustedEdgePct: number;
  kellyFraction: number;
  cappedStakePct: number;
  recommendedStake: number;
  maxLoss: number;
  expectedValue: number;
  rewardRiskRatio: number;
}

export interface PredictionScanInput {
  ts?: string;
  markets: PredictionMarketSnapshot[];
  fees: PredictionFeeConfig;
  sizing: PredictionSizingConfig;
}
