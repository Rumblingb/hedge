import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { getConfig } from "../config.js";
import { loadBarsFromCsv } from "../data/csv.js";
import { SUPPORTED_STRATEGY_IDS, type LabConfig, type SupportedStrategyId } from "../domain.js";
import { loadRedFolderEvents } from "../news/redFolder.js";
import { MockNewsGate, SAMPLE_HEADLINES } from "../news/mockNewsGate.js";
import { readLatestForkSynthesis, type ForkSynthesisReport } from "../research/forkSynthesis.js";
import { buildNoEdgeLedger, loadLatestNoEdgeLedger, mergeNoEdgeLedgers, noEdgeLedgerLatestPath, writeNoEdgeLedger } from "../research/noEdgeLedger.js";
import { loadLatestPositioningContext, positioningContextLatestPath, type PositioningContextArtifact } from "../research/positioning.js";
import { RESEARCH_PROFILES, type ResearchProfile } from "../research/profiles.js";
import { loadLatestResearchStrategyFeed } from "../research/strategyFeed.js";
import { loadTraderIntuition, type TraderIntuition } from "../research/traderIntuition.js";
import { buildStrategyCatalog } from "../strategies/wctcEnsemble.js";
import { buildAgenticFundReport } from "./agenticFund.js";
import { evaluateResearchPromotion } from "./promotionGate.js";
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
  quantCoverage: {
    profilesEvaluated: number;
    profileSelection: {
      mode: "all" | "ids" | "limit";
      requestedIds: string[];
      selectedIds: string[];
      unknownIds: string[];
      availableProfiles: number;
    };
    supportedStrategies: SupportedStrategyId[];
    testedStrategies: SupportedStrategyId[];
    missingStrategies: SupportedStrategyId[];
    inSampleBars: number;
    oosBars: number;
    minBars: number;
    sampleSizeOk: boolean;
  };
  researchContext: {
    researchFeedStrategyCount: number;
    forkSynthesis: {
      present: boolean;
      adoptedPatterns: string[];
      strategyDirectives: Array<{
        strategyId: SupportedStrategyId;
        sourceForks: string[];
        directive: string;
      }>;
      blockers: string[];
      path: string;
    };
    redFolderEvents: number;
    redFolderPath: string;
    redFolderWarnings: string[];
    positioning: {
      present: boolean;
      path: string;
      cotSymbols: number;
      gammaReports: number;
      gammaErrors: number;
      notes: string[];
    };
    traderIntuition: TraderIntuition;
    noEdgeLedger: {
      present: boolean;
      path: string;
      noEdgeProfiles: number;
      blockedProfiles: number;
      needsMoreDataProfiles: number;
      promotableProfiles: number;
      blockedStrategies: SupportedStrategyId[];
      learningSummary: string[];
    };
  };
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
    noEdgeLedgerPath: string;
  };
}

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

function createNewsGate(config: LabConfig, redFolderEvents: Awaited<ReturnType<typeof loadRedFolderEvents>>): MockNewsGate {
  return new MockNewsGate({
    headlines: unique([...SAMPLE_HEADLINES, ...redFolderEvents.events]),
    blackoutMinutesBefore: config.guardrails.newsBlackoutMinutesBefore,
    blackoutMinutesAfter: config.guardrails.newsBlackoutMinutesAfter
  });
}

function parsePositiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseCsvList(value: string | undefined): string[] {
  return unique((value ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean));
}

function selectResearchProfiles(env: NodeJS.ProcessEnv): {
  profiles: ResearchProfile[];
  mode: "all" | "ids" | "limit";
  requestedIds: string[];
  selectedIds: string[];
  unknownIds: string[];
  availableProfiles: number;
} {
  const allProfiles = RESEARCH_PROFILES;
  const requestedIds = parseCsvList(env.BILL_STRATEGY_FACTORY_PROFILE_IDS);
  if (requestedIds.length > 0) {
    const profileById = new Map(allProfiles.map((profile) => [profile.id, profile]));
    const selected = requestedIds
      .map((id) => profileById.get(id))
      .filter((profile): profile is ResearchProfile => Boolean(profile));
    const profiles = selected.length > 0 ? selected : allProfiles;
    return {
      profiles,
      mode: "ids",
      requestedIds,
      selectedIds: profiles.map((profile) => profile.id),
      unknownIds: requestedIds.filter((id) => !profileById.has(id)),
      availableProfiles: allProfiles.length
    };
  }

  const limit = Number.parseInt(env.BILL_STRATEGY_FACTORY_PROFILE_LIMIT ?? "", 10);
  if (Number.isFinite(limit) && limit > 0 && limit < allProfiles.length) {
    const offset = Math.max(0, Number.parseInt(env.BILL_STRATEGY_FACTORY_PROFILE_OFFSET ?? "0", 10) || 0);
    const rotated = [...allProfiles.slice(offset), ...allProfiles.slice(0, offset)];
    const profiles = rotated.slice(0, limit);
    return {
      profiles,
      mode: "limit",
      requestedIds: [],
      selectedIds: profiles.map((profile) => profile.id),
      unknownIds: [],
      availableProfiles: allProfiles.length
    };
  }

  return {
    profiles: allProfiles,
    mode: "all",
    requestedIds: [],
    selectedIds: allProfiles.map((profile) => profile.id),
    unknownIds: [],
    availableProfiles: allProfiles.length
  };
}

function implementedStrategies(): SupportedStrategyId[] {
  const supported = new Set<string>(SUPPORTED_STRATEGY_IDS);
  return Object.keys(buildStrategyCatalog())
    .filter((strategyId) => supported.has(strategyId)) as SupportedStrategyId[];
}

function strategiesByResearchProfile(): Map<string, SupportedStrategyId[]> {
  const implemented = new Set(implementedStrategies());
  return new Map(
    RESEARCH_PROFILES.map((profile) => [
      profile.id,
      (profile.overrides.enabledStrategies ?? [])
        .filter((strategyId): strategyId is SupportedStrategyId => implemented.has(strategyId as SupportedStrategyId))
    ])
  );
}

function testedStrategiesFromProfiles(profiles: Array<{ profileId: string; description: string }>): SupportedStrategyId[] {
  const byProfile = strategiesByResearchProfile();
  return unique(profiles.flatMap((profile) => byProfile.get(profile.profileId) ?? []));
}

function summarizeForkSynthesis(report: ForkSynthesisReport | null, path: string): StrategyFactoryReport["researchContext"]["forkSynthesis"] {
  if (!report) {
    return {
      present: false,
      adoptedPatterns: [],
      strategyDirectives: [],
      blockers: ["Fork synthesis is missing. Run npm run bill:fork-synthesis after fork-intake."],
      path
    };
  }
  return {
    present: true,
    adoptedPatterns: report.adoptedPatterns.map((pattern) => pattern.label).slice(0, 8),
    strategyDirectives: report.strategyLabDirectives.slice(0, 8),
    blockers: report.blockers,
    path: report.outputPath
  };
}

function summarizePositioning(report: PositioningContextArtifact | null, path: string): StrategyFactoryReport["researchContext"]["positioning"] {
  if (!report) {
    return {
      present: false,
      path,
      cotSymbols: 0,
      gammaReports: 0,
      gammaErrors: 0,
      notes: ["Positioning context is missing. Run npm run bill:positioning-status."]
    };
  }
  return {
    present: true,
    path,
    cotSymbols: report.cot.symbols.length,
    gammaReports: report.dealerGamma.reports.length,
    gammaErrors: report.dealerGamma.errors.length,
    notes: report.strategyNotes.slice(0, 8)
  };
}

export async function runStrategyFactory(options: StrategyFactoryOptions = {}): Promise<StrategyFactoryReport> {
  const env = options.env ?? process.env;
  const generatedAt = options.now?.() ?? new Date().toISOString();
  const csvPath = resolve(options.csvPath ?? env.BILL_STRATEGY_LAB_CSV_PATH ?? "data/free/ALL-6MARKETS-1m-30d-normalized.csv");
  const oosCsvPath = resolve(options.oosCsvPath ?? env.BILL_STRATEGY_LAB_OOS_CSV_PATH ?? "data/free/ALL-6MARKETS-1m-90d-normalized.csv");
  const outputPath = resolve(options.outputPath ?? env.BILL_STRATEGY_FACTORY_OUTPUT_PATH ?? ".rumbling-hedge/state/strategy-factory.latest.json");
  const forkSynthesisPath = resolve(env.BILL_FORK_SYNTHESIS_PATH ?? ".rumbling-hedge/research/forks/_synthesis.latest.json");
  const positioningPath = positioningContextLatestPath(env);
  const config = getConfig();
  const noEdgePath = noEdgeLedgerLatestPath(env);
  const profileSelection = selectResearchProfiles(env);
  const [bars, oosBars, researchFeed, forkSynthesis, positioning, redFolderEvents, traderIntuition] = await Promise.all([
    loadBarsFromCsv(csvPath),
    loadBarsFromCsv(oosCsvPath),
    loadLatestResearchStrategyFeed(undefined, {
      maxAgeMs: parsePositiveInt(env.BILL_RESEARCH_STRATEGY_FEED_MAX_AGE_HOURS, 72) * 60 * 60 * 1000
    }),
    readLatestForkSynthesis(forkSynthesisPath),
    loadLatestPositioningContext(positioningPath),
    loadRedFolderEvents(env.BILL_RED_FOLDER_EVENTS_PATH),
    loadTraderIntuition({ env })
  ]);
  const newsGate = createNewsGate(config, redFolderEvents);

  const walkforward = await runWalkforwardResearch({
    baseConfig: config,
    bars,
    newsGate,
    profiles: profileSelection.profiles
  });
  const walkforwardReport = buildAgenticFundReport({
    research: walkforward,
    config
  });
  const rollingOos = await runRollingOosEvaluation({
    bars: oosBars,
    baseConfig: config,
    newsGate,
    profiles: profileSelection.profiles,
    tune: true, // Enable per-window tuning so tuned stats differ from baseline (was dead code)
    windows: parsePositiveInt(env.BILL_STRATEGY_FACTORY_OOS_WINDOWS, 4),
    minTrainDays: parsePositiveInt(env.BILL_STRATEGY_FACTORY_OOS_MIN_TRAIN_DAYS, 20),
    testDays: parsePositiveInt(env.BILL_STRATEGY_FACTORY_OOS_TEST_DAYS, 5),
    embargoDays: parsePositiveInt(env.BILL_STRATEGY_FACTORY_OOS_EMBARGO_DAYS, 1)
  });
  const liveReadiness = await runLiveDeploymentReadiness({
    bars,
    baseConfig: config,
    newsGate,
    profiles: profileSelection.profiles,
    iterations: parsePositiveInt(env.BILL_STRATEGY_FACTORY_LIVE_ITERATIONS, 1)
  });

  // Demo mode defaults to 2 OOS windows; env can still tighten/loosen bounded research slices.
  const demoMode = env.BILL_FUTURES_DEMO_EXPLORATION_ENABLED === "true";
  const minRollingOosWindows = parsePositiveInt(env.BILL_STRATEGY_FACTORY_MIN_OOS_WINDOWS, demoMode ? 2 : 4);
  const minBars = parsePositiveInt(env.BILL_STRATEGY_FACTORY_MIN_BARS, 1000);
  const profileStrategies = strategiesByResearchProfile();
  const implemented = implementedStrategies();
  const testedStrategies = testedStrategiesFromProfiles(walkforward.profiles);
  const missingStrategies = profileSelection.mode === "all"
    ? implemented.filter((strategyId) => !testedStrategies.includes(strategyId))
    : [];
  const sampleSizeOk = bars.length >= minBars && oosBars.length >= minBars;
  const gatesByProfileId = new Map(walkforward.profiles.map((profile) => [
    profile.profileId,
    evaluateResearchPromotion({
      winner: profile,
      recommendedFamilyBudget: profile.familyBudget,
      phase: config.accountPhase,
      profilesTested: walkforward.profiles.length
    })
  ]));
  const currentNoEdgeLedger = buildNoEdgeLedger({
    generatedAt,
    runId: `strategy-factory-${generatedAt.replace(/[:.]/g, "-")}`,
    profiles: walkforward.profiles,
    gatesByProfileId,
    strategiesByProfileId: profileStrategies
  });
  const noEdgeLedger = mergeNoEdgeLedgers({
    previous: await loadLatestNoEdgeLedger(noEdgePath),
    current: currentNoEdgeLedger
  });
  const noEdgeLedgerPaths = await writeNoEdgeLedger(noEdgeLedger, { latestPath: noEdgePath });
  const noEdgeBlockedStrategySet = new Set(noEdgeLedger.blockedStrategies);
  const preferredStrategies = unique([...(researchFeed?.preferredStrategies ?? []), ...traderIntuition.preferredStrategies])
    .filter((strategyId) => !noEdgeBlockedStrategySet.has(strategyId));
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
    ...(missingStrategies.length > 0 ? [`strategy coverage is incomplete: missing ${missingStrategies.join(", ")}`] : []),
    ...(!sampleSizeOk ? [`sample size is too small for quant promotion (${bars.length}/${oosBars.length} bars, min ${minBars})`] : []),
    ...(!gates.liveReadinessDeployable ? ["stressed live-readiness pass is not deployable"] : []),
    ...(!gates.researchFeedFresh ? ["no fresh research strategy feed supports candidates"] : []),
    ...(!gates.liveDisabled ? ["live prediction execution must remain disabled for v1"] : []),
    ...(!gates.futuresDemoDisabled ? ["futures demo execution is enabled; keep strategy-factory promotion paper-only unless demo routing is explicitly being tested"] : [])
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
    preferredStrategies,
    preferredSymbols: unique([...(researchFeed?.preferredSymbols ?? []), ...traderIntuition.preferredSymbols]),
    quantCoverage: {
      profilesEvaluated: walkforward.profiles.length,
      profileSelection: {
        mode: profileSelection.mode,
        requestedIds: profileSelection.requestedIds,
        selectedIds: profileSelection.selectedIds,
        unknownIds: profileSelection.unknownIds,
        availableProfiles: profileSelection.availableProfiles
      },
      supportedStrategies: implemented,
      testedStrategies,
      missingStrategies,
      inSampleBars: bars.length,
      oosBars: oosBars.length,
      minBars,
      sampleSizeOk
    },
    researchContext: {
      researchFeedStrategyCount: researchFeed?.strategyCount ?? 0,
      forkSynthesis: summarizeForkSynthesis(forkSynthesis, forkSynthesisPath),
      redFolderEvents: redFolderEvents.events.length,
      redFolderPath: redFolderEvents.path,
      redFolderWarnings: redFolderEvents.warnings,
      positioning: summarizePositioning(positioning, positioningPath),
      traderIntuition,
      noEdgeLedger: {
        present: true,
        path: noEdgeLedgerPaths.latestPath,
        noEdgeProfiles: noEdgeLedger.noEdgeCount,
        blockedProfiles: noEdgeLedger.blockedCount,
        needsMoreDataProfiles: noEdgeLedger.needsMoreDataCount,
        promotableProfiles: noEdgeLedger.promotableCount,
        blockedStrategies: noEdgeLedger.blockedStrategies,
        learningSummary: noEdgeLedger.learningSummary
      }
    },
    blockers,
    evidence: {
      walkforwardStatus: walkforwardReport.status,
      survivabilityScore: walkforwardReport.survivabilityScore,
      liveReadinessFinalScore: liveReadiness.final.report.survivabilityScore,
      rollingOosMeanSurvivability: rollingOos.aggregate.tunedMeanSurvivability
    },
    artifacts: {
      outputPath,
      researchFeedPath: researchFeed?.artifactPath ?? ".rumbling-hedge/research/researcher/strategy-hypotheses.latest.json",
      noEdgeLedgerPath: noEdgeLedgerPaths.latestPath
    }
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
