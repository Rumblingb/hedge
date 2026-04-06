import type { Bar, LabConfig } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { buildAgenticFundReport } from "./agenticFund.js";
import { runAgenticImprovementLoop } from "./agenticLoop.js";
import { runWalkforwardResearch } from "./walkforward.js";

function buildLiveStressConfig(baseConfig: LabConfig): LabConfig {
  const latencyMultiplier = 1 + Math.min(1.5, (baseConfig.executionEnv.latencyMs + baseConfig.executionEnv.latencyJitterMs) / 250);
  const tickSlippagePenalty = Math.max(0, baseConfig.executionEnv.slippageTicksPerSide * 0.006);

  return {
    ...baseConfig,
    executionCosts: {
      ...baseConfig.executionCosts,
      slippageRPerSidePerContract: baseConfig.executionCosts.slippageRPerSidePerContract + tickSlippagePenalty,
      stressMultiplier: Number((baseConfig.executionCosts.stressMultiplier * latencyMultiplier).toFixed(4)),
      stressBufferRPerTrade: Number((baseConfig.executionCosts.stressBufferRPerTrade + baseConfig.executionEnv.dataQualityPenaltyR).toFixed(4))
    }
  };
}

export async function runLiveDeploymentReadiness(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
  iterations?: number;
}): Promise<{
  baseline: ReturnType<typeof buildAgenticFundReport>;
  stressedBaseline: ReturnType<typeof buildAgenticFundReport>;
  final: {
    config: LabConfig;
    report: ReturnType<typeof buildAgenticFundReport>;
  };
  iterations: Array<{
    iteration: number;
    survivabilityScore: number;
    deployableNow: boolean;
    failedChecks: string[];
    appliedPatch: {
      RH_MIN_RR?: number;
      RH_MAX_CONTRACTS?: number;
      RH_MAX_TRADES_PER_DAY?: number;
      RH_MAX_DAILY_LOSS_R?: number;
    };
  }>;
  delta: {
    baselineToLiveSurvivability: number;
    stressedToFinalSurvivability: number;
    deployableRecovered: boolean;
  };
}> {
  const iterations = Math.max(1, args.iterations ?? 3);

  const baselineResearch = await runWalkforwardResearch({
    baseConfig: args.baseConfig,
    bars: args.bars,
    newsGate: args.newsGate
  });
  const baselineReport = buildAgenticFundReport({
    research: baselineResearch,
    config: args.baseConfig
  });

  let workingConfig = buildLiveStressConfig(args.baseConfig);
  const stressedResearch = await runWalkforwardResearch({
    baseConfig: workingConfig,
    bars: args.bars,
    newsGate: args.newsGate
  });
  const stressedBaseline = buildAgenticFundReport({
    research: stressedResearch,
    config: workingConfig
  });

  const iterationReports: Array<{
    iteration: number;
    survivabilityScore: number;
    deployableNow: boolean;
    failedChecks: string[];
    appliedPatch: {
      RH_MIN_RR?: number;
      RH_MAX_CONTRACTS?: number;
      RH_MAX_TRADES_PER_DAY?: number;
      RH_MAX_DAILY_LOSS_R?: number;
    };
  }> = [];

  for (let index = 0; index < iterations; index += 1) {
    const loop = await runAgenticImprovementLoop({
      baseConfig: workingConfig,
      bars: args.bars,
      newsGate: args.newsGate
    });

    workingConfig = loop.tuned.config;
    const report = buildAgenticFundReport({
      research: loop.tuned.research,
      config: workingConfig
    });
    iterationReports.push({
      iteration: index + 1,
      survivabilityScore: report.survivabilityScore,
      deployableNow: report.deployableNow,
      failedChecks: report.failedChecks,
      appliedPatch: loop.appliedPatch
    });

    if (report.deployableNow) {
      break;
    }
  }

  const finalResearch = await runWalkforwardResearch({
    baseConfig: workingConfig,
    bars: args.bars,
    newsGate: args.newsGate
  });
  const finalReport = buildAgenticFundReport({
    research: finalResearch,
    config: workingConfig
  });

  return {
    baseline: baselineReport,
    stressedBaseline,
    final: {
      config: workingConfig,
      report: finalReport
    },
    iterations: iterationReports,
    delta: {
      baselineToLiveSurvivability: Number((stressedBaseline.survivabilityScore - baselineReport.survivabilityScore).toFixed(2)),
      stressedToFinalSurvivability: Number((finalReport.survivabilityScore - stressedBaseline.survivabilityScore).toFixed(2)),
      deployableRecovered: finalReport.deployableNow && !stressedBaseline.deployableNow
    }
  };
}
