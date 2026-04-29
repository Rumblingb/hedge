import { SUPPORTED_STRATEGY_IDS, type Bar, type LabConfig, type SupportedStrategyId } from "../domain.js";
import { buildAgenticFundReport } from "./agenticFund.js";
import type { WalkforwardResearchResult } from "./walkforward.js";
import { runWalkforwardResearch } from "./walkforward.js";
import type { NewsGate } from "../news/base.js";

interface AppliedPatch {
  RH_MIN_RR?: number;
  RH_MAX_CONTRACTS?: number;
  RH_MAX_TRADES_PER_DAY?: number;
  RH_MAX_DAILY_LOSS_R?: number;
  RH_ENABLED_STRATEGIES?: string;
}

function hasAppliedPatchChanges(patch: AppliedPatch): boolean {
  return Object.values(patch).some((value) => value !== undefined);
}

function priorityRank(priority: "now" | "next" | "later"): number {
  if (priority === "now") {
    return 0;
  }
  if (priority === "next") {
    return 1;
  }
  return 2;
}

function parseEnabledStrategies(raw: string | undefined): SupportedStrategyId[] {
  if (!raw) {
    return [];
  }

  const supported = new Set<string>(SUPPORTED_STRATEGY_IDS);
  return Array.from(new Set(
    raw
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter((value): value is SupportedStrategyId => supported.has(value))
  ));
}

function mergeStrategyPatch(current: string | undefined, next: string | undefined): string | undefined {
  const nextStrategies = parseEnabledStrategies(next);
  if (nextStrategies.length === 0) {
    return current;
  }

  if (!current) {
    return nextStrategies.join(",");
  }

  const currentStrategies = parseEnabledStrategies(current);
  const nextSet = new Set(nextStrategies);
  const intersection = currentStrategies.filter((strategyId) => nextSet.has(strategyId));
  return (intersection.length > 0 ? intersection : nextStrategies).join(",");
}

function deriveAppliedPatch(args: {
  baseConfig: LabConfig;
  report: ReturnType<typeof buildAgenticFundReport>;
}): AppliedPatch {
  const { baseConfig, report } = args;
  const patch: AppliedPatch = {};
  const actions = [...report.learningActions]
    .sort((left, right) => priorityRank(left.priority) - priorityRank(right.priority));

  for (const action of actions) {
    if (action.priority === "later") {
      continue;
    }

    const envPatch = action.envPatch;
    if (typeof envPatch.RH_MIN_RR === "number") {
      patch.RH_MIN_RR = patch.RH_MIN_RR === undefined
        ? Math.max(baseConfig.guardrails.minRr, envPatch.RH_MIN_RR)
        : Math.max(patch.RH_MIN_RR, envPatch.RH_MIN_RR);
    }
    if (typeof envPatch.RH_MAX_CONTRACTS === "number") {
      patch.RH_MAX_CONTRACTS = patch.RH_MAX_CONTRACTS === undefined
        ? Math.min(baseConfig.guardrails.maxContracts, envPatch.RH_MAX_CONTRACTS)
        : Math.min(patch.RH_MAX_CONTRACTS, envPatch.RH_MAX_CONTRACTS);
    }
    if (typeof envPatch.RH_MAX_TRADES_PER_DAY === "number") {
      patch.RH_MAX_TRADES_PER_DAY = patch.RH_MAX_TRADES_PER_DAY === undefined
        ? Math.min(baseConfig.guardrails.maxTradesPerDay, envPatch.RH_MAX_TRADES_PER_DAY)
        : Math.min(patch.RH_MAX_TRADES_PER_DAY, envPatch.RH_MAX_TRADES_PER_DAY);
    }
    if (typeof envPatch.RH_MAX_DAILY_LOSS_R === "number") {
      patch.RH_MAX_DAILY_LOSS_R = patch.RH_MAX_DAILY_LOSS_R === undefined
        ? Math.min(baseConfig.guardrails.maxDailyLossR, envPatch.RH_MAX_DAILY_LOSS_R)
        : Math.min(patch.RH_MAX_DAILY_LOSS_R, envPatch.RH_MAX_DAILY_LOSS_R);
    }
    if (typeof envPatch.RH_ENABLED_STRATEGIES === "string") {
      patch.RH_ENABLED_STRATEGIES = mergeStrategyPatch(
        patch.RH_ENABLED_STRATEGIES,
        envPatch.RH_ENABLED_STRATEGIES
      );
    }
  }

  return patch;
}

function applyPatchToConfig(args: {
  baseConfig: LabConfig;
  patch: AppliedPatch;
}): LabConfig {
  const { baseConfig, patch } = args;

  return {
    ...baseConfig,
    enabledStrategies: parseEnabledStrategies(patch.RH_ENABLED_STRATEGIES).length > 0
      ? parseEnabledStrategies(patch.RH_ENABLED_STRATEGIES)
      : baseConfig.enabledStrategies,
    guardrails: {
      ...baseConfig.guardrails,
      minRr: patch.RH_MIN_RR ?? baseConfig.guardrails.minRr,
      maxContracts: patch.RH_MAX_CONTRACTS ?? baseConfig.guardrails.maxContracts,
      maxTradesPerDay: patch.RH_MAX_TRADES_PER_DAY ?? baseConfig.guardrails.maxTradesPerDay,
      maxDailyLossR: patch.RH_MAX_DAILY_LOSS_R ?? baseConfig.guardrails.maxDailyLossR
    }
  };
}

export async function runAgenticImprovementLoop(args: {
  baseConfig: LabConfig;
  bars: Bar[];
  newsGate: NewsGate;
}): Promise<{
  baseline: {
    research: WalkforwardResearchResult;
    report: ReturnType<typeof buildAgenticFundReport>;
  };
  tuned: {
    research: WalkforwardResearchResult;
    report: ReturnType<typeof buildAgenticFundReport>;
    config: LabConfig;
  };
  appliedPatch: AppliedPatch;
  reusedBaseline: boolean;
  delta: {
    survivabilityScore: number;
    profitableNow: boolean;
    deployableNow: boolean;
    failedChecksDelta: number;
  };
}> {
  return runAgenticImprovementLoopWithEvaluator({
    baseConfig: args.baseConfig,
    evaluateResearch: (config) => runWalkforwardResearch({
      baseConfig: config,
      bars: args.bars,
      newsGate: args.newsGate
    })
  });
}

export async function runAgenticImprovementLoopWithEvaluator(args: {
  baseConfig: LabConfig;
  evaluateResearch: (config: LabConfig) => Promise<WalkforwardResearchResult>;
}): Promise<{
  baseline: {
    research: WalkforwardResearchResult;
    report: ReturnType<typeof buildAgenticFundReport>;
  };
  tuned: {
    research: WalkforwardResearchResult;
    report: ReturnType<typeof buildAgenticFundReport>;
    config: LabConfig;
  };
  appliedPatch: AppliedPatch;
  reusedBaseline: boolean;
  delta: {
    survivabilityScore: number;
    profitableNow: boolean;
    deployableNow: boolean;
    failedChecksDelta: number;
  };
}> {
  const { baseConfig, evaluateResearch } = args;

  const baselineResearch = await evaluateResearch(baseConfig);
  const baselineReport = buildAgenticFundReport({
    research: baselineResearch,
    config: baseConfig
  });

  const appliedPatch = deriveAppliedPatch({
    baseConfig,
    report: baselineReport
  });
  const tunedConfig = applyPatchToConfig({
    baseConfig,
    patch: appliedPatch
  });
  const reusedBaseline = !hasAppliedPatchChanges(appliedPatch);
  const tunedResearch = reusedBaseline
    ? baselineResearch
    : await evaluateResearch(tunedConfig);
  const tunedReport = reusedBaseline
    ? baselineReport
    : buildAgenticFundReport({
        research: tunedResearch,
        config: tunedConfig
      });

  return {
    baseline: {
      research: baselineResearch,
      report: baselineReport
    },
    tuned: {
      research: tunedResearch,
      report: tunedReport,
      config: tunedConfig
    },
    appliedPatch,
    reusedBaseline,
    delta: {
      survivabilityScore: tunedReport.survivabilityScore - baselineReport.survivabilityScore,
      profitableNow: tunedReport.profitableNow && !baselineReport.profitableNow,
      deployableNow: tunedReport.deployableNow && !baselineReport.deployableNow,
      failedChecksDelta: tunedReport.failedChecks.length - baselineReport.failedChecks.length
    }
  };
}
