import type { Bar, LabConfig } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { chicagoDateKey } from "../utils/time.js";
import { buildAgenticFundReport } from "./agenticFund.js";
import { runAgenticImprovementLoopWithEvaluator } from "./agenticLoop.js";
import { runWalkforwardResearch, runWalkforwardResearchOnWindows } from "./walkforward.js";

interface RollingWindow {
  startDay: string;
  endDay: string;
  trainDays: string[];
  testDays: string[];
  trainBars: Bar[];
  testBars: Bar[];
}

function buildRollingWindows(args: {
  bars: Bar[];
  windows: number;
  minTrainDays: number;
  testDays: number;
  embargoDays: number;
}): RollingWindow[] {
  const { bars, windows, minTrainDays, testDays, embargoDays } = args;
  const uniqueDays = Array.from(new Set(bars.map((bar) => chicagoDateKey(bar.ts)))).sort();
  if (uniqueDays.length < minTrainDays + testDays + embargoDays) {
    return [];
  }

  const out: RollingWindow[] = [];
  let endIndex = uniqueDays.length;

  while (out.length < windows) {
    const testStart = endIndex - testDays;
    const trainEnd = testStart - embargoDays;
    const trainStart = Math.max(0, trainEnd - minTrainDays);
    if (testStart <= 0 || trainEnd <= trainStart) {
      break;
    }

    const trainSet = new Set(uniqueDays.slice(trainStart, trainEnd));
    const testSet = new Set(uniqueDays.slice(testStart, endIndex));
    const trainBars = bars.filter((bar) => trainSet.has(chicagoDateKey(bar.ts)));
    const testBars = bars.filter((bar) => testSet.has(chicagoDateKey(bar.ts)));
    if (trainBars.length > 0 && testBars.length > 0) {
      out.push({
        startDay: uniqueDays[trainStart],
        endDay: uniqueDays[endIndex - 1],
        trainDays: Array.from(trainSet),
        testDays: Array.from(testSet),
        trainBars,
        testBars
      });
    }

    endIndex = testStart;
    if (endIndex < minTrainDays + testDays) {
      break;
    }
  }

  return out;
}

export async function runRollingOosEvaluation(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
  windows?: number;
  minTrainDays?: number;
  testDays?: number;
  embargoDays?: number;
}): Promise<{
  config: {
    accountPhase: string;
    windows: number;
    minTrainDays: number;
    testDays: number;
    embargoDays: number;
  };
  windows: Array<{
    windowId: number;
    startDay: string;
    endDay: string;
    trainDays: number;
    testDays: number;
    baseline: {
      status: string;
      survivabilityScore: number;
      deployableNow: boolean;
      failedChecks: string[];
      winnerProfileId: string | null;
    };
    tuned: {
      status: string;
      survivabilityScore: number;
      deployableNow: boolean;
      failedChecks: string[];
      winnerProfileId: string | null;
    };
    delta: {
      survivabilityScore: number;
      failedChecksDelta: number;
      deployableDelta: boolean;
    };
    appliedPatch: {
      RH_MIN_RR?: number;
      RH_MAX_CONTRACTS?: number;
      RH_MAX_TRADES_PER_DAY?: number;
      RH_MAX_DAILY_LOSS_R?: number;
    };
  }>;
  aggregate: {
    windowsEvaluated: number;
    baselineMeanSurvivability: number;
    tunedMeanSurvivability: number;
    meanDeltaSurvivability: number;
    baselineDeployableWindows: number;
    tunedDeployableWindows: number;
  };
}> {
  const windows = buildRollingWindows({
    bars: args.bars,
    windows: args.windows ?? 4,
    minTrainDays: args.minTrainDays ?? 20,
    testDays: args.testDays ?? 5,
    embargoDays: args.embargoDays ?? 1
  });

  const results: Array<{
    windowId: number;
    startDay: string;
    endDay: string;
    trainDays: number;
    testDays: number;
    baseline: {
      status: string;
      survivabilityScore: number;
      deployableNow: boolean;
      failedChecks: string[];
      winnerProfileId: string | null;
    };
    tuned: {
      status: string;
      survivabilityScore: number;
      deployableNow: boolean;
      failedChecks: string[];
      winnerProfileId: string | null;
    };
    delta: {
      survivabilityScore: number;
      failedChecksDelta: number;
      deployableDelta: boolean;
    };
    appliedPatch: {
      RH_MIN_RR?: number;
      RH_MAX_CONTRACTS?: number;
      RH_MAX_TRADES_PER_DAY?: number;
      RH_MAX_DAILY_LOSS_R?: number;
    };
  }> = [];

  for (let index = 0; index < windows.length; index += 1) {
    const window = windows[index];
    const loop = await runAgenticImprovementLoopWithEvaluator({
      baseConfig: args.baseConfig,
      evaluateResearch: (config) => runWalkforwardResearch({
        baseConfig: config,
        bars: window.trainBars,
        newsGate: args.newsGate
      })
    });
    const baselineResearch = await runWalkforwardResearchOnWindows({
      baseConfig: args.baseConfig,
      windows: [{
        train: window.trainBars,
        test: window.testBars
      }],
      newsGate: args.newsGate
    });
    const tunedResearch = loop.reusedBaseline
      ? baselineResearch
      : await runWalkforwardResearchOnWindows({
          baseConfig: loop.tuned.config,
          windows: [{
            train: window.trainBars,
            test: window.testBars
          }],
          newsGate: args.newsGate
        });

    const baselineReport = buildAgenticFundReport({
      research: baselineResearch,
      config: args.baseConfig
    });
    const tunedReport = buildAgenticFundReport({
      research: tunedResearch,
      config: loop.tuned.config
    });

    results.push({
      windowId: index + 1,
      startDay: window.startDay,
      endDay: window.endDay,
      trainDays: window.trainDays.length,
      testDays: window.testDays.length,
      baseline: {
        status: baselineReport.status,
        survivabilityScore: baselineReport.survivabilityScore,
        deployableNow: baselineReport.deployableNow,
        failedChecks: baselineReport.failedChecks,
        winnerProfileId: baselineReport.winnerProfileId
      },
      tuned: {
        status: tunedReport.status,
        survivabilityScore: tunedReport.survivabilityScore,
        deployableNow: tunedReport.deployableNow,
        failedChecks: tunedReport.failedChecks,
        winnerProfileId: tunedReport.winnerProfileId
      },
      delta: {
        survivabilityScore: tunedReport.survivabilityScore - baselineReport.survivabilityScore,
        failedChecksDelta: tunedReport.failedChecks.length - baselineReport.failedChecks.length,
        deployableDelta: tunedReport.deployableNow && !baselineReport.deployableNow
      },
      appliedPatch: loop.appliedPatch
    });
  }

  const baselineMean = results.length > 0
    ? results.reduce((sum, item) => sum + item.baseline.survivabilityScore, 0) / results.length
    : 0;
  const tunedMean = results.length > 0
    ? results.reduce((sum, item) => sum + item.tuned.survivabilityScore, 0) / results.length
    : 0;

  return {
    config: {
      accountPhase: args.baseConfig.accountPhase,
      windows: args.windows ?? 4,
      minTrainDays: args.minTrainDays ?? 20,
      testDays: args.testDays ?? 5,
      embargoDays: args.embargoDays ?? 1
    },
    windows: results,
    aggregate: {
      windowsEvaluated: results.length,
      baselineMeanSurvivability: Number(baselineMean.toFixed(2)),
      tunedMeanSurvivability: Number(tunedMean.toFixed(2)),
      meanDeltaSurvivability: Number((tunedMean - baselineMean).toFixed(2)),
      baselineDeployableWindows: results.filter((item) => item.baseline.deployableNow).length,
      tunedDeployableWindows: results.filter((item) => item.tuned.deployableNow).length
    }
  };
}
