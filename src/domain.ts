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
export const SUPPORTED_STRATEGY_IDS = [
  "session-momentum",
  "opening-range-reversal",
  "liquidity-reversion",
  "ict-displacement",
  "orb-breakout",
  "donchian-breakout",
  "wq-trend-mom",
  "daily-range-breakout",
  "bollinger-squeeze",
  "capitulation-score",
  "cross-sectional-momentum",
  "drawdown-momentum",
  "drift-regime-csm",
  "event-spike-fade",
  "expiry-flow",
  "gamma-stability",
  "hmm-pairs-arb",
  "ict-breakout",
  "ict-narrative",
  "ict-sweep-reversion",
  "kronos-direction",
  "llm-ga-evolutionary",
  "llm-momentum-gate",
  "network-momentum",
  "opening-stop-hunt",
  "optimal-cost-pairs",
  "orb-breakout-60m",
  "pairs-trading",
  "push-response-anomaly",
  "regime-orb-breakout",
  "wq-alpha-009-rust",
  "wq-alpha-001-rust",
  "wq-alpha-012-rust",
  "two-level-uncertainty",
  "vol-risk-premium",
  "volatility-regime",
  "vwap-reversion",
  "wq-alpha-001",
  "wq-alpha-002",
  "wq-alpha-006",
  "wq-alpha-009",
  "wq-alpha-012",
  "wq-alpha-020",
  "wq-alpha-054",
  "wq-alpha-065",
  "wq-alpha-101",
  "wq-alpha-003",
  "wq-alpha-007",
  "wq-alpha-008",
  "wq-alpha-021",
  "wq-alpha-033",
  "wq-alpha-049",
  "wq-alpha-053",
  "wq-alpha-083",
  "wq-alpha-024",
  "wq-alpha-044",
  "wq-alpha-057",
  "wq-trend-mom-60m",
  "wq-vol-regime-60m"
] as const;
// Strategy IDs are intentionally open-ended: research feeds, no-edge ledgers,
// strategy-zoo experiments, and externally generated hypotheses can reference
// IDs before they are promoted into the executable catalog above. Treat
// SUPPORTED_STRATEGY_IDS as the executable default/catalog seed, not as a
// closed-world union that blocks research and audit tooling from compiling.
export type SupportedStrategyId = string;

/**
 * Strategy Classification — the ONLY source of truth for what each strategy actually is.
 * 
 * GOLD:       Proven edge, ≥20 demo trades, positive expectancy, OOS passed
 * SILVER:     Backtest profit factor >1.2, OOS passed, no demo trades yet
 * BRONZE:     File exists, builds signals, never through backtest/OOS/demo
 * SKELETON:   Name only — no implementation file, or stub with no real logic
 * QUARANTINED: Tested, failed OOS — no-edge ledger confirmed
 *
 * TRUTH IS NOW IN PIPELINE STAGES (src/engine/pipeline.ts).
 * This classification is legacy backward compatibility only.
 */
import { PipelineStage, stageToLegacyClassification } from "./engine/pipeline.js";

export type Classification = "GOLD" | "SILVER" | "BRONZE" | "SKELETON" | "QUARANTINED";

export const STRATEGY_CLASSIFICATION: Record<SupportedStrategyId, Classification> = {
  "ict-displacement": "QUARANTINED",
  "liquidity-reversion": "QUARANTINED",
  "session-momentum": "QUARANTINED",
  "opening-range-reversal": "QUARANTINED",
  "orb-breakout": "QUARANTINED",
  "donchian-breakout": "BRONZE",
  "wq-trend-mom": "BRONZE",
  "daily-range-breakout": "BRONZE",
};

export function getClassification(id: SupportedStrategyId): Classification {
  return STRATEGY_CLASSIFICATION[id] ?? "SKELETON";
}

export function isExecutable(id: SupportedStrategyId): boolean {
  const c = getClassification(id);
  return c === "GOLD" || c === "SILVER";
}

/**
 * Filter strategies that should be actively tested/researched.
 */
export function isTestable(id: SupportedStrategyId): boolean {
  const c = getClassification(id);
  return c === "BRONZE" || c === "SILVER" || c === "GOLD";
}

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

export interface MacroContextSnapshot {
  source: "free-macro-context" | "unknown";
  generatedAt?: string;
  tailScore: number | null;
  riskRegime: "normal" | "elevated" | "stress" | "unknown";
  vixLevel: number | null;
  vixTermStructure: "contango" | "backwardation" | "unknown";
  yieldCurveProxyBps: number | null;
  creditRiskProxy: "normal" | "weakening" | "unknown";
  equityTrendProxy: "risk-on" | "risk-off" | "unknown";
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
  reversionVolumeMultiplier: number;
  reversionWickToBody: number;
  openingRangeVolumeMultiplier: number;
  measuredMoveRr: number;
  volatilityKillAtrMultiple: number;
  pairsZEntry: number;
  pairsLookbackBars: number;
  volRegimeAtrFast: number;
  volRegimeAtrSlow: number;
  volRegimeThreshold: number;
}

export interface LiveAdapterConfig {
  enabled: boolean;
  baseUrl?: string;
  username?: string;
  accountId?: string;
  allowedAccountId?: string;
  allowedAccountIds?: string[];
  allowedAccountLabel?: string;
  allowedAccountLabels?: string[];
  apiKey?: string;
  demoOnly: boolean;
  readOnly: boolean;
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
  killSwitchPath: string;
  enabledStrategies: string[];
  guardrails: GuardrailConfig;
  executionCosts: ExecutionCostConfig;
  executionEnv: ExecutionEnvironmentConfig;
  stopManagement: StopManagementConfig;
  tuning: StrategyTuning;
  live: LiveAdapterConfig;
  polygon: PolygonDataConfig;
}

export interface RedactedLabConfig extends Omit<LabConfig, "live" | "polygon"> {
  live: Omit<LiveAdapterConfig, "apiKey"> & { apiKey?: string };
  polygon: Omit<PolygonDataConfig, "apiKey"> & { apiKey?: string };
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

/** Macro context injected per-symbol into every strategy call. Optional — strategies that don't read it are unaffected. */
export interface MacroContext {
  /** HMM regime for this symbol: "trending" | "range-chop" | "high-vol" | "low-vol" */
  hmmRegime?: string;
  /** HMM state confidence 0–1 */
  hmmConfidence?: number;
  /** COT dealer z-score (52-week). Negative = dealer net short. Extreme < -1.0 or > 1.0 is actionable. */
  cotDealerZ52?: number;
  /** VIX contango flag: "contango" | "backwardation" | undefined */
  vixRegime?: string;
  /** Capitulation score 0–5 (COT extreme + VIX backwardation + options put/call extreme) */
  capitulationScore?: number;
  /** Kronos forecast direction: 1 = bullish, -1 = bearish, 0 = neutral. From Kronos sidecar on :8787 */
  kronosDirection?: number;
  /** Kronos forecast confidence 0–1 */
  kronosConfidence?: number;
}

export interface StrategyContext {
  symbol: string;
  bar: Bar;
  history: Bar[];
  sessionHistory: Bar[];
  config: LabConfig;
  news?: NewsScore;
  dailyTradeCount: number;
  macroContext?: MacroContextSnapshot;
  /** Optional macro context: HMM regime, COT positioning, VIX regime. Read-only for strategies. */
  macro?: MacroContext;
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
  macroContext?: MacroContextSnapshot;
}

export interface RejectedSignalRecord {
  ts: string;
  symbol: string;
  strategyId: string;
  reasons: string[];
  newsImpact?: "low" | "medium" | "high";
  newsBlackoutActive: boolean;
  macroRiskRegime?: MacroContextSnapshot["riskRegime"];
  macroTailScore?: number | null;
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
  byStrategy: Record<string, StrategyContributionSummary>;
  byLeaf?: Record<string, StrategyContributionSummary>;
  bySymbol: Record<string, ContributionSummary>;
  byMarketFamily: Record<MarketCategory, ContributionSummary>;
  suggestedFocus: SuggestedResearchFocus[];
  tradeQuality: TradeQualityMetrics;
}

export interface StrategyContributionSummary extends ContributionSummary {
  totalR: number;
  profitFactor: number;
  payoffRatio: number;
  avgWinR: number;
  avgLossR: number;
  sharpePerTrade: number;
  sortinoPerTrade: number;
  ulcerIndexR: number;
  cvar95TradeR: number;
  riskOfRuinProb: number;
  maxConsecutiveLosses: number;
  frictionR: number;
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
    RH_ENABLED_STRATEGIES: string;
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
