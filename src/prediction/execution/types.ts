import type { PredictionCandidate, PredictionSizingRecommendation } from "../types.js";

export type FillMode = "paper" | "live";

export interface PaperFill {
  fillId: string;
  ts: string;
  mode: FillMode;
  candidateId: string;
  venue: string;
  referenceVenue: string;
  marketQuestion: string;
  outcomeLabel: string;
  side: "yes" | "no";
  price: number;
  referencePrice: number;
  consensusPrice: number;
  stake: number;
  stakeCurrency: string;
  impliedEdgePct: number;
  expectedValue: number;
  maxLoss: number;
  rewardRiskRatio: number;
  reasons: string[];
}

export interface ExecutionOutcome {
  placed: PaperFill[];
  skipped: Array<{
    candidateId: string;
    reason: string;
  }>;
  totalStake: number;
  totalMaxLoss: number;
  mode: FillMode;
}

export interface ExecutionConfig {
  mode: FillMode;
  maxTotalStake: number;
  maxTotalMaxLoss: number;
  stakeCurrency: string;
  journalPath: string;
  onePerCandidate: boolean;
}

export interface LiveGateReason {
  ok: boolean;
  failures: string[];
}

export interface ExecutionContext {
  config: ExecutionConfig;
  existingFills: PaperFill[];
  now: () => Date;
}

export function isExecutableCandidate(candidate: PredictionCandidate): boolean {
  return candidate.verdict === "paper-trade" && Boolean(candidate.sizing) && candidate.sizing!.recommendedStake > 0;
}

export function sizingToFill(
  candidate: PredictionCandidate,
  sizing: PredictionSizingRecommendation,
  mode: FillMode,
  now: Date
): PaperFill {
  return {
    fillId: `${candidate.candidateId}-${now.toISOString()}`,
    ts: now.toISOString(),
    mode,
    candidateId: candidate.candidateId,
    venue: sizing.venue,
    referenceVenue: sizing.referenceVenue,
    marketQuestion: candidate.eventTitleA ?? candidate.eventTitleB ?? candidate.candidateId,
    outcomeLabel: candidate.outcomeA ?? candidate.outcomeB ?? "yes",
    side: "yes",
    price: sizing.entryPrice,
    referencePrice: sizing.referencePrice,
    consensusPrice: sizing.consensusPrice,
    stake: sizing.recommendedStake,
    stakeCurrency: sizing.bankrollCurrency,
    impliedEdgePct: sizing.impliedEdgePct,
    expectedValue: sizing.expectedValue,
    maxLoss: sizing.maxLoss,
    rewardRiskRatio: sizing.rewardRiskRatio,
    reasons: candidate.reasons ?? []
  };
}
