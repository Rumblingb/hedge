import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { Bar, LabConfig, StrategyContributionSummary, SummaryReport, TradeRecord } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { mergeProfile, RESEARCH_PROFILES, type ResearchProfile } from "../research/profiles.js";
import { buildDefaultEnsemble } from "../strategies/wctcEnsemble.js";
import { runBacktest } from "./backtest.js";
import { summarizeTrades } from "./report.js";
import { runWalkforwardResearch, type WalkforwardProfileResult } from "./walkforward.js";

export interface StrategyResearchContractReport {
  command: "strategy-research-contracts";
  generatedAt: string;
  status: "edge-candidate" | "research-only" | "reject-current-stack";
  outputPath: string;
  csvPath: string;
  contract: {
    objective: string;
    constraints: string[];
    validation: string[];
    rejectionCondition: string;
  };
  researchPriors: Array<{
    theme: string;
    institutionOrSource: string;
    implication: string;
    stackAction: string;
  }>;
  imageFeedAudit: Array<{
    source: string;
    use: string;
    decision: "plug-now" | "catalog-only" | "reject-for-now";
    reason: string;
  }>;
  walkforward: {
    winnerProfileId: string | null;
    deployableProfileId: string | null;
    profileDiagnostics: ProfileDiagnosis[];
  };
  strategyDiagnostics: StrategyDiagnosis[];
  segmentDiagnostics: SegmentDiagnosis[];
  hypotheses: ResearchHypothesisDiagnosis[];
  decisions: string[];
  nextExperiments: string[];
}

export interface ProfileDiagnosis {
  profileId: string;
  status: "candidate" | "decayed" | "no-edge" | "too-thin" | "blocked";
  trainTrades: number;
  testTrades: number;
  trainNetR: number;
  testNetR: number;
  testProfitFactor: number;
  testSharpePerTrade: number;
  testMaxDrawdownR: number;
  testExpectancyR: number;
  scoreStability: number;
  failureModes: string[];
  recommendation: string;
}

export interface StrategyDiagnosis {
  strategyId: string;
  trades: number;
  netTotalR: number;
  averageR: number;
  profitFactor: number;
  sharpePerTrade: number;
  maxConsecutiveLosses: number;
  status: "candidate" | "incubate" | "kill";
  reason: string;
}

export interface SegmentDiagnosis {
  segment: string;
  trades: number;
  netTotalR: number;
  averageR: number;
  profitFactor: number;
  status: "use-as-filter" | "insufficient" | "avoid";
}

export interface ResearchHypothesisDiagnosis {
  id: string;
  objective: string;
  observed: string;
  verdict: "test-next" | "reject" | "already-covered";
  nextTest: string;
}

export interface SurvivalMetrics {
  terminalWealthQ05: number;
  deflatedOOS: number;
  walkforwardWindows: number;
  profitableWindows: number;
  permittedBreachProportion: number; // default 0.1
  maxDrawdown: number;
  calmarRatio: number;
}

export function evaluateSurvival(metrics: SurvivalMetrics): {
  passed: boolean;
  violations: string[];
  score: number;
} {
  let score = 1.0;
  const violations: string[] = [];

  if (metrics.terminalWealthQ05 <= 0) {
    score -= 0.2;
    violations.push("terminalWealthQ05 must be > 0");
  }

  if (metrics.deflatedOOS <= 0) {
    score -= 0.2;
    violations.push("deflatedOOS must be > 0");
  }

  const breachRatio = metrics.walkforwardWindows > 0 
    ? metrics.profitableWindows / metrics.walkforwardWindows 
    : 0;
  
  if (breachRatio < (1 - metrics.permittedBreachProportion)) {
    score -= 0.2;
    violations.push(`profitableWindows/walkforwardWindows (${breachRatio.toFixed(2)}) must be >= ${(1 - metrics.permittedBreachProportion).toFixed(2)}`);
  }

  if (metrics.maxDrawdown >= -0.25) {
    score -= 0.2;
    violations.push("maxDrawdown must be < -0.25 (25%)");
  }

  if (metrics.calmarRatio <= 0.5) {
    score -= 0.2;
    violations.push("calmarRatio should be > 0.5");
  }

  // Ensure score doesn't go below 0
  score = Math.max(0, score);

  return {
    passed: score >= 0.4, // At least SILVER level to pass
    violations,
    score
  };
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/strategy-research-contracts.latest.json";

function round(value: number): number {
  return Number(value.toFixed(4));
}

function finite(value: number | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function diagnoseProfile(profile: WalkforwardProfileResult): ProfileDiagnosis {
  const train = profile.trainSummary;
  const test = profile.testSummary;
  const failureModes = [
    ...(test.totalTrades < 20 ? ["sample-too-thin"] : []),
    ...(train.tradeQuality.expectancyR > 0 && test.tradeQuality.expectancyR <= 0 ? ["edge-decay"] : []),
    ...(train.netTotalR > 0 && test.netTotalR <= 0 ? ["train-test-break"] : []),
    ...(test.grossTotalR > 0 && test.netTotalR <= 0 ? ["costs-erased-gross-edge"] : []),
    ...(test.profitFactor < 1.4 ? ["profit-factor-below-contract"] : []),
    ...(test.tradeQuality.sharpePerTrade < 0.15 ? ["weak-risk-adjusted-return"] : []),
    ...(test.maxDrawdownR > 4 ? ["drawdown-too-high"] : []),
    ...(profile.scoreStability < 0.55 ? ["unstable-walkforward-splits"] : [])
  ];
  const status: ProfileDiagnosis["status"] = test.totalTrades < 8
    ? "too-thin"
    : train.tradeQuality.expectancyR <= 0 && test.tradeQuality.expectancyR <= 0
      ? "no-edge"
      : failureModes.includes("edge-decay") || failureModes.includes("train-test-break")
        ? "decayed"
        : failureModes.length === 0
          ? "candidate"
          : "blocked";

  return {
    profileId: profile.profileId,
    status,
    trainTrades: train.totalTrades,
    testTrades: test.totalTrades,
    trainNetR: round(train.netTotalR),
    testNetR: round(test.netTotalR),
    testProfitFactor: round(test.profitFactor),
    testSharpePerTrade: round(test.tradeQuality.sharpePerTrade),
    testMaxDrawdownR: round(test.maxDrawdownR),
    testExpectancyR: round(test.tradeQuality.expectancyR),
    scoreStability: profile.scoreStability,
    failureModes,
    recommendation: status === "candidate"
      ? "Keep as a candidate, then demand rolling OOS and stressed live-readiness."
      : status === "decayed"
        ? "Treat as decayed: preserve the setup, but test regime/session/volume filters before any routing."
        : status === "no-edge"
          ? "Kill from first-lane promotion unless a new independent filter creates OOS expectancy."
          : status === "too-thin"
            ? "Collect more demo/shadow observations before judging."
            : "Research-only until the named failure modes are repaired."
  };
}

function strategyStatus(item: StrategyContributionSummary): StrategyDiagnosis["status"] {
  if (item.trades >= 20 && item.netTotalR <= 0 && item.profitFactor < 1) return "kill";
  if (item.trades >= 20 && item.averageR > 0 && item.profitFactor >= 1.25 && item.sharpePerTrade > 0.05) return "candidate";
  return "incubate";
}

function diagnoseStrategies(summary: SummaryReport): StrategyDiagnosis[] {
  return Object.entries(summary.byStrategy)
    .map(([strategyId, item]) => {
      const status = strategyStatus(item);
      return {
        strategyId,
        trades: item.trades,
        netTotalR: round(item.netTotalR),
        averageR: round(item.averageR),
        profitFactor: round(item.profitFactor),
        sharpePerTrade: round(item.sharpePerTrade),
        maxConsecutiveLosses: item.maxConsecutiveLosses,
        status,
        reason: status === "kill"
          ? "Large enough sample is net negative after costs."
          : status === "candidate"
            ? "Positive after costs with acceptable profit factor and risk-adjusted return."
            : "Not enough robust evidence; keep in research/demos only."
      };
    })
    .sort((left, right) => right.netTotalR - left.netTotalR);
}

function metaNumber(trade: TradeRecord, key: string): number {
  const value = trade.meta?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function summarizeSegment(label: string, trades: TradeRecord[]): SegmentDiagnosis {
  const summary = summarizeTrades(trades);
  const status: SegmentDiagnosis["status"] = trades.length < 8
    ? "insufficient"
    : summary.netTotalR > 0 && summary.profitFactor >= 1.2
      ? "use-as-filter"
      : "avoid";
  return {
    segment: label,
    trades: summary.totalTrades,
    netTotalR: round(summary.netTotalR),
    averageR: round(summary.netAverageR),
    profitFactor: round(summary.profitFactor),
    status
  };
}

function segmentDiagnostics(trades: TradeRecord[]): SegmentDiagnosis[] {
  const buckets: Array<{ label: string; predicate: (trade: TradeRecord) => boolean }> = [
    { label: "session:first-30m", predicate: (trade) => String(trade.meta?.entrySessionBucket ?? "") === "first-30m" },
    { label: "session:30-90m", predicate: (trade) => String(trade.meta?.entrySessionBucket ?? "") === "30-90m" },
    { label: "session:90-180m", predicate: (trade) => String(trade.meta?.entrySessionBucket ?? "") === "90-180m" },
    { label: "volume:above-1.2x-20bar", predicate: (trade) => metaNumber(trade, "entryVolumeRatio20") >= 1.2 },
    { label: "volume:below-0.8x-20bar", predicate: (trade) => metaNumber(trade, "entryVolumeRatio20") > 0 && metaNumber(trade, "entryVolumeRatio20") <= 0.8 },
    { label: "volatility:range-below-1atr", predicate: (trade) => metaNumber(trade, "entryRangeAtr") > 0 && metaNumber(trade, "entryRangeAtr") <= 1 },
    { label: "volatility:range-above-1.5atr", predicate: (trade) => metaNumber(trade, "entryRangeAtr") >= 1.5 }
  ];

  return buckets
    .map((bucket) => summarizeSegment(bucket.label, trades.filter(bucket.predicate)))
    .sort((left, right) => right.netTotalR - left.netTotalR);
}

function buildHypotheses(args: {
  profiles: ProfileDiagnosis[];
  segments: SegmentDiagnosis[];
  strategies: StrategyDiagnosis[];
}): ResearchHypothesisDiagnosis[] {
  const usefulSegments = args.segments.filter((segment) => segment.status === "use-as-filter").map((segment) => segment.segment);
  const killedStrategies = args.strategies.filter((strategy) => strategy.status === "kill").map((strategy) => strategy.strategyId);
  const decayed = args.profiles.filter((profile) => profile.status === "decayed").map((profile) => profile.profileId);

  return [
    {
      id: "volatility-filter",
      objective: "Reduce drawdown and false breakout exposure without accepting lower net expectancy.",
      observed: usefulSegments.some((segment) => segment.startsWith("volatility:"))
        ? `Useful volatility segment found: ${usefulSegments.filter((segment) => segment.startsWith("volatility:")).join(", ")}.`
        : "No volatility segment currently clears enough positive evidence.",
      verdict: usefulSegments.some((segment) => segment.startsWith("volatility:")) ? "test-next" : "reject",
      nextTest: "Create a profile variant that only admits the useful volatility bucket, then require rolling OOS."
    },
    {
      id: "volume-confirmation",
      objective: "Require participation confirmation before continuation or displacement entries.",
      observed: usefulSegments.some((segment) => segment.startsWith("volume:"))
        ? `Useful volume segment found: ${usefulSegments.filter((segment) => segment.startsWith("volume:")).join(", ")}.`
        : "Volume confirmation is plausible but not yet proven by the current trade sample.",
      verdict: usefulSegments.some((segment) => segment.startsWith("volume:")) ? "test-next" : "reject",
      nextTest: "Test momentum/displacement variants with entryVolumeRatio20 thresholds at 1.0, 1.2, and 1.5."
    },
    {
      id: "session-filter",
      objective: "Find whether edge exists only in a session bucket rather than across all allowed hours.",
      observed: usefulSegments.some((segment) => segment.startsWith("session:"))
        ? `Useful session segment found: ${usefulSegments.filter((segment) => segment.startsWith("session:")).join(", ")}.`
        : "No session bucket currently justifies promotion.",
      verdict: usefulSegments.some((segment) => segment.startsWith("session:")) ? "test-next" : "reject",
      nextTest: "Split first 30m, 30-90m, and 90-180m into separate research profiles with no cross-bucket pooling."
    },
    {
      id: "strategy-kill-list",
      objective: "Stop spending runtime on strategies with negative evidence after costs.",
      observed: killedStrategies.length > 0 ? `Kill-list candidates: ${killedStrategies.join(", ")}.` : "No strategy has enough negative sample to force a permanent kill.",
      verdict: killedStrategies.length > 0 ? "test-next" : "already-covered",
      nextTest: "Remove kill-list strategies from first-lane promotion and keep them shadow-only until a new independent filter repairs OOS expectancy."
    },
    {
      id: "decay-analysis",
      objective: "Separate real edge decay from luck by comparing train/test expectancy and split stability.",
      observed: decayed.length > 0 ? `Decayed profiles: ${decayed.join(", ")}.` : "Current failures look more like no-edge/thin-sample than classic train-positive/test-negative decay.",
      verdict: decayed.length > 0 ? "test-next" : "already-covered",
      nextTest: "For decayed profiles, test whether volatility/session/volume filters explain the break before retuning entries."
    }
  ];
}

function bestProfileForBacktest(researchProfiles: WalkforwardProfileResult[]): ResearchProfile {
  const winnerId = researchProfiles[0]?.profileId;
  return RESEARCH_PROFILES.find((profile) => profile.id === winnerId) ?? RESEARCH_PROFILES[0]!;
}

export async function buildStrategyResearchContracts(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
  csvPath: string;
  outputPath?: string;
  profiles?: ResearchProfile[];
  now?: () => string;
}): Promise<StrategyResearchContractReport> {
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? process.env.BILL_STRATEGY_RESEARCH_CONTRACTS_PATH ?? DEFAULT_OUTPUT_PATH);
  const research = await runWalkforwardResearch({
    baseConfig: args.baseConfig,
    bars: args.bars,
    newsGate: args.newsGate,
    profiles: args.profiles
  });
  const profileDiagnostics = research.profiles.map(diagnoseProfile);
  const backtestProfile = bestProfileForBacktest(research.profiles);
  const backtestConfig = mergeProfile(args.baseConfig, backtestProfile);
  const backtest = await runBacktest({
    bars: args.bars,
    strategy: buildDefaultEnsemble(backtestConfig),
    config: backtestConfig,
    newsGate: args.newsGate
  });
  const summary = summarizeTrades(backtest.trades);
  const strategyDiagnostics = diagnoseStrategies(summary);
  const segments = segmentDiagnostics(backtest.trades);
  const hypotheses = buildHypotheses({
    profiles: profileDiagnostics,
    segments,
    strategies: strategyDiagnostics
  });
  const candidates = profileDiagnostics.filter((profile) => profile.status === "candidate");
  const status: StrategyResearchContractReport["status"] = research.deployableWinner
    ? "edge-candidate"
    : candidates.length > 0
      ? "research-only"
      : "reject-current-stack";

  const report: StrategyResearchContractReport = {
    command: "strategy-research-contracts",
    generatedAt,
    status,
    outputPath,
    csvPath: resolve(args.csvPath),
    contract: {
      objective: "Find a futures strategy edge that improves OOS risk-adjusted return while surviving costs, slippage, drawdown, regime splits, and walk-forward validation.",
      constraints: [
        "No live-money promotion from in-sample or single-window performance.",
        "Include fees, slippage, latency, spread, and stress buffer already modeled in the backtest engine.",
        "Require Topstep-compatible day-trading guardrails and one-contract starter sizing.",
        "A rejected strategy is a valid successful research outcome."
      ],
      validation: [
        "Walk-forward profile ranking with train/test separation.",
        "Rolling OOS and stressed live-readiness before paper/demo routing.",
        "Segment checks for volatility, volume, and session failure modes.",
        "Strategy kill/incubate/candidate decisions after costs."
      ],
      rejectionCondition: "Reject any candidate that cannot show positive OOS expectancy, profit factor >= 1.4, acceptable drawdown, and enough observations without overfitting."
    },
    researchPriors: [
      {
        theme: "trend following and time-series momentum",
        institutionOrSource: "AQR / managed-futures literature",
        implication: "Momentum can work, but only with diversification, risk control, and long OOS histories.",
        stackAction: "Keep session momentum as a hypothesis, not a default edge."
      },
      {
        theme: "volatility-managed exposure",
        institutionOrSource: "Academic volatility-managed portfolio research",
        implication: "Volatility scaling/filtering can improve Sharpe and drawdown when volatility predicts risk more than return.",
        stackAction: "Test volatility buckets before changing entries."
      },
      {
        theme: "realized-volatility forecasting",
        institutionOrSource: "Oxford-Man / realized volatility research",
        implication: "ATR proxies are a starter; realized volatility regime labels should become first-class features.",
        stackAction: "Promote entryAtrPct and entryRangeAtr from diagnostics into candidate filters only after OOS proof."
      },
      {
        theme: "microstructure and volume participation",
        institutionOrSource: "market microstructure literature across US, China, and India",
        implication: "Volume and session effects can be real, but they decay quickly and are vulnerable to costs.",
        stackAction: "Treat volume confirmation as a measurable filter, not a narrative."
      }
    ],
    imageFeedAudit: [
      {
        source: "swpc.noaa.gov",
        use: "solar/geomagnetic storm veto for abnormal risk days",
        decision: "catalog-only",
        reason: "Free and useful as a context veto, but not yet tied to a measured failure mode."
      },
      {
        source: "earthquake.usgs.gov",
        use: "major shock/event context for commodities and regional risk",
        decision: "catalog-only",
        reason: "Free API; useful for macro context, not a first-lane futures edge by itself."
      },
      {
        source: "opensky-network.org",
        use: "global air-traffic disruption proxy",
        decision: "catalog-only",
        reason: "Potential supply-chain/geopolitical feature; should not enter trading logic until tied to an OOS hypothesis."
      },
      {
        source: "firms.modaps.eosdis.nasa.gov",
        use: "wildfire/supply disruption context",
        decision: "catalog-only",
        reason: "Free NASA source, better suited to commodity/macro context than intraday index execution."
      },
      {
        source: "mempool.space",
        use: "Bitcoin network congestion context",
        decision: "reject-for-now",
        reason: "Relevant to crypto/prediction lanes, not the current Topstep futures research contract."
      }
    ],
    walkforward: {
      winnerProfileId: research.winner?.profileId ?? null,
      deployableProfileId: research.deployableWinner?.profileId ?? null,
      profileDiagnostics
    },
    strategyDiagnostics,
    segmentDiagnostics: segments,
    hypotheses,
    decisions: [
      ...(status === "reject-current-stack" ? ["Do not widen demo routing because the current strategy stack has no deployable edge."] : []),
      ...strategyDiagnostics.filter((strategy) => strategy.status === "kill").map((strategy) => `Kill or shadow-only: ${strategy.strategyId}.`),
      ...segments.filter((segment) => segment.status === "use-as-filter").map((segment) => `Promote to next experiment only: ${segment.segment}.`)
    ],
    nextExperiments: [
      "Run separate volatility, volume, and session-filtered profiles instead of retuning all parameters together.",
      "Require each candidate to beat the research contract on at least four rolling OOS windows.",
      "Apply survival-constrained KPIs: terminalWealthQ05 > 0, deflatedOOS > 0, Calmar > 0.5, maxDD < 25%.",
      "Use permittedBreachProportion of 0.1 (allow 1 in 10 walkforward windows to fail).",
    ],
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
