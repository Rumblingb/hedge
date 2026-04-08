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
export type AccountPhase = "challenge" | "funded";
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
  blackout?: {
    active: boolean;
    eventTs: string;
    minutesBefore: number;
    minutesAfter: number;
    label: string;
  };
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
  trailingMaxDrawdownR: number;
  maxConsecutiveLosses: number;
  newsProbabilityThreshold: number;
  newsBlackoutMinutesBefore: number;
  newsBlackoutMinutesAfter: number;
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
  volatilityKillAtrMultiple: number;
}

export interface LiveAdapterConfig {
  enabled: boolean;
  baseUrl?: string;
  accountId?: string;
  apiKey?: string;
}

export interface PolygonDataConfig {
  enabled: boolean;
  apiKey?: string;
  baseUrl?: string;
}

export interface ExecutionEnvironmentConfig {
  latencyMs: number;
  latencyJitterMs: number;
  slippageTicksPerSide: number;
  dataQualityPenaltyR: number;
  maxSpreadTicks: number;
  riskPerContractDollars: number;
  slippageModel: "ticks" | "dollars";
}

export interface StopManagementConfig {
  enabled: boolean;
  breakEvenTriggerR: number;
  breakEvenOffsetR: number;
  runnerEnabled: boolean;
  runnerTriggerR: number;
  runnerTrailingDistanceR: number;
}

export interface LabConfig {
  mode: Mode;
  accountPhase: AccountPhase;
  journalPath: string;
  enabledStrategies: string[];
  guardrails: GuardrailConfig;
  executionCosts: ExecutionCostConfig;
  executionEnv: ExecutionEnvironmentConfig;
  stopManagement: StopManagementConfig;
  tuning: StrategyTuning;
  live: LiveAdapterConfig;
  polygon: PolygonDataConfig;
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
  rejectedSignalRecords: RejectedSignalRecord[];
  rejectedReasonCounts: Record<string, number>;
}

export interface RejectedSignalRecord {
  ts: string;
  symbol: string;
  strategyId: string;
  reasons: string[];
  newsImpact?: "low" | "medium" | "high";
  newsBlackoutActive: boolean;
}

export interface RiskState {
  tradeCount: number;
  realizedR: number;
  peakRealizedR: number;
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
  tradeQuality: TradeQualityMetrics;
}

export interface TradeQualityMetrics {
  expectancyR: number;
  payoffRatio: number;
  avgWinR: number;
  avgLossR: number;
  winRate: number;
  lossRate: number;
  maxConsecutiveWins: number;
  maxConsecutiveLosses: number;
  sharpePerTrade: number;
  sortinoPerTrade: number;
  ulcerIndexR: number;
  cvar95TradeR: number;
  riskOfRuinProb: number;
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

export interface AgenticIssue {
  id: string;
  severity: "low" | "medium" | "high";
  component: "research" | "risk" | "portfolio" | "data";
  summary: string;
  fixActions: string[];
}

export interface AgenticLearningAction {
  id: string;
  priority: "now" | "next" | "later";
  title: string;
  rationale: string;
  envPatch: Partial<{
    RH_MIN_RR: number;
    RH_MAX_CONTRACTS: number;
    RH_MAX_TRADES_PER_DAY: number;
    RH_MAX_DAILY_LOSS_R: number;
  }>;
}

export interface AgenticFundReport {
  timestamp: string;
  phase: AccountPhase;
  mode: Mode;
  status: "green" | "yellow" | "red";
  survivabilityScore: number;
  profitableNow: boolean;
  deployableNow: boolean;
  winnerProfileId: string | null;
  deployableProfileId: string | null;
  diagnostics: {
    testNetR: number;
    testTrades: number;
    maxDrawdownR: number;
    riskOfRuinProb: number;
    scoreStability: number;
    activeFamilies: number;
  };
  failedChecks: string[];
  issues: AgenticIssue[];
  learningActions: AgenticLearningAction[];
  nextRunChecklist: string[];
  agentStatus: AgentStatus;
  evolutionPlan: AgenticEvolutionPlan;
}

export interface AgentStatus {
  operatingMode: "stabilize" | "guarded-expansion";
  message: string;
}

export interface AgenticEvolutionPlan {
  objective: string;
  currentStep: string;
  nextSteps: string[];
  guardrailsLocked: string[];
  candidateMarkets: Array<{
    marketFamily: MarketCategory;
    confidence: number;
    note: string;
  }>;
  institutionalPrinciples: string[];
}

export interface RiskTradeScenarioSummary {
  name: string;
  trades: number;
  grossTotalR: number;
  netTotalR: number;
  averageR: number;
  winRate: number;
  maxDrawdownR: number;
  cvar95TradeR: number;
  riskOfRuinProb: number;
}

export interface RiskTradeBucketSummary {
  bucket: string;
  trades: number;
  winRate: number;
  grossTotalR: number;
  netTotalR: number;
  averageR: number;
  maxDrawdownR: number;
  cvar95TradeR: number;
  note: string;
}

export interface RiskTradeModelReport {
  timestamp: string;
  current: RiskTradeScenarioSummary;
  frictionless: RiskTradeScenarioSummary;
  stressed: RiskTradeScenarioSummary;
  edgeDecay: {
    frictionlessMinusCurrentNetR: number;
    stressedMinusCurrentNetR: number;
    grossEdgeRetention: number;
  };
  rrBuckets: RiskTradeBucketSummary[];
  strategyInsights: RiskTradeSegmentInsight[];
  symbolInsights: RiskTradeSegmentInsight[];
  recommendation: {
    preferredBucket: string | null;
    reason: string;
    modelView: string;
  };
}

export interface RiskTradeSegmentInsight {
  kind: "strategy" | "symbol";
  key: string;
  current: RiskTradeScenarioSummary;
  frictionless: RiskTradeScenarioSummary;
  stressed: RiskTradeScenarioSummary;
  rrBuckets: RiskTradeBucketSummary[];
  recommendation: {
    preferredBucket: string | null;
    reason: string;
    modelView: string;
  };
}
