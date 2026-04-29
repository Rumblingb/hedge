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
  sameHorizon?: boolean;
  settlementCompatible: boolean;
  matchScore: number;
  entityOverlap: number;
  questionOverlap: number;
  grossEdgePct: number;
  netEdgePct: number;
  feeDragPct: number;
  displayedSizeA?: number;
  displayedSizeB?: number;
  sizeVerdict: string;
  verdict: PredictionVerdict;
  reasons: string[];
  sizing?: PredictionSizingRecommendation;
}

export interface PredictionNearMiss {
  candidateId: string;
  venueA: string;
  venueB: string;
  eventTitleA: string;
  eventTitleB: string;
  outcomeA: string;
  outcomeB: string;
  expiryA?: string;
  expiryB?: string;
  marketTypeA: string;
  marketTypeB: string;
  resolutionStyleA: string;
  resolutionStyleB: string;
  matchScore: number;
  entityOverlap: number;
  questionOverlap: number;
  grossEdgePct: number;
  netEdgePct: number;
  reasons: string[];
}

export interface PredictionScanDiagnostics {
  ts: string;
  totalMarkets: number;
  totalPairs: number;
  crossVenuePairs: number;
  skippedSameVenuePairs: number;
  skippedComboPairs: number;
  viablePairs: number;
  rejectReasons: Record<string, number>;
  venuePairs: Record<string, number>;
  topNearMisses: PredictionNearMiss[];
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

export type PredictionCommitteeStance = "approve" | "watch" | "reject";

export interface PredictionCommitteeVote {
  analyst: string;
  stance: PredictionCommitteeStance;
  summary: string;
  evidence: string[];
}

export interface PredictionCommitteeReview {
  finalStance: PredictionCommitteeStance;
  summary: string;
  votes: PredictionCommitteeVote[];
}

export interface PredictionScanInput {
  ts?: string;
  markets: PredictionMarketSnapshot[];
  fees: PredictionFeeConfig;
  sizing: PredictionSizingConfig;
  policy?: PredictionScanPolicy;
}

export interface PredictionScanPolicy {
  minMatchScore: number;
  paperMatchScore: number;
  paperEdgeThresholdPct: number;
  minDisplayedSize: number;
  minRecommendedStake: number;
}

export interface PredictionSourcePolicy {
  enabledSources: string[];
  requiredSources: string[];
  minHealthyVenues: number;
  minRowsPerVenue: number;
  minWatchCandidates: number;
  minPaperCandidates: number;
  preferredKalshiSeries: string[];
}

export interface PredictionReviewCheck {
  name: string;
  passed: boolean;
  observed: number | string;
  threshold: number | string;
  reason: string;
}

export interface PredictionCycleReview {
  ts: string;
  policy: PredictionSourcePolicy;
  venueCounts: Record<string, number>;
  counts: Record<PredictionVerdict, number>;
  crossVenueEdgeDetected?: boolean;
  topCandidate: {
    candidateId: string;
    verdict: PredictionVerdict;
    reasons: string[];
    grossEdgePct: number;
    netEdgePct: number;
    feeDragPct: number;
    edgeShortfallPct: number;
    matchScore: number;
    recommendedStake: number;
    venuePair: string;
    history: PredictionCandidateHistorySummary | null;
    committee?: PredictionCommitteeReview;
  } | null;
  checks: PredictionReviewCheck[];
  blockers: string[];
  recommendation: string;
  readyForPaper: boolean;
}

export type PredictionHistoryTrend = "improving" | "flat" | "worsening";

export interface PredictionCandidateHistorySummary {
  observations: number;
  watchCycles: number;
  paperCycles: number;
  bestGrossEdgePct: number;
  bestNetEdgePct: number;
  averageGrossEdgePct: number;
  averageNetEdgePct: number;
  averageShortfallPct: number;
  latestGrossEdgePct: number;
  latestNetEdgePct: number;
  latestShortfallPct: number;
  trend: PredictionHistoryTrend;
}

export interface PredictionRecurringCandidateSummary {
  candidateId: string;
  observations: number;
  bestGrossEdgePct: number;
  latestGrossEdgePct: number;
  latestShortfallPct: number;
  trend: PredictionHistoryTrend;
}

export interface PredictionPolicyEvaluation {
  objectiveScore: number;
  counts: Record<PredictionVerdict, number>;
  paperCount: number;
  watchCount: number;
  rejectCount: number;
  avgPaperEdgePct: number;
  avgPaperMatchScore: number;
  avgPaperStake: number;
  topPaperEdgePct: number;
  uniqueVenuePairs: number;
  lowConvictionPaperCount: number;
}

export interface PredictionSourceSummary {
  totalSources: number;
  activeSources: number;
  activePredictionSources: number;
  missingConfigSources: number;
  catalogOnlySources: number;
}

export interface PredictionRecentCycleSummary {
  totalCycles: number;
  healthyCycles: number;
  paperCandidateCycles: number;
  structuralWatchCycles: number;
  economicBlockCycles: number;
  averageTopEdgePct: number;
  averageTopMatchScore: number;
  dominantCandidate: PredictionRecurringCandidateSummary | null;
}

export interface PredictionTrainingState {
  ts: string;
  journalPath: string;
  policyPath: string;
  statePath: string;
  historyPath: string;
  trainingSetPath: string;
  baselinePolicy: PredictionScanPolicy;
  selectedPolicy: PredictionScanPolicy;
  baselineEvaluation: PredictionPolicyEvaluation;
  selectedEvaluation: PredictionPolicyEvaluation;
  recentCycleSummary: PredictionRecentCycleSummary;
  sourceSummary: PredictionSourceSummary;
  recommendations: string[];
}

export type BillPromotionStage = "research" | "backtest" | "rolling-oos" | "stress" | "paper" | "demo" | "live";

export interface BillPromotionState {
  track: string;
  currentStage: BillPromotionStage;
  recommendedStage: BillPromotionStage;
  updatedAt: string;
  blockers: string[];
  approvalsRequired: string[];
  checks: Array<{
    name: string;
    passed: boolean;
    reason: string;
  }>;
  notes: string[];
}
