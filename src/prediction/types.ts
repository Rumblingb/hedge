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
  eventTitleA: string;
  eventTitleB: string;
  outcomeA: string;
  outcomeB: string;
  expiryA?: string;
  expiryB?: string;
  settlementCompatible: boolean;
  matchScore: number;
  grossEdgePct: number;
  netEdgePct: number;
  displayedSizeA?: number;
  displayedSizeB?: number;
  sizeVerdict: string;
  verdict: PredictionVerdict;
  reasons: string[];
}

export interface PredictionFeeConfig {
  venueAFeePct: number;
  venueBFeePct: number;
  slippagePct: number;
  minDisplayedSize: number;
  watchThresholdPct: number;
}

export interface PredictionScanInput {
  ts?: string;
  markets: PredictionMarketSnapshot[];
  fees: PredictionFeeConfig;
}
