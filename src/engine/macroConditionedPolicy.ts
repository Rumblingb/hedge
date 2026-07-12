import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { Bar, LabConfig, MacroContextSnapshot, StrategyContributionSummary, TradeRecord } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { loadLatestFreeMacroContextSnapshot } from "../research/freeMacroContext.js";
import { RESEARCH_PROFILES, mergeProfile } from "../research/profiles.js";
import { buildDefaultEnsemble } from "../strategies/wctcEnsemble.js";
import { runBacktest } from "./backtest.js";
import { summarizeTrades } from "./report.js";

export interface MacroConditionedPolicyCandidate {
  profileId: string;
  symbol: string;
  strategyId: string;
  macroGate: {
    riskRegime: MacroContextSnapshot["riskRegime"];
    vixTermStructure: MacroContextSnapshot["vixTermStructure"];
    creditRiskProxy: MacroContextSnapshot["creditRiskProxy"];
    equityTrendProxy: MacroContextSnapshot["equityTrendProxy"];
    maxTailScore: number | null;
  };
  action: "paper-allow" | "shadow-only" | "disable";
  score: number;
  trades: number;
  netTotalR: number;
  averageR: number;
  winRate: number;
  profitFactor: number;
  sharpePerTrade: number;
  cvar95TradeR: number;
  riskOfRuinProb: number;
  maxConsecutiveLosses: number;
  rationale: string[];
}

export interface MacroConditionedPolicyReport {
  command: "macro-conditioned-policy";
  generatedAt: string;
  mode: "paper-only";
  csvPath: string;
  outputPath: string;
  macroContext: MacroContextSnapshot | null;
  gates: {
    macroJoined: boolean;
    liveExecutionDisabled: boolean;
    futuresDemoDisabled: boolean;
    minTradesPerLeaf: number;
    hardStopDailyLossR: number;
    hardStopMaxConsecutiveLosses: number;
  };
  status: "candidate-ready" | "shadow-only" | "blocked";
  selected: MacroConditionedPolicyCandidate | null;
  candidates: MacroConditionedPolicyCandidate[];
  rejectedLeaves: MacroConditionedPolicyCandidate[];
  policyPatch: {
    RH_ENABLED_STRATEGIES?: string;
    RH_ALLOWED_SYMBOLS?: string;
    RH_MAX_CONTRACTS: number;
    RH_MAX_TRADES_PER_DAY: number;
    RH_MAX_DAILY_LOSS_R: number;
    RH_MAX_CONSECUTIVE_LOSSES: number;
    BILL_PREOPEN_POLICY_PROFILE_ID?: string;
    BILL_PREOPEN_MACRO_RISK_REGIME?: string;
    BILL_PREOPEN_VIX_TERM_STRUCTURE?: string;
  };
  preOpenRunbook: string[];
  llmBoundary: string[];
  blockers: string[];
}

function round(value: number, digits = 4): number {
  return Number(value.toFixed(digits));
}

function leafParts(leafId: string): { symbol: string; strategyId: string } {
  const [symbol, ...rest] = leafId.split(":");
  const strategyId = rest.at(-1) ?? rest.join(":") ?? "unknown";
  return {
    symbol: symbol || "UNKNOWN",
    strategyId
  };
}

function candidateScore(summary: StrategyContributionSummary, minTrades: number): number {
  const support = Math.min(1, summary.trades / Math.max(1, minTrades));
  const expectancy = Math.max(-1, Math.min(1.5, summary.averageR));
  const profitFactor = Math.min(1.5, Math.max(0, summary.profitFactor - 1));
  const sharpe = Math.max(-0.5, Math.min(1, summary.sharpePerTrade));
  const tailPenalty = Math.min(1, Math.abs(Math.min(0, summary.cvar95TradeR)) / 2.5);
  const ruinPenalty = Math.min(1, summary.riskOfRuinProb);
  const streakPenalty = Math.min(1, Math.max(0, summary.maxConsecutiveLosses - 1) / 3);

  return round(
    (expectancy * 0.34) +
    (profitFactor * 0.2) +
    (sharpe * 0.14) +
    (support * 0.18) -
    (tailPenalty * 0.18) -
    (ruinPenalty * 0.22) -
    (streakPenalty * 0.12)
  );
}

function classifyCandidate(args: {
  summary: StrategyContributionSummary;
  score: number;
  minTrades: number;
}): MacroConditionedPolicyCandidate["action"] {
  const { summary, score, minTrades } = args;
  if (summary.netTotalR <= 0 || summary.averageR <= 0 || summary.riskOfRuinProb > 0.35) {
    return "disable";
  }
  if (summary.trades < minTrades || summary.maxConsecutiveLosses > 2 || score < 0.35) {
    return "shadow-only";
  }
  return "paper-allow";
}

function macroGateFor(macroContext: MacroContextSnapshot | null): MacroConditionedPolicyCandidate["macroGate"] {
  return {
    riskRegime: macroContext?.riskRegime ?? "unknown",
    vixTermStructure: macroContext?.vixTermStructure ?? "unknown",
    creditRiskProxy: macroContext?.creditRiskProxy ?? "unknown",
    equityTrendProxy: macroContext?.equityTrendProxy ?? "unknown",
    maxTailScore: macroContext?.tailScore ?? null
  };
}

function buildCandidate(args: {
  profileId: string;
  leafId: string;
  summary: StrategyContributionSummary;
  macroContext: MacroContextSnapshot | null;
  minTrades: number;
}): MacroConditionedPolicyCandidate {
  const parts = leafParts(args.leafId);
  const score = candidateScore(args.summary, args.minTrades);
  const action = classifyCandidate({
    summary: args.summary,
    score,
    minTrades: args.minTrades
  });

  return {
    profileId: args.profileId,
    symbol: parts.symbol,
    strategyId: parts.strategyId,
    macroGate: macroGateFor(args.macroContext),
    action,
    score,
    trades: args.summary.trades,
    netTotalR: args.summary.netTotalR,
    averageR: args.summary.averageR,
    winRate: args.summary.winRate,
    profitFactor: args.summary.profitFactor,
    sharpePerTrade: args.summary.sharpePerTrade,
    cvar95TradeR: args.summary.cvar95TradeR,
    riskOfRuinProb: args.summary.riskOfRuinProb,
    maxConsecutiveLosses: args.summary.maxConsecutiveLosses,
    rationale: [
      `Leaf ${parts.symbol}/${parts.strategyId} produced ${args.summary.trades} net-costed trades in this macro-conditioned run.`,
      `Expectancy ${args.summary.averageR.toFixed(4)}R, net ${args.summary.netTotalR.toFixed(2)}R, win rate ${(args.summary.winRate * 100).toFixed(1)}%.`,
      `Tail controls: CVaR95 ${args.summary.cvar95TradeR.toFixed(2)}R, risk-of-ruin ${args.summary.riskOfRuinProb.toFixed(2)}, max consecutive losses ${args.summary.maxConsecutiveLosses}.`,
      `Macro gate: ${args.macroContext?.riskRegime ?? "unknown"} risk, ${args.macroContext?.vixTermStructure ?? "unknown"} VIX curve, tail score ${args.macroContext?.tailScore ?? "unknown"}.`
    ]
  };
}

function compareCandidates(left: MacroConditionedPolicyCandidate, right: MacroConditionedPolicyCandidate): number {
  const actionRank = { "paper-allow": 3, "shadow-only": 2, disable: 1 } as const;
  return actionRank[right.action] - actionRank[left.action]
    || right.score - left.score
    || right.averageR - left.averageR
    || right.trades - left.trades
    || left.riskOfRuinProb - right.riskOfRuinProb;
}

export async function runMacroConditionedPolicyLab(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
  csvPath?: string;
  outputPath?: string;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  macroContext?: MacroContextSnapshot | null;
  minTradesPerLeaf?: number;
}): Promise<MacroConditionedPolicyReport> {
  const env = args.env ?? process.env;
  const outputPath = resolve(args.outputPath ?? env.BILL_MACRO_CONDITIONED_POLICY_PATH ?? ".rumbling-hedge/state/macro-conditioned-policy.latest.json");
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const macroContext = args.macroContext ?? await loadLatestFreeMacroContextSnapshot({ env });
  const configuredMinTradesPerLeaf = args.minTradesPerLeaf ?? Number.parseInt(env.BILL_MACRO_POLICY_MIN_TRADES_PER_LEAF ?? "20", 10);
  const hardMinTradesPerLeaf = args.minTradesPerLeaf === undefined
    ? Number.parseInt(env.BILL_MACRO_POLICY_HARD_MIN_TRADES_PER_LEAF ?? "20", 10)
    : configuredMinTradesPerLeaf;
  const minTradesPerLeaf = Math.max(
    1,
    Number.isFinite(configuredMinTradesPerLeaf) ? configuredMinTradesPerLeaf : 20,
    Number.isFinite(hardMinTradesPerLeaf) ? hardMinTradesPerLeaf : 20
  );
  const configuredMaxProfiles = Number.parseInt(env.BILL_MACRO_POLICY_MAX_PROFILES ?? "32", 10);
  const maxProfiles = Number.isFinite(configuredMaxProfiles) && configuredMaxProfiles > 0
    ? configuredMaxProfiles
    : RESEARCH_PROFILES.length;
  const allCandidates: MacroConditionedPolicyCandidate[] = [];

  for (const profile of RESEARCH_PROFILES.slice(0, maxProfiles)) {
    const config = mergeProfile(args.baseConfig, profile);
    const run = await runBacktest({
      bars: args.bars,
      strategy: buildDefaultEnsemble(config),
      config,
      newsGate: args.newsGate,
      macroContext: macroContext ?? undefined
    });
    const summary = summarizeTrades(run.trades);

    for (const [leafId, leafSummary] of Object.entries(summary.byLeaf ?? {})) {
      allCandidates.push(buildCandidate({
        profileId: profile.id,
        leafId,
        summary: leafSummary,
        macroContext,
        minTrades: minTradesPerLeaf
      }));
    }
  }

  const sorted = allCandidates.sort(compareCandidates);
  const candidates = sorted.filter((candidate) => candidate.action !== "disable").slice(0, 12);
  const rejectedLeaves = sorted.filter((candidate) => candidate.action === "disable").slice(0, 12);
  const selected = candidates.find((candidate) => candidate.action === "paper-allow") ?? null;
  const approvedFuturesDemoTransport = env.BILL_ENABLE_FUTURES_DEMO_EXECUTION === "true"
    && env.RH_TOPSTEP_DEMO_ONLY !== "false"
    && Boolean(env.BILL_FUTURES_DEMO_APPROVAL_ID?.trim());
  const liveExecutionDisabled = (env.RH_LIVE_EXECUTION_ENABLED !== "true" || approvedFuturesDemoTransport)
    && env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED !== "true";
  const futuresDemoDisabled = env.BILL_ENABLE_FUTURES_DEMO_EXECUTION !== "true";
  const hardStopDailyLossR = Math.min(args.baseConfig.guardrails.maxDailyLossR, 1);
  const hardStopMaxConsecutiveLosses = Math.min(args.baseConfig.guardrails.maxConsecutiveLosses, 1);
  const blockers = [
    ...(!macroContext ? ["missing free macro context artifact"] : []),
    ...(!liveExecutionDisabled ? ["live execution is armed; policy lab refuses to promote"] : []),
    ...(!selected ? ["no strategy-symbol leaf cleared paper-allow thresholds"] : []),
    ...(selected && !futuresDemoDisabled && !approvedFuturesDemoTransport ? ["futures demo execution is enabled; keep this policy paper-only until reviewed"] : [])
  ];

  const report: MacroConditionedPolicyReport = {
    command: "macro-conditioned-policy",
    generatedAt,
    mode: "paper-only",
    csvPath: resolve(args.csvPath ?? env.BILL_STRATEGY_LAB_CSV_PATH ?? "data/free/ALL-6MARKETS-1m-5d-normalized.csv"),
    outputPath,
    macroContext,
    gates: {
      macroJoined: Boolean(macroContext),
      liveExecutionDisabled,
      futuresDemoDisabled,
      minTradesPerLeaf,
      hardStopDailyLossR,
      hardStopMaxConsecutiveLosses
    },
    status: blockers.length === 0 && selected
      ? "candidate-ready"
      : candidates.length > 0
        ? "shadow-only"
        : "blocked",
    selected,
    candidates,
    rejectedLeaves,
    policyPatch: {
      ...(selected ? {
        RH_ENABLED_STRATEGIES: selected.strategyId,
        RH_ALLOWED_SYMBOLS: selected.symbol,
        BILL_PREOPEN_POLICY_PROFILE_ID: selected.profileId,
        BILL_PREOPEN_MACRO_RISK_REGIME: selected.macroGate.riskRegime,
        BILL_PREOPEN_VIX_TERM_STRUCTURE: selected.macroGate.vixTermStructure
      } : {}),
      RH_MAX_CONTRACTS: 1,
      RH_MAX_TRADES_PER_DAY: 1,
      RH_MAX_DAILY_LOSS_R: hardStopDailyLossR,
      RH_MAX_CONSECUTIVE_LOSSES: hardStopMaxConsecutiveLosses
    },
    preOpenRunbook: [
      "Run this report about 30 minutes before the futures cash session.",
      "Refresh macro-context-free first; stale macro context makes this report advisory only.",
      "If status is candidate-ready, allow only the selected strategy/symbol in paper or reviewed demo.",
      "Stop for the day after one realized loss, one daily-loss breach, kill-switch on, data-quality failure, or prediction-market/liquidity anomaly.",
      "LLMs may summarize why the policy was selected, but may not override the policy patch, hard stops, or live-execution flags."
    ],
    llmBoundary: [
      "LLMs are observers, not portfolio managers.",
      "LLM output is treated as untrusted text unless converted into a deterministic policy and revalidated.",
      "Known failure modes: hallucinated catalysts, stale data, narrative overfit, hidden prompt injection in scraped research, and false certainty around low-liquidity markets.",
      "Algorithms own sizing, eligibility, hard stops, OOS thresholds, fill-cost assumptions, and execution authorization."
    ],
    blockers
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
