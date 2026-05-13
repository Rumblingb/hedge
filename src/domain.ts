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
  "session-momentum","opening-range-reversal","opening-stop-hunt","liquidity-reversion","ict-displacement","ict-displacement-5m","ict-narrative","ict-sweep-reversion","ict-breakout",
  "expiry-flow","pairs-trading","cross-sectional-momentum","volatility-regime",
  // WorldQuant 101 Alphas — institutional alpha signals (Kakushadze 2015)
  "wq-alpha-001","wq-alpha-002","wq-alpha-003","wq-alpha-006","wq-alpha-007",
  "wq-alpha-008","wq-alpha-009","wq-alpha-012","wq-alpha-020","wq-alpha-021",
  "wq-alpha-024","wq-alpha-033","wq-alpha-044","wq-alpha-049","wq-alpha-053",
  "wq-alpha-054","wq-alpha-057","wq-alpha-065","wq-alpha-083","wq-alpha-101",
  "ret-30-momentum","vwap-reversion","bollinger-squeeze",
  "donchian-breakout",
  "prop-fvg-scalp","prop-liq-grab","prop-orb-scalp","prop-vwap-bounce",
  "prop-momentum-scalp","tick-scalp","zscore-mean-rev","open-drive-fade",
  "time-based-exit","range-bound-scalp",
  "drift-regime-csm","hmm-pairs-arb","gamma-stability",
  "llm-momentum-gate","two-level-uncertainty",
  "llm-ga-evolutionary",
  "drawdown-momentum","push-response-anomaly","intraday-momentum",
  "optimal-cost-pairs","network-momentum",
  "vol-targeted-momentum",
  "capitulation-score",
  "structural-flows",
  "event-spike-fade",
  "post-news-settlement",
  "options-selling-framework",
  "kronos-direction",
  "gap-fade-regime",
  "short-term-reversal",
  "monthly-seasonality",
  "regime-locked-momentum",
  "rsi2-mean-reversion",
  "vol-risk-premium",
  "cot-positioning",
  "vix-term-structure",
  "cpi-reaction",
  "opec-fade",
  "eia-inventory",
  "gamma-pin",
  "wq-alpha-009-rust",
  "wq-alpha-001-rust",
  "wq-alpha-012-rust",
  "orb-breakout"
] as const;
export type SupportedStrategyId = (typeof SUPPORTED_STRATEGY_IDS)[number];

/**
 * Strategy Classification — the ONLY source of truth for what each strategy actually is.
 * 
 * GOLD:       Proven edge, ≥20 demo trades, positive expectancy, OOS passed
 * SILVER:     Backtest profit factor >1.2, OOS passed, no demo trades yet
 * BRONZE:     File exists, builds signals, never through backtest/OOS/demo
 * SKELETON:   Name only — no implementation file, or stub with no real logic
 * QUARANTINED: Tested, failed OOS — no-edge ledger confirmed
 */
export type Classification =
  | "GOLD"
  | "SILVER"
  | "BRONZE"
  | "SKELETON"
  | "QUARANTINED";

/**
 * Every strategy ID mapped to its real classification.
 * This is the SYSTEM TRUTH — NOT aspirational.
 * Update only when a strategy actually passes the next gate.
 */
export const STRATEGY_CLASSIFICATION: Record<SupportedStrategyId, Classification> = {
  // ── QUARANTINED — tested, failed OOS (no-edge ledger confirmed) ──
  "ict-displacement": "QUARANTINED",
  "ict-displacement-5m": "QUARANTINED",
  "liquidity-reversion": "QUARANTINED",
  "session-momentum": "QUARANTINED",
  "structural-flows": "QUARANTINED",
  "ret-30-momentum": "BRONZE",
  "vwap-reversion": "QUARANTINED",
  "cross-sectional-momentum": "QUARANTINED",
  "wq-alpha-001": "QUARANTINED",
  "wq-alpha-002": "QUARANTINED",
  "wq-alpha-003": "QUARANTINED",
  "wq-alpha-006": "QUARANTINED",
  "wq-alpha-007": "QUARANTINED",
  "wq-alpha-008": "QUARANTINED",
  "wq-alpha-020": "QUARANTINED",
  "wq-alpha-024": "QUARANTINED",
  "wq-alpha-033": "QUARANTINED",
  "wq-alpha-044": "QUARANTINED",
  "wq-alpha-053": "QUARANTINED",
  "wq-alpha-054": "QUARANTINED",
  "wq-alpha-057": "QUARANTINED",
  "wq-alpha-065": "QUARANTINED",
  "wq-alpha-101": "QUARANTINED",

  // ── BRONZE — implemented, builds signals, never through backtest/OOS/demo ──
  "short-term-reversal": "BRONZE",
  "opening-range-reversal": "QUARANTINED",
  "opening-stop-hunt": "BRONZE",
  "ict-narrative": "BRONZE",
  "ict-sweep-reversion": "BRONZE",
  "ict-breakout": "BRONZE",
  "expiry-flow": "BRONZE",
  "pairs-trading": "BRONZE",
  "volatility-regime": "BRONZE",
  "bollinger-squeeze": "BRONZE",
  "donchian-breakout": "BRONZE",
  "prop-fvg-scalp": "BRONZE",
  "prop-liq-grab": "BRONZE",
  "prop-orb-scalp": "BRONZE",
  "prop-vwap-bounce": "BRONZE",
  "prop-momentum-scalp": "BRONZE",
  "tick-scalp": "BRONZE",
  "zscore-mean-rev": "BRONZE",
  "open-drive-fade": "BRONZE",
  "time-based-exit": "BRONZE",
  "range-bound-scalp": "BRONZE",
  "drift-regime-csm": "BRONZE",
  "hmm-pairs-arb": "BRONZE",
  "gamma-stability": "BRONZE",
  "llm-momentum-gate": "BRONZE",
  "two-level-uncertainty": "BRONZE",
  "llm-ga-evolutionary": "BRONZE",
  "drawdown-momentum": "BRONZE",
  "push-response-anomaly": "BRONZE",
  "intraday-momentum": "BRONZE",
  "optimal-cost-pairs": "BRONZE",
  "network-momentum": "BRONZE",
  "vol-targeted-momentum": "BRONZE",
  "capitulation-score": "BRONZE",
  "event-spike-fade": "BRONZE",
  "post-news-settlement": "BRONZE",
  "options-selling-framework": "BRONZE",
  "kronos-direction": "BRONZE",
  "gap-fade-regime": "BRONZE",
  "monthly-seasonality": "BRONZE",
  "regime-locked-momentum": "BRONZE",
  "rsi2-mean-reversion": "BRONZE",
  "vol-risk-premium": "BRONZE",
  "cot-positioning": "BRONZE",
  "vix-term-structure": "BRONZE",
  "cpi-reaction": "BRONZE",
  "opec-fade": "BRONZE",
  "eia-inventory": "BRONZE",
  "gamma-pin": "BRONZE",
  "wq-alpha-009-rust": "BRONZE",
  "wq-alpha-001-rust": "BRONZE",
  "wq-alpha-012-rust": "BRONZE",
  "wq-alpha-009": "QUARANTINED",
  "wq-alpha-012": "QUARANTINED",
  "wq-alpha-021": "QUARANTINED",
  "wq-alpha-049": "QUARANTINED",
  "wq-alpha-083": "QUARANTINED",
  "orb-breakout": "BRONZE"
};

/**
 * Get the real classification for any strategy.
 * Returns the truth — always.
 */
export function getClassification(id: SupportedStrategyId): Classification {
  return STRATEGY_CLASSIFICATION[id] ?? "SKELETON";
}

/**
 * Filter strategies that should actually be considered for execution.
 * Only GOLD and SILVER strategies can execute.
 * BRONZE can be tested but not executed.
 * SKELETON and QUARANTINED are blocked.
 */
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
