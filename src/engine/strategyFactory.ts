import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { getConfig } from "../config.js";
import { loadBarsFromCsv } from "../data/csv.js";
import type { LabConfig } from "../domain.js";
import { MockNewsGate } from "../news/mockNewsGate.js";
import { loadLatestResearchStrategyFeed } from "../research/strategyFeed.js";
import { buildAgenticFundReport } from "./agenticFund.js";
import { runLiveDeploymentReadiness } from "./liveReadiness.js";
import { runRollingOosEvaluation } from "./rollingOos.js";
import { runWalkforwardResearch } from "./walkforward.js";

export interface StrategyFactoryOptions {
  csvPath?: string;
  oosCsvPath?: string;
  outputPath?: string;
  now?: () => string;
  env?: NodeJS.ProcessEnv;
}

export interface StrategyFactoryReport {
  command: "strategy-factory";
  generatedAt: string;
  mode: "paper-only";
  csvPath: string;
  oosCsvPath: string;
  status: "promotable-to-paper" | "blocked";
  gates: {
    walkforwardDeployable: boolean;
    rollingOosWindows: number;
    minRollingOosWindows: number;
    rollingOosDeployableWindows: number;
    liveReadinessDeployable: boolean;
    researchFeedFresh: boolean;
    liveDisabled: boolean;
    futuresDemoDisabled: boolean;
  };
  selectedProfileId: string | null;
  preferredStrategies: string[];
  preferredSymbols: string[];
  blockers: string[];
  evidence: {
    walkforwardStatus: string;
    survivabilityScore: number;
    liveReadinessFinalScore: number;
    rollingOosMeanSurvivability: number;
  };
  artifacts: {
    outputPath: string;
    researchFeedPath: string;
  };
}

function createNewsGate(config: LabConfig): MockNewsGate {
  return new MockNewsGate({
    blackoutMinutesBefore: config.guardrails.newsBlackoutMinutesBefore,
    blackoutMinutesAfter: config.guardrails.newsBlackoutMinutesAfter
  });
}

function parsePositiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export async function runStrategyFactory(options: StrategyFactoryOptions = {}): Promise<StrategyFactoryReport> {
  const env = options.env ?? process.env;
  const generatedAt = options.now?.() ?? new Date().toISOString();
  const csvPath = resolve(options.csvPath ?? env.BILL_STRATEGY_LAB_CSV_PATH ?? "data/free/ALL-6MARKETS-1m-10d-normalized.csv");
  const oosCsvPath = resolve(options.oosCsvPath ?? env.BILL_STRATEGY_LAB_OOS_CSV_PATH ?? "data/free/ALL-6MARKETS-1m-30d-normalized.csv");
  const outputPath = resolve(options.outputPath ?? env.BILL_STRATEGY_FACTORY_OUTPUT_PATH ?? ".rumbling-hedge/state/strategy-factory.latest.json");
  const config = getConfig();
  const newsGate = createNewsGate(config);
  const [bars, oosBars, researchFeed] = await Promise.all([
    loadBarsFromCsv(csvPath),
    loadBarsFromCsv(oosCsvPath),
    loadLatestResearchStrategyFeed(undefined, {
      maxAgeMs: parsePositiveInt(env.BILL_RESEARCH_STRATEGY_FEED_MAX_AGE_HOURS, 72) * 60 * 60 * 1000
    })
  ]);

  const walkforward = await runWalkforwardResearch({
    baseConfig: config,
    bars,
    newsGate
  });
  const walkforwardReport = buildAgenticFundReport({
    research: walkforward,
    config
  });
  const rollingOos = await runRollingOosEvaluation({
    bars: oosBars,
    baseConfig: config,
    newsGate,
    windows: parsePositiveInt(env.BILL_STRATEGY_FACTORY_OOS_WINDOWS, 4),
    minTrainDays: parsePositiveInt(env.BILL_STRATEGY_FACTORY_OOS_MIN_TRAIN_DAYS, 20),
    testDays: parsePositiveInt(env.BILL_STRATEGY_FACTORY_OOS_TEST_DAYS, 5),
    embargoDays: parsePositiveInt(env.BILL_STRATEGY_FACTORY_OOS_EMBARGO_DAYS, 1)
  });
  const liveReadiness = await runLiveDeploymentReadiness({
    bars,
    baseConfig: config,
    newsGate,
    iterations: parsePositiveInt(env.BILL_STRATEGY_FACTORY_LIVE_ITERATIONS, 1)
  });

  const minRollingOosWindows = parsePositiveInt(env.BILL_STRATEGY_FACTORY_MIN_OOS_WINDOWS, 4);
  const gates = {
    walkforwardDeployable: walkforwardReport.deployableNow,
    rollingOosWindows: rollingOos.aggregate.windowsEvaluated,
    minRollingOosWindows,
    rollingOosDeployableWindows: rollingOos.aggregate.tunedDeployableWindows,
    liveReadinessDeployable: liveReadiness.final.report.deployableNow,
    researchFeedFresh: Boolean(researchFeed && researchFeed.strategyCount > 0),
    liveDisabled: env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED !== "true",
    futuresDemoDisabled: env.BILL_ENABLE_FUTURES_DEMO_EXECUTION !== "true"
  };

  const blockers = [
    ...(!gates.walkforwardDeployable ? ["walkforward report is not deployable"] : []),
    ...(gates.rollingOosWindows < gates.minRollingOosWindows ? [`rolling OOS evidence is thin (${gates.rollingOosWindows}/${gates.minRollingOosWindows} windows)`] : []),
    ...(gates.rollingOosDeployableWindows < gates.minRollingOosWindows ? ["not all rolling OOS windows are deployable"] : []),
    ...(!gates.liveReadinessDeployable ? ["stressed live-readiness pass is not deployable"] : []),
    ...(!gates.researchFeedFresh ? ["no fresh research strategy feed supports candidates"] : []),
    ...(!gates.liveDisabled ? ["live prediction execution must remain disabled for v1"] : []),
    ...(!gates.futuresDemoDisabled ? ["futures demo execution must remain disabled for v1 paper-only autonomy"] : [])
  ];

  const report: StrategyFactoryReport = {
    command: "strategy-factory",
    generatedAt,
    mode: "paper-only",
    csvPath,
    oosCsvPath,
    status: blockers.length === 0 ? "promotable-to-paper" : "blocked",
    gates,
    selectedProfileId: walkforwardReport.winnerProfileId,
    preferredStrategies: researchFeed?.preferredStrategies ?? [],
    preferredSymbols: researchFeed?.preferredSymbols ?? [],
    blockers,
    evidence: {
      walkforwardStatus: walkforwardReport.status,
      survivabilityScore: walkforwardReport.survivabilityScore,
      liveReadinessFinalScore: liveReadiness.final.report.survivabilityScore,
      rollingOosMeanSurvivability: rollingOos.aggregate.tunedMeanSurvivability
    },
    artifacts: {
      outputPath,
      researchFeedPath: researchFeed?.artifactPath ?? ".rumbling-hedge/research/researcher/strategy-hypotheses.latest.json"
    }
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}

