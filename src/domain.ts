export const ALLOWED_TOPSTEP_MARKETS = [
  "ES",
  "NQ",
  "RTY",
  "MES",
  "MNQ",
  "M2K",
  "NKD",
  "YM",
  "MYM",
  "6A",
  "6B",
  "6C",
  "6E",
  "E7",
  "6J",
  "6S",
  "6M",
  "6N",
  "M6E",
  "M6A",
  "M6B",
  "HE",
  "LE",
  "MBT",
  "MET",
  "CL",
  "NG",
  "QM",
  "QG",
  "MCL",
  "MNG",
  "RB",
  "HO",
  "PL",
  "GC",
  "SI",
  "HG",
  "MGC",
  "SIL",
  "MHG",
  "UB",
  "TN",
  "ZF",
  "ZT",
  "ZN",
  "ZB",
  "ZC",
  "ZW",
  "ZS",
  "ZM",
  "ZL"
] as const;

export type AllowedTopstepSymbol = (typeof ALLOWED_TOPSTEP_MARKETS)[number];
export type MarketCategory = "index" | "fx" | "energy" | "metal" | "bond" | "ag" | "crypto";
export type TradeSide = "long" | "short";
export type ExitReason = "stop" | "target" | "timeout" | "flat-cutoff";
export type Mode = "paper" | "backtest" | "live";
export type NewsDirection = TradeSide | "flat";

export interface Bar {
  ts: string;
  symbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface NewsScore {
  provider: string;
  direction: NewsDirection;
  probability: number;
  impact: "low" | "medium" | "high";
  headline?: string;
  reason: string;
}

export interface GuardrailConfig {
  allowedSymbols: string[];
  sessionStartCt: string;
  lastEntryCt: string;
  flatByCt: string;
  minRr: number;
  maxRiskPerTradePct: number;
  maxContracts: number;
  maxTradesPerDay: number;
  maxHoldMinutes: number;
  maxDailyLossR: number;
  maxConsecutiveLosses: number;
  newsProbabilityThreshold: number;
}

export interface ExecutionCostConfig {
  roundTripFeeRPerContract: number;
  slippageRPerSidePerContract: number;
  stressMultiplier: number;
  stressBufferRPerTrade: number;
}

export interface StrategyTuning {
  momentumLookbackBars: number;
  momentumVolumeMultiplier: number;
  reversionLookbackBars: number;
  reversionWickToBody: number;
  measuredMoveRr: number;
}

export interface LiveAdapterConfig {
  enabled: boolean;
  baseUrl?: string;
  accountId?: string;
  apiKey?: string;
}

export interface LabConfig {
  mode: Mode;
  journalPath: string;
  enabledStrategies: string[];
  guardrails: GuardrailConfig;
  executionCosts: ExecutionCostConfig;
  tuning: StrategyTuning;
  live: LiveAdapterConfig;
}

export interface StrategySignal {
  symbol: string;
  strategyId: string;
  side: TradeSide;
  entry: number;
  stop: number;
  target: number;
  rr: number;
  confidence: number;
  contracts: number;
  maxHoldMinutes: number;
  meta?: Record<string, string | number | boolean>;
}

export interface StrategyContext {
  symbol: string;
  bar: Bar;
  history: Bar[];
  sessionHistory: Bar[];
  config: LabConfig;
  news?: NewsScore;
  dailyTradeCount: number;
}

export interface Strategy {
  id: string;
  description: string;
  generateSignal(context: StrategyContext): StrategySignal | null;
}

export interface ActiveTrade extends StrategySignal {
  id: string;
  entryTs: string;
}

export interface TradeRecord extends ActiveTrade {
  exitTs: string;
  exitPrice: number;
  exitReason: ExitReason;
  pnlPoints: number;
  grossRMultiple: number;
  netRMultiple: number;
  executionCostR: number;
  rMultiple: number;
  status: "closed";
}

export interface BacktestResult {
  trades: TradeRecord[];
  rejectedSignals: number;
}

export interface RiskState {
  tradeCount: number;
  realizedR: number;
  consecutiveLosses: number;
}

export interface SummaryReport {
  totalTrades: number;
  wins: number;
  losses: number;
  winRate: number;
  totalR: number;
  averageR: number;
  grossTotalR: number;
  grossAverageR: number;
  netTotalR: number;
  netAverageR: number;
  frictionR: number;
  profitFactor: number;
  maxDrawdownR: number;
  byStrategy: Record<string, { trades: number; totalR: number; winRate: number }>;
  bySymbol: Record<string, ContributionSummary>;
  byMarketFamily: Record<MarketCategory, ContributionSummary>;
  suggestedFocus: SuggestedResearchFocus[];
}

export interface ContributionSummary {
  trades: number;
  grossTotalR: number;
  netTotalR: number;
  averageR: number;
  winRate: number;
}

export interface SuggestedResearchFocus {
  marketFamily: MarketCategory;
  weight: number;
  note: string;
}

export interface FamilyBudgetEntry {
  marketFamily: MarketCategory;
  trainNetR: number;
  testNetR: number;
  combinedNetR: number;
  weight: number;
  confidence: number;
  active: boolean;
  note: string;
}

export interface FamilyBudgetRecommendation {
  activeFamilies: MarketCategory[];
  targetWeights: Record<MarketCategory, number>;
  rankedFamilies: FamilyBudgetEntry[];
}

export interface EvolutionProposal {
  id: string;
  summary: string;
  rationale: string;
  patch: Partial<{
    enabledStrategies: string[];
    guardrails: Partial<GuardrailConfig>;
  }>;
  impact: "tighten" | "disable";
}
