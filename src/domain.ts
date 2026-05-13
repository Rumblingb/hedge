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
  "carry-trade","gap-fade","event-driven","supply-demand",
  "scalping","market-open-drive","power-hour","overnight-hold",
  "news-spike-fade","cross-asset-rotation",
  "vwap-reversion","rsi-divergence","bollinger-squeeze","delta-divergence",
  "market-profile","seasonality","ichimoku","macd-crossover","keltner-channel",
  "adx-trend","donchian-breakout","inside-bar","pin-bar","engulfing-pattern",
  "stochastic","heikin-ashi","false-breakout","gamma-scalp","vol-premium",
  "renko-momentum","head-shoulders","double-top-bottom","flag-pennant",
  "wedge-breakout","breakout-retest","volume-spike","market-structure",
  "trendline-break","multi-timeframe",
  "rl-inspired","uncertainty-sizing","ensemble-meta","order-flow-imbalance",
  "hawkes-process","harnet-vol","optimal-execution","dispersion-trading",
  "pairs-convergence","implied-correlation","tail-risk","regime-probability",
  "volatility-of-vol","correlation-switch","momentum-crash","liquidity-cascade",
  "overnight-drift","pre-market-reversal","initial-balance","econ-surprise",
  "put-call-signal","dark-pool-print","block-trade-fade","auction-imbalance",
  "yield-curve-steepen","inflation-breakeven","dollar-smile","risk-parity-rebalance",
  "opening-auction","closing-auction","pre-fomc-drift","post-fomc-fade",
  "nfp-reaction","cpi-reaction","opec-fade","eia-inventory",
  "cot-positioning","vix-term-structure","gamma-pin","zero-dte-flow",
  "vol-skew","credit-spread","gold-silver-ratio","copper-gold-ratio",
  "oil-crack-spread","natgas-seasonality","btc-correlation","fed-put-strategy",
  "event-arbitrage","momentum-ignition","value-area-rotation",
  "algo-execution","cross-venue-arb",
  "prop-fvg-scalp","prop-liq-grab","prop-orb-scalp","prop-vwap-bounce",
  "prop-momentum-scalp","tick-scalp","zscore-mean-rev","open-drive-fade",
  "time-based-exit","range-bound-scalp",
  "drift-regime-csm","hmm-pairs-arb","gamma-stability",
  "llm-momentum-gate","two-level-uncertainty",
  "llm-ga-evolutionary",
  "drawdown-momentum","push-response-anomaly","intraday-momentum",
  "donchian-breakout",
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
  "vol-risk-premium"
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

  // ── BRONZE — implemented, builds signals, never backtested ──
  // These were QUARANTINED but have been structurally fixed in v2:
  "short-term-reversal": "BRONZE",
  "opening-range-reversal": "BRONZE",
  "donchian-breakout": "BRONZE",
  "bollinger-squeeze": "BRONZE",
  "capitulation-score": "BRONZE",
  "carry-trade": "BRONZE",
  "delta-divergence": "BRONZE",
  "drawdown-momentum": "BRONZE",
  "drift-regime-csm": "BRONZE",
  "event-driven": "BRONZE",
  "event-spike-fade": "BRONZE",
  "expiry-flow": "BRONZE",
  "gap-fade": "BRONZE",
  "gap-fade-regime": "BRONZE",
  "gamma-stability": "BRONZE",
  "hmm-pairs-arb": "BRONZE",
  "ichimoku": "BRONZE",
  "ict-breakout": "BRONZE",
  "ict-narrative": "BRONZE",
  "ict-sweep-reversion": "BRONZE",
  "intraday-momentum": "BRONZE",
  "kronos-direction": "BRONZE",
  "llm-ga-evolutionary": "BRONZE",
  "llm-momentum-gate": "BRONZE",
  "market-open-drive": "BRONZE",
  "market-profile": "BRONZE",
  "monthly-seasonality": "BRONZE",
  "network-momentum": "BRONZE",
  "news-spike-fade": "BRONZE",
  "opening-stop-hunt": "BRONZE",
  "optimal-cost-pairs": "BRONZE",
  "options-selling-framework": "BRONZE",
  "overnight-hold": "BRONZE",
  "pairs-trading": "BRONZE",
  "post-news-settlement": "BRONZE",
  "power-hour": "BRONZE",
  "push-response-anomaly": "BRONZE",
  "regime-locked-momentum": "BRONZE",
  "rsi2-mean-reversion": "BRONZE",
  "rsi-divergence": "BRONZE",
  "scalping": "BRONZE",
  "seasonality": "BRONZE",
  "supply-demand": "BRONZE",
  "two-level-uncertainty": "BRONZE",
  "volatility-regime": "BRONZE",
  "vol-risk-premium": "BRONZE",
  "vol-targeted-momentum": "BRONZE",

  // ── SKELETON — registered as name ONLY, no implementation file, zero logic ──
  "adx-trend": "SKELETON",
  "algo-execution": "SKELETON",
  "auction-imbalance": "SKELETON",
  "block-trade-fade": "SKELETON",
  "breakout-retest": "SKELETON",
  "btc-correlation": "SKELETON",
  "closing-auction": "SKELETON",
  "copper-gold-ratio": "SKELETON",
  "correlation-switch": "SKELETON",
  "cot-positioning": "SKELETON",
  "cpi-reaction": "SKELETON",
  "credit-spread": "SKELETON",
  "cross-asset-rotation": "SKELETON",
  "cross-venue-arb": "SKELETON",
  "dark-pool-print": "SKELETON",
  "dispersion-trading": "SKELETON",
  "dollar-smile": "SKELETON",
  "double-top-bottom": "SKELETON",
  "econ-surprise": "SKELETON",
  "eia-inventory": "SKELETON",
  "engulfing-pattern": "SKELETON",
  "ensemble-meta": "SKELETON",
  "event-arbitrage": "SKELETON",
  "false-breakout": "SKELETON",
  "fed-put-strategy": "SKELETON",
  "flag-pennant": "SKELETON",
  "gamma-pin": "SKELETON",
  "gamma-scalp": "SKELETON",
  "gold-silver-ratio": "SKELETON",
  "harnet-vol": "SKELETON",
  "hawkes-process": "SKELETON",
  "head-shoulders": "SKELETON",
  "heikin-ashi": "SKELETON",
  "implied-correlation": "SKELETON",
  "inflation-breakeven": "SKELETON",
  "initial-balance": "SKELETON",
  "inside-bar": "SKELETON",
  "keltner-channel": "SKELETON",
  "liquidity-cascade": "SKELETON",
  "macd-crossover": "SKELETON",
  "market-structure": "SKELETON",
  "momentum-crash": "SKELETON",
  "momentum-ignition": "SKELETON",
  "multi-timeframe": "SKELETON",
  "natgas-seasonality": "SKELETON",
  "nfp-reaction": "SKELETON",
  "oil-crack-spread": "SKELETON",
  "opec-fade": "SKELETON",
  "open-drive-fade": "SKELETON",
  "opening-auction": "SKELETON",
  "optimal-execution": "SKELETON",
  "order-flow-imbalance": "SKELETON",
  "overnight-drift": "SKELETON",
  "pairs-convergence": "SKELETON",
  "pin-bar": "SKELETON",
  "post-fomc-fade": "SKELETON",
  "pre-fomc-drift": "SKELETON",
  "pre-market-reversal": "SKELETON",
  "prop-fvg-scalp": "SKELETON",
  "prop-liq-grab": "SKELETON",
  "prop-momentum-scalp": "SKELETON",
  "prop-orb-scalp": "SKELETON",
  "prop-vwap-bounce": "SKELETON",
  "put-call-signal": "SKELETON",
  "range-bound-scalp": "SKELETON",
  "regime-probability": "SKELETON",
  "renko-momentum": "SKELETON",
  "risk-parity-rebalance": "SKELETON",
  "rl-inspired": "SKELETON",
  "stochastic": "SKELETON",
  "tail-risk": "SKELETON",
  "tick-scalp": "SKELETON",
  "time-based-exit": "SKELETON",
  "trendline-break": "SKELETON",
  "uncertainty-sizing": "SKELETON",
  "value-area-rotation": "SKELETON",
  "vix-term-structure": "SKELETON",
  "vol-premium": "SKELETON",
  "vol-skew": "SKELETON",
  "volatility-of-vol": "SKELETON",
  "volume-spike": "SKELETON",
  "wedge-breakout": "SKELETON",
  "wq-alpha-009": "SKELETON",
  "wq-alpha-012": "SKELETON",
  "wq-alpha-021": "SKELETON",
  "wq-alpha-049": "SKELETON",
  "wq-alpha-083": "SKELETON",
  "yield-curve-steepen": "SKELETON",
  "zero-dte-flow": "SKELETON",
  "zscore-mean-rev": "SKELETON"
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
