import type { Bar, LabConfig } from "../domain.js";
import { buildAgenticFundReport } from "./agenticFund.js";
import type { WalkforwardResearchResult } from "./walkforward.js";
import { runWalkforwardResearch } from "./walkforward.js";
import type { NewsGate } from "../news/base.js";

interface AppliedPatch {
  RH_MIN_RR?: number;
  RH_MAX_CONTRACTS?: number;
  RH_MAX_TRADES_PER_DAY?: number;
  RH_MAX_DAILY_LOSS_R?: number;
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
  delta: {
    survivabilityScore: number;
    profitableNow: boolean;
    deployableNow: boolean;
    failedChecksDelta: number;
  };
}> {
  const { baseConfig, bars, newsGate } = args;

  const baselineResearch = await runWalkforwardResearch({
    baseConfig,
    bars,
    newsGate
  });
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

  const tunedResearch = await runWalkforwardResearch({
    baseConfig: tunedConfig,
    bars,
    newsGate
  });
  const tunedReport = buildAgenticFundReport({
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
    delta: {
      survivabilityScore: tunedReport.survivabilityScore - baselineReport.survivabilityScore,
      profitableNow: tunedReport.profitableNow && !baselineReport.profitableNow,
      deployableNow: tunedReport.deployableNow && !baselineReport.deployableNow,
      failedChecksDelta: tunedReport.failedChecks.length - baselineReport.failedChecks.length
    }
  };
}
