import { parse as parseDotenv } from "dotenv";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { readdir } from "node:fs/promises";
import os from "node:os";
import { dirname, extname, join, resolve } from "node:path";
import { getConfig, redactConfigForDiagnostics } from "./config.js";
import { inspectBarsFromCsv, loadBarsFromCsv } from "./data/csv.js";
import { fetchFreeBars, type FreeDataProvider, type FreeInterval, writeBarsCsv } from "./data/freeSources.js";
import { normalizeUniverseByInnerTimestamp } from "./data/normalize.js";
import { assertBarsResearchReady, assessBarsForResearch } from "./data/quality.js";
import { generateSyntheticBars } from "./data/synthetic.js";
import { runBacktest } from "./engine/backtest.js";
import { buildDashboardSnapshot } from "./engine/dashboardSnapshot.js";
import { buildDailyStrategyPlan } from "./engine/dailyPlan.js";
import { buildAgenticFundReport } from "./engine/agenticFund.js";
import { runAgenticImprovementLoop } from "./engine/agenticLoop.js";
import { readKillSwitch, writeKillSwitch } from "./engine/killSwitch.js";
import { runLiveDeploymentReadiness } from "./engine/liveReadiness.js";
import { buildJarvisBrief } from "./engine/jarvisBrief.js";
import { buildOpenJarvisStatus } from "./engine/openJarvis.js";
import { writeOpenJarvisBoardArtifacts } from "./engine/openJarvisBoard.js";
import { writeAutonomyStatus } from "./engine/autonomyStatus.js";
import { runStrategyFactory } from "./engine/strategyFactory.js";
import { applyHermesSupervisorDecision, findHermesSupervisorTask, readHermesSupervisorArtifact, type HermesSupervisorDecisionAction } from "./engine/hermesSupervisor.js";
import { runRiskTradeModel } from "./engine/riskModel.js";
import { readJournal, writeJournal } from "./engine/journal.js";
import { summarizeTrades } from "./engine/report.js";
import { runWalkforwardResearch } from "./engine/walkforward.js";
import { runRollingOosEvaluation } from "./engine/rollingOos.js";
import { proposeEvolution } from "./evolution/proposals.js";
import { MockNewsGate } from "./news/mockNewsGate.js";
import { collectResearchUniverse } from "./research/profiles.js";
import { buildDefaultEnsemble } from "./strategies/wctcEnsemble.js";
import { diagnosePredictionScan, scanPredictionCandidates } from "./prediction/matcher.js";
import { readPredictionJournal, writePredictionJournal } from "./prediction/journal.js";
import { buildPredictionReport } from "./prediction/report.js";
import { DEFAULT_PREDICTION_FEES } from "./prediction/fees.js";
import type { BillPromotionState, PredictionCycleReview, PredictionMarketSnapshot } from "./prediction/types.js";
import { collectPredictionSnapshots } from "./prediction/collector.js";
import { buildPredictionSourcePolicyFromEnv } from "./prediction/policy.js";
import { resolvePredictionScanPolicy } from "./prediction/scanPolicy.js";
import { buildPredictionSizingConfigFromEnv } from "./prediction/sizing.js";
import { runPredictionTraining } from "./prediction/training.js";
import { buildPredictionCycleReview } from "./prediction/review.js";
import { buildPredictionCopyDemoReport } from "./prediction/copyTrading.js";
import { buildBtcFiveMinuteEdgeReport } from "./prediction/btcFiveMinuteEdge.js";
import { resolvePredictionJournal, buildCalibrationReportFromJsonl } from "./prediction/resolver.js";
import { buildCounterfactualReport, summarizeCounterfactual } from "./prediction/counterfactual.js";
import { collectFlowSnapshots, appendFlowSnapshots, scanFlowAcceleration } from "./prediction/flowSignals.js";
import { inspectPredictionMarketAnalysisDataset, writePredictionMarketAnalysisReadiness } from "./prediction/historicalDataset.js";
import { kronosForecast, kronosHealth } from "./research/kronos.js";
import { authorizePredictionExecution } from "./prediction/execution/authorization.js";
import { appendFills, buildExecutionConfigFromEnv, readFillsJournal, routePredictionCandidates } from "./prediction/execution/router.js";
import { evaluateLiveGate } from "./prediction/execution/liveGate.js";
import { buildResearchCatalogReport, collectResearchCatalog, readResearchCatalog } from "./research/collector.js";
import { runMarkovOosReport, runMarkovReturnBacktest } from "./research/markov.js";
import { inspectTimesFmReadiness, writeTimesFmReadiness } from "./research/timesfm.js";
import { buildPromotionStateFromPredictionReview, readPromotionState, writePromotionState } from "./promotion/state.js";
import { buildBillSourceCatalog } from "./research/sources.js";
import { loadLatestResearchStrategyFeed } from "./research/strategyFeed.js";
import { buildTrackPolicyFromEnv } from "./research/tracks.js";
import { buildBillToolRegistry } from "./research/tools.js";
import { readLatestResearcherRunReport, runResearcherPipeline, type ResearcherRunReport } from "./research/pipeline.js";
import { runForkIntake } from "./research/forkIntake.js";
import {
  buildOneDayToExpiryOptionReport,
  fetchAlpacaOptionSnapshots,
  fetchAlpacaUnderlyingPrice,
  fetchPolygonOptionSnapshots,
  fetchYahooOptionSnapshots
} from "./research/options.js";
import { SUPPORTED_STRATEGY_IDS } from "./domain.js";
import { buildDemoAccountStrategyLanes, isDemoAccountLockSatisfied, listAllowedDemoAccounts } from "./live/demoAccounts.js";
import { buildDemoStrategySampleSnapshot } from "./live/demoSampling.js";
import { executeFuturesDemoLanes } from "./live/demoExecution.js";
import { prepareFuturesLoopDataset } from "./live/futuresPreflight.js";
import { buildOpportunitySnapshot } from "./opportunity/orchestrator.js";
import { resolveProjectXApiBaseUrl } from "./adapters/projectx/baseUrl.js";

function findBillEnvCandidates(): string[] {
  const seen = new Set<string>();
  const userScopedSystemAccess = (() => {
    try {
      return readdirSync("/Users", { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => resolve("/Users", entry.name, "Public/Drop Box/system-access.env"));
    } catch {
      return [] as string[];
    }
  })();
  const candidates = [
    resolve(process.cwd(), ".env"),
    ...["system-access.env", "Public/Drop Box/system-access.env"].map((relativePath) => resolve(os.homedir(), relativePath)),
    ...userScopedSystemAccess,
    resolve(os.homedir(), "Library/Application Support/AgentPay/bill/bill.env"),
    ...(process.env.BILL_ENV_FILE ? [resolve(process.env.BILL_ENV_FILE)] : [])
  ];

  return candidates.filter((candidate) => {
    if (seen.has(candidate)) return false;
    seen.add(candidate);
    return existsSync(candidate);
  });
}

function loadBillDotenvChain(): void {
  const lockedKeys = new Set(
    Object.entries(process.env)
      .filter(([, value]) => value != null && value !== "")
      .map(([key]) => key)
  );
  for (const filePath of findBillEnvCandidates()) {
    let parsed: Record<string, string>;
    try {
      parsed = parseDotenv(readFileSync(filePath, "utf8"));
    } catch {
      continue;
    }
    for (const [key, value] of Object.entries(parsed)) {
      if (value === "") continue;
      if (lockedKeys.has(key)) continue;
      process.env[key] = value;
    }
  }
}

loadBillDotenvChain();

function printUsage(): void {
  console.log("Commands: doctor | sim | backtest [csvPath] | research [csvPath] | day-plan [csvPath] | dashboard [csvPath] | kill-switch [on|off|status] [reason] | inspect-csv <csvPath> | data-quality <csvPath> [minCoveragePct] [maxEndLagMinutes] | normalize-universe <csvPath> [outPath] | oos-rolling <csvPath> [windows] [minTrainDays] [testDays] [embargoDays] | live-readiness <csvPath> [iterations] | demo-tomorrow [csvPath] | demo-overnight [csvPath] | risk-model <csvPath> | markov-return <csvPath> [minTrainingTransitions=60] [signalThreshold=0.001] | markov-oos [csvOrDir=data/research] [trainReturns=20] [testReturns=5] [stepReturns=5] | fetch-free <symbol> [interval] [range] [outPath] [provider] | fetch-free-universe [interval] [range] [outDir] [provider] | btc-5m-edge [csvPath] [liveUpImplied] | options-1dte-report [underlying] | evolve | jarvis [csvPath] | jarvis-loop [csvPath] | jarvis-brief [csvPath] [--note text] | openjarvis-status | openjarvis-board | autonomy-status | fork-intake [manifestPath] [outputDir] | strategy-factory [csvPath] [oosCsvPath] | hermes-supervisor-status | hermes-supervisor-approve <taskId> [note] | hermes-supervisor-pause <taskId> [note] | hermes-supervisor-resume <taskId> [note] | hermes-supervisor-complete <taskId> [note] | hermes-supervisor-why <taskId> | prediction-collect [source] [limit] [outPath] | prediction-scan [inputPath] | prediction-train [journalPath] | prediction-report [journalPath] | prediction-execute [journalPath] | prediction-review [journalPath] [snapshotPath] | prediction-copy-demo | prediction-market-analysis-status [dataRoot] [reportPath] [markdownPath] | timesfm-status [reportPath] [markdownPath] | opportunity-snapshot | promotion-status | promotion-review [journalPath] [snapshotPath] | market-track-status | research-agent-collect | research-agent-report | researcher-run [--target id] [--max-targets n] [--skip-judge] [--skip-embed] | researcher-report [reportPath] | ollama-smoke [prompt] | nim-smoke [prompt]");
}

function createNewsGate(config: ReturnType<typeof getConfig>): MockNewsGate {
  return new MockNewsGate({
    blackoutMinutesBefore: config.guardrails.newsBlackoutMinutesBefore,
    blackoutMinutesAfter: config.guardrails.newsBlackoutMinutesAfter
  });
}

const DEFAULT_UNIVERSE_SYMBOLS = ["NQ", "ES", "CL", "GC", "6E", "ZN"];

function parseInterval(value: string | undefined): FreeInterval {
  const selected = (value ?? "1m") as FreeInterval;
  const allowed: FreeInterval[] = ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1d"];
  if (!allowed.includes(selected)) {
    throw new Error(`Unsupported interval: ${value}.`);
  }
  return selected;
}

function parseProvider(value: string | undefined): FreeDataProvider {
  const selected = (value ?? "auto") as FreeDataProvider;
  const allowed: FreeDataProvider[] = ["auto", "databento", "yahoo", "stooq", "polygon"];
  if (!allowed.includes(selected)) {
    throw new Error(`Unsupported provider: ${value}.`);
  }
  return selected;
}

function maybeEnforceResearchQualityGate(bars: Awaited<ReturnType<typeof loadBarsFromCsv>>): void {
  if (process.env.RH_ALLOW_INCOMPLETE_DATA === "1") {
    return;
  }

  assertBarsResearchReady(bars);
}

function resolvePaperLoopCsvPath(csvPath?: string): string {
  return resolve(
    csvPath
    ?? process.env.BILL_PAPER_LOOP_CSV_PATH
    ?? "data/free/ALL-6MARKETS-1m-10d-normalized.csv"
  );
}

function selectRecentPlanningBars<T extends { ts: string }>(bars: T[]): T[] {
  const recentDays = Number.parseFloat(process.env.BILL_DAILY_PLAN_RECENT_DAYS ?? "5");
  if (!Number.isFinite(recentDays) || recentDays <= 0 || bars.length === 0) {
    return bars;
  }
  let latestMs = Number.NEGATIVE_INFINITY;
  for (const bar of bars) {
    const parsed = Date.parse(bar.ts);
    if (Number.isFinite(parsed) && parsed > latestMs) {
      latestMs = parsed;
    }
  }
  if (!Number.isFinite(latestMs)) {
    return bars;
  }
  const cutoffMs = latestMs - (recentDays * 24 * 60 * 60 * 1000);
  const recent = bars.filter((bar) => {
    const parsed = Date.parse(bar.ts);
    return Number.isFinite(parsed) && parsed >= cutoffMs;
  });
  return recent.length > 0 ? recent : bars;
}

async function appendJsonLine(path: string, value: unknown): Promise<void> {
  const fs = await import("node:fs/promises");
  await fs.mkdir(dirname(path), { recursive: true });
  await fs.appendFile(path, `${JSON.stringify(value)}\n`, "utf8");
}

async function readJsonlRecords(path: string): Promise<Array<Record<string, unknown>>> {
  const fs = await import("node:fs/promises");
  try {
    const raw = await fs.readFile(path, "utf8");
    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
  } catch {
    return [];
  }
}

async function writeJsonFile(path: string, value: unknown): Promise<void> {
  const fs = await import("node:fs/promises");
  await fs.mkdir(dirname(path), { recursive: true });
  await fs.writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function readJsonFile<T>(path: string): Promise<T | null> {
  const fs = await import("node:fs/promises");
  try {
    const raw = await fs.readFile(path, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

async function countJsonLines(path: string): Promise<number> {
  const fs = await import("node:fs/promises");
  try {
    const raw = await fs.readFile(path, "utf8");
    return raw.split(/\r?\n/).filter(Boolean).length;
  } catch {
    return 0;
  }
}

function buildTomorrowOperatorChecklist(args: {
  config: ReturnType<typeof getConfig>;
  selection: Awaited<ReturnType<typeof buildDailyStrategyPlan>>["selection"];
}): string[] {
  const { config, selection } = args;
  const demoAccountLanes = buildDemoAccountStrategyLanes({
    config: config.live,
    enabledStrategies: selection.enabledStrategies
  });

  return [
    `Keep the lane constrained to ${config.guardrails.allowedSymbols.join(", ")} in ${config.mode} mode.`,
    `Trade only during ${config.guardrails.sessionStartCt} CT to ${config.guardrails.lastEntryCt} CT, flat by ${config.guardrails.flatByCt} CT.`,
    `Respect hard risk rails: min RR ${config.guardrails.minRr}, max ${config.guardrails.maxContracts} contract(s), max ${config.guardrails.maxTradesPerDay} trade(s), max daily loss ${config.guardrails.maxDailyLossR}R.`,
    demoAccountLanes.length > 0
      ? `Keep the demo lanes split by account: ${demoAccountLanes.map((lane) => `${lane.label ?? `slot-${lane.slot}`}=${lane.primaryStrategy ?? "standby"}`).join("; ")}.`
      : "No demo account lanes are configured yet. Fill RH_TOPSTEP_ALLOWED_ACCOUNT_ID or RH_TOPSTEP_ALLOWED_ACCOUNT_IDS before attempting any routed Topstep work.",
    selection.selectedExecutionPlan.action === "paper-trade"
      ? `Paper-trade only the top regime-aligned candidate on ${selection.selectedExecutionPlan.candidate?.symbol ?? selection.preferredSymbols[0] ?? "NQ"}.`
      : "Stand down on execution if the promotion gate is still failing. Use the session for shadow decisions, screenshots, and journal capture only.",
    config.live.readOnly
      ? "Keep Topstep integration read-only. Do not submit orders through the adapter yet."
      : "If read-only is lifted later, keep demo-only account lock enforced.",
    "Capture every candidate, rejection reason, and session outcome so the next research pass can learn from tomorrow."
  ];
}

async function loadFreshResearchStrategyFeed(
  latestResearcherRun: ResearcherRunReport | null
): Promise<Awaited<ReturnType<typeof loadLatestResearchStrategyFeed>>> {
  if (!latestResearcherRun?.runId || latestResearcherRun.strategyHypothesesCount <= 0) {
    return null;
  }
  return loadLatestResearchStrategyFeed(undefined, {
    requiredRunId: latestResearcherRun.runId,
    maxAgeMs: 24 * 60 * 60 * 1000
  });
}

async function runSim(): Promise<void> {
  const config = getConfig();
  const bars = generateSyntheticBars({ symbols: config.guardrails.allowedSymbols });
  const result = await runBacktest({
    bars,
    strategy: buildDefaultEnsemble(config),
    config,
    newsGate: createNewsGate(config)
  });

  const summary = summarizeTrades(result.trades);
  await writeJournal(config.journalPath, result.trades);
  console.log(JSON.stringify({
    summary,
    rejectedSignals: result.rejectedSignals,
    rejectedReasonCounts: result.rejectedReasonCounts,
    rejectedSignalRecords: result.rejectedSignalRecords,
    journalPath: config.journalPath
  }, null, 2));
}

async function runCsvBacktest(csvPath?: string): Promise<void> {
  const config = getConfig();
  const targetPath = csvPath ? resolve(csvPath) : undefined;
  const bars = targetPath ? await loadBarsFromCsv(targetPath) : generateSyntheticBars({ symbols: config.guardrails.allowedSymbols });
  const result = await runBacktest({
    bars,
    strategy: buildDefaultEnsemble(config),
    config,
    newsGate: createNewsGate(config)
  });

  const summary = summarizeTrades(result.trades);
  await writeJournal(config.journalPath, result.trades);
  console.log(JSON.stringify({
    summary,
    rejectedSignals: result.rejectedSignals,
    rejectedReasonCounts: result.rejectedReasonCounts,
    rejectedSignalRecords: result.rejectedSignalRecords,
    journalPath: config.journalPath
  }, null, 2));
}

async function runEvolution(): Promise<void> {
  const config = getConfig();
  const trades = await readJournal(config.journalPath);
  const proposals = proposeEvolution(trades, config);
  console.log(JSON.stringify({ journalPath: config.journalPath, proposals }, null, 2));
}

async function runResearch(csvPath?: string): Promise<void> {
  const config = getConfig();
  const targetPath = csvPath ? resolve(csvPath) : undefined;
  const bars = targetPath
    ? await loadBarsFromCsv(targetPath)
    : generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 6,
        seed: 11
      });
  if (targetPath) {
    maybeEnforceResearchQualityGate(bars);
  }
  const result = await runWalkforwardResearch({
    baseConfig: config,
    bars,
    newsGate: createNewsGate(config)
  });

  console.log(JSON.stringify(result, null, 2));
}

async function runDayPlan(csvPath?: string): Promise<void> {
  const config = getConfig();
  const targetPath = csvPath ? resolve(csvPath) : undefined;
  const bars = targetPath
    ? await loadBarsFromCsv(targetPath)
    : generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 6,
        seed: 37
      });

  if (targetPath) {
    maybeEnforceResearchQualityGate(bars);
  }

  const latestResearcherRun = await readLatestResearcherRunReport();
  const researchStrategyFeed = await loadFreshResearchStrategyFeed(latestResearcherRun);
  const result = await buildDailyStrategyPlan({
    bars: selectRecentPlanningBars(bars),
    baseConfig: config,
    newsGate: createNewsGate(config),
    researchStrategyFeed
  });

  console.log(JSON.stringify(result, null, 2));
}

async function runDashboard(csvPath?: string): Promise<void> {
  const config = getConfig();
  const targetPath = csvPath ? resolve(csvPath) : undefined;
  const bars = targetPath
    ? await loadBarsFromCsv(targetPath)
    : generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 6,
        seed: 41
      });

  if (targetPath) {
    maybeEnforceResearchQualityGate(bars);
  }

  const snapshot = await buildDashboardSnapshot({
    bars,
    baseConfig: config,
    newsGate: createNewsGate(config)
  });

  console.log(JSON.stringify(snapshot, null, 2));
}

async function runKillSwitch(args: string[]): Promise<void> {
  const [command, ...reasonParts] = args;
  const config = getConfig();
  const reason = reasonParts.join(" ").trim();

  if (!command || command === "status") {
    const state = await readKillSwitch(config.killSwitchPath);
    console.log(JSON.stringify({
      path: config.killSwitchPath,
      state
    }, null, 2));
    return;
  }

  if (command === "on") {
    const state = await writeKillSwitch({
      path: config.killSwitchPath,
      active: true,
      reason
    });
    console.log(JSON.stringify({
      path: config.killSwitchPath,
      state
    }, null, 2));
    return;
  }

  if (command === "off") {
    const state = await writeKillSwitch({
      path: config.killSwitchPath,
      active: false,
      reason
    });
    console.log(JSON.stringify({
      path: config.killSwitchPath,
      state
    }, null, 2));
    return;
  }

  throw new Error(`Unknown kill-switch command: ${command}`);
}

async function runJarvis(csvPath?: string): Promise<void> {
  const config = getConfig();
  const targetPath = csvPath ? resolve(csvPath) : undefined;
  const bars = targetPath
    ? await loadBarsFromCsv(targetPath)
    : generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 6,
        seed: 23
      });
  if (targetPath) {
    maybeEnforceResearchQualityGate(bars);
  }

  const research = await runWalkforwardResearch({
    baseConfig: config,
    bars,
    newsGate: createNewsGate(config)
  });
  const report = buildAgenticFundReport({ research, config });

  console.log(JSON.stringify({
    report,
    research,
    agentStatus: report.agentStatus,
    evolutionPlan: report.evolutionPlan
  }, null, 2));
}

async function runJarvisLoop(csvPath?: string): Promise<void> {
  const config = getConfig();
  const targetPath = csvPath ? resolve(csvPath) : undefined;
  const bars = targetPath
    ? await loadBarsFromCsv(targetPath)
    : generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 6,
        seed: 29
      });
  if (targetPath) {
    maybeEnforceResearchQualityGate(bars);
  }

  const loop = await runAgenticImprovementLoop({
    baseConfig: config,
    bars,
    newsGate: createNewsGate(config)
  });

  console.log(JSON.stringify(loop, null, 2));
}

function parseJarvisBriefArgs(args: string[]): { csvPath?: string; operatorNote?: string } {
  const noteIndex = args.indexOf("--note");
  const csvPath = args[0] && args[0] !== "--note" ? args[0] : undefined;
  const operatorNote = noteIndex >= 0 ? args.slice(noteIndex + 1).join(" ").trim() || undefined : undefined;

  return { csvPath, operatorNote };
}

async function runJarvisBrief(args: string[]): Promise<void> {
  const { csvPath, operatorNote } = parseJarvisBriefArgs(args);
  const config = getConfig();
  const targetPath = csvPath ? resolve(csvPath) : undefined;
  const bars = targetPath
    ? await loadBarsFromCsv(targetPath)
    : generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 6,
        seed: 31
      });
  if (targetPath) {
    maybeEnforceResearchQualityGate(bars);
  }

  const brief = await buildJarvisBrief({
    bars,
    baseConfig: config,
    newsGate: createNewsGate(config),
    operatorNote
  });

  console.log(JSON.stringify(brief, null, 2));
}

async function runCsvInspect(csvPath?: string): Promise<void> {
  if (!csvPath) {
    throw new Error("inspect-csv requires a CSV path.");
  }

  const targetPath = resolve(csvPath);
  const inspection = await inspectBarsFromCsv(targetPath);
  console.log(JSON.stringify(inspection, null, 2));
}

async function runFetchFreeData(args: string[]): Promise<void> {
  const [symbol, intervalRaw, rangeRaw, outPathRaw, providerRaw] = args;
  if (!symbol) {
    throw new Error("fetch-free requires at least <symbol>.");
  }

  const interval = parseInterval(intervalRaw);
  const range = rangeRaw ?? (interval === "1d" ? "1y" : "5d");
  const provider = parseProvider(providerRaw);
  const defaultFile = `data/free/${symbol.toUpperCase()}-${interval}-${range}.csv`;
  const outPath = outPathRaw ? resolve(outPathRaw) : resolve(defaultFile);

  const result = await fetchFreeBars({
    symbol,
    interval,
    range,
    provider
  });
  const writtenPath = await writeBarsCsv({ bars: result.bars, outPath });

  console.log(JSON.stringify({
    command: "fetch-free",
    symbol: symbol.toUpperCase(),
    interval,
    range,
    providerRequested: provider,
    providerUsed: result.providerUsed,
    providerSymbol: result.providerSymbol,
    bars: result.bars.length,
    startTs: result.bars[0]?.ts,
    endTs: result.bars[result.bars.length - 1]?.ts,
    outPath: writtenPath,
    warnings: result.warnings
  }, null, 2));
}

async function runFetchFreeUniverse(args: string[]): Promise<void> {
  const [intervalRaw, rangeRaw, outDirRaw, providerRaw] = args;
  const interval = parseInterval(intervalRaw);
  const range = rangeRaw ?? (interval === "1d" ? "1y" : "5d");
  const provider = parseProvider(providerRaw);
  const outDir = outDirRaw ? resolve(outDirRaw) : resolve("data/free");

  const outputs: Array<{
    symbol: string;
    outPath?: string;
    bars?: number;
    providerUsed?: string;
    error?: string;
  }> = [];
  const combined = [] as Awaited<ReturnType<typeof fetchFreeBars>>["bars"];

  for (const symbol of DEFAULT_UNIVERSE_SYMBOLS) {
    try {
      const result = await fetchFreeBars({
        symbol,
        interval,
        range,
        provider
      });

      const outPath = resolve(outDir, `${symbol}-${interval}-${range}.csv`);
      await writeBarsCsv({ bars: result.bars, outPath });
      combined.push(...result.bars);
      outputs.push({
        symbol,
        outPath,
        bars: result.bars.length,
        providerUsed: result.providerUsed
      });
    } catch (error) {
      outputs.push({
        symbol,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }

  const combinedPath = resolve(outDir, `ALL-${DEFAULT_UNIVERSE_SYMBOLS.length}MARKETS-${interval}-${range}.csv`);
  if (combined.length > 0) {
    await writeBarsCsv({ bars: combined, outPath: combinedPath });
  }

  console.log(JSON.stringify({
    command: "fetch-free-universe",
    interval,
    range,
    providerRequested: provider,
    symbols: DEFAULT_UNIVERSE_SYMBOLS,
    successfulSymbols: outputs.filter((entry) => !entry.error).length,
    failedSymbols: outputs.filter((entry) => entry.error).length,
    combinedBars: combined.length,
    combinedPath: combined.length > 0 ? combinedPath : undefined,
    outputs
  }, null, 2));
}

async function runBtcFiveMinuteEdge(args: string[]): Promise<void> {
  const [csvPathRaw, liveUpImpliedRaw] = args;
  const csvPath = resolve(csvPathRaw ?? "data/free/BTCUSD-5m-1mo.csv");
  const bars = await loadBarsFromCsv(csvPath);
  const liveUpImplied = liveUpImpliedRaw
    ? (() => {
        const parsed = Number(liveUpImpliedRaw);
        if (!Number.isFinite(parsed)) {
          throw new Error(`Invalid liveUpImplied value: ${liveUpImpliedRaw}`);
        }
        return parsed > 1 ? parsed / 100 : parsed;
      })()
    : undefined;
  const report = buildBtcFiveMinuteEdgeReport({
    bars: bars.filter((bar) => bar.symbol === "BTCUSD"),
    liveUpImplied
  });
  console.log(JSON.stringify({ command: "btc-5m-edge", csvPath, report }, null, 2));
}

async function runOptionsOneDayToExpiryReport(args: string[]): Promise<void> {
  const [underlyingRaw] = args;
  const underlying = (underlyingRaw ?? "SPY").toUpperCase();
  const apiKey = process.env.RH_POLYGON_API_KEY;
  const alpacaApiKey = process.env.ALPACA_API_KEY;
  const alpacaSecretKey = process.env.ALPACA_SECRET_KEY;

  try {
    if (apiKey) {
      const snapshots = await fetchPolygonOptionSnapshots({
        underlying,
        apiKey,
        baseUrl: process.env.RH_POLYGON_BASE_URL,
        limit: 100
      });
      const selectedExpirationDate = snapshots
        .map((row) => row.expirationDate)
        .filter((value): value is string => Boolean(value))
        .sort()[0];
      const report = buildOneDayToExpiryOptionReport({
        underlying,
        snapshots,
        source: "polygon",
        selectedExpirationDate
      });
      console.log(JSON.stringify({ command: "options-1dte-report", report }, null, 2));
      return;
    }
  } catch {
    // fall through to the next available provider
  }

  if (alpacaApiKey && alpacaSecretKey) {
    const alpaca = await fetchAlpacaOptionSnapshots({
      underlying,
      apiKey: alpacaApiKey,
      secretKey: alpacaSecretKey,
      feed: "indicative",
      limit: 1000
    });
    const selectedExpirationDate = alpaca.snapshots
      .map((row) => row.expirationDate)
      .filter((value): value is string => Boolean(value))
      .sort()[0];
    const underlyingPrice = await fetchAlpacaUnderlyingPrice({
      underlying,
      apiKey: alpacaApiKey,
      secretKey: alpacaSecretKey
    });
    const report = buildOneDayToExpiryOptionReport({
      underlying,
      snapshots: alpaca.snapshots,
      source: "alpaca",
      selectedExpirationDate,
      underlyingPrice
    });
    console.log(JSON.stringify({ command: "options-1dte-report", report }, null, 2));
    return;
  }

  const yahoo = await fetchYahooOptionSnapshots({ underlying });
  const report = buildOneDayToExpiryOptionReport({
    underlying,
    snapshots: yahoo.snapshots,
    source: "yahoo",
    selectedExpirationDate: yahoo.selectedExpirationDate,
    underlyingPrice: yahoo.underlyingPrice
  });
  console.log(JSON.stringify({ command: "options-1dte-report", report }, null, 2));
}

async function runDataQuality(args: string[]): Promise<void> {
  const [csvPath, minCoverageRaw, maxEndLagRaw] = args;
  if (!csvPath) {
    throw new Error("data-quality requires <csvPath>.");
  }

  const targetPath = resolve(csvPath);
  const bars = await loadBarsFromCsv(targetPath);
  const report = assessBarsForResearch(bars, {
    minCoveragePct: minCoverageRaw ? Number(minCoverageRaw) : undefined,
    maxEndLagMinutes: maxEndLagRaw ? Number(maxEndLagRaw) : undefined
  });

  console.log(JSON.stringify(report, null, 2));
}

async function runNormalizeUniverse(args: string[]): Promise<void> {
  const [csvPath, outPathRaw] = args;
  if (!csvPath) {
    throw new Error("normalize-universe requires <csvPath>.");
  }

  const inputPath = resolve(csvPath);
  const bars = await loadBarsFromCsv(inputPath);
  const normalized = normalizeUniverseByInnerTimestamp(bars);
  const outPath = outPathRaw
    ? resolve(outPathRaw)
    : resolve(inputPath.replace(/\.csv$/i, "-normalized.csv"));

  const writtenPath = await writeBarsCsv({ bars: normalized.bars, outPath });
  console.log(JSON.stringify({
    command: "normalize-universe",
    inputPath,
    outputPath: writtenPath,
    inputRows: normalized.inputRows,
    outputRows: normalized.outputRows,
    symbols: normalized.symbols,
    keptTimestamps: normalized.keptTimestamps,
    droppedTimestamps: normalized.droppedTimestamps,
    coverageBefore: normalized.coverageBefore,
    coverageAfter: normalized.coverageAfter
  }, null, 2));
}

async function runOosRolling(args: string[]): Promise<void> {
  const [csvPath, windowsRaw, minTrainRaw, testDaysRaw, embargoRaw] = args;
  if (!csvPath) {
    throw new Error("oos-rolling requires <csvPath>.");
  }

  const config = getConfig();
  const targetPath = resolve(csvPath);
  const bars = await loadBarsFromCsv(targetPath);
  maybeEnforceResearchQualityGate(bars);

  const result = await runRollingOosEvaluation({
    bars,
    baseConfig: config,
    newsGate: createNewsGate(config),
    windows: windowsRaw ? Number(windowsRaw) : Number.parseInt(process.env.BILL_ROLLING_OOS_WINDOWS ?? "4", 10),
    minTrainDays: minTrainRaw ? Number(minTrainRaw) : Number.parseInt(process.env.BILL_ROLLING_OOS_MIN_TRAIN_DAYS ?? "20", 10),
    testDays: testDaysRaw ? Number(testDaysRaw) : Number.parseInt(process.env.BILL_ROLLING_OOS_TEST_DAYS ?? "5", 10),
    embargoDays: embargoRaw ? Number(embargoRaw) : Number.parseInt(process.env.BILL_ROLLING_OOS_EMBARGO_DAYS ?? "1", 10)
  });

  console.log(JSON.stringify(result, null, 2));
}

async function runLiveReadiness(args: string[]): Promise<void> {
  const [csvPath, iterationsRaw] = args;
  const config = getConfig();
  const requestedPath = resolvePaperLoopCsvPath(csvPath);
  const prepared = await prepareFuturesLoopDataset({
    csvPath: requestedPath
  });
  const targetPath = prepared.selectedPath;
  const bars = await loadBarsFromCsv(targetPath);
  maybeEnforceResearchQualityGate(bars);

  const result = await runLiveDeploymentReadiness({
    bars,
    baseConfig: config,
    newsGate: createNewsGate(config),
    iterations: iterationsRaw ? Number(iterationsRaw) : 3
  });

  console.log(JSON.stringify({
    ...result,
    requestedPath,
    csvPath: targetPath,
    preflight: {
      refreshed: prepared.refreshed,
      priorStatus: prepared.status,
      refreshReport: prepared.refreshReport,
      warnings: prepared.warnings
    },
    agentStatus: result.final.report.agentStatus,
    evolutionPlan: result.final.report.evolutionPlan
  }, null, 2));
}

async function runTomorrowDemo(args: string[]): Promise<void> {
  const [csvPath] = args;

  const config = getConfig();
  const requestedPath = resolvePaperLoopCsvPath(csvPath);
  const prepared = await prepareFuturesLoopDataset({
    csvPath: requestedPath
  });
  const targetPath = prepared.selectedPath;
  const inspection = await inspectBarsFromCsv(targetPath);
  const bars = await loadBarsFromCsv(targetPath);
  maybeEnforceResearchQualityGate(bars);

  const dataQuality = assessBarsForResearch(bars, {
    requiredSymbols: config.guardrails.allowedSymbols
  });
  const latestResearcherRun = await readLatestResearcherRunReport();
  const researchStrategyFeed = await loadFreshResearchStrategyFeed(latestResearcherRun);
  const plan = await buildDailyStrategyPlan({
    bars: selectRecentPlanningBars(bars),
    baseConfig: config,
    newsGate: createNewsGate(config),
    researchStrategyFeed
  });
  const allowedDemoAccounts = listAllowedDemoAccounts(config.live);
  const demoAccountLanes = buildDemoAccountStrategyLanes({
    config: config.live,
    enabledStrategies: plan.selection.enabledStrategies
  });

  const demoAccountLocked = isDemoAccountLockSatisfied(config.live);

  const blockers = [
    ...(!dataQuality.pass ? ["Research dataset failed data-quality checks."] : []),
    ...(plan.report.deployableNow ? [] : plan.report.issues.map((issue) => issue.summary)),
    ...(!demoAccountLocked ? ["Topstep demo-only account lock is incomplete or mismatched."] : []),
    ...(config.live.readOnly ? ["Topstep adapter remains read-only, so tomorrow is shadow/demo-only rather than routed execution."] : [])
  ];

  console.log(JSON.stringify({
    command: "demo-tomorrow",
    posture: {
      mode: config.mode,
      accountPhase: config.accountPhase,
      liveExecutionEnabled: config.live.enabled,
      demoOnly: config.live.demoOnly,
      readOnly: config.live.readOnly,
      demoAccountLocked,
      allowedDemoAccounts,
      demoAccountLanes,
      allowedSymbols: config.guardrails.allowedSymbols,
      sessionWindowCt: {
        start: config.guardrails.sessionStartCt,
        lastEntry: config.guardrails.lastEntryCt,
        flatBy: config.guardrails.flatByCt
      },
      hardRiskRails: {
        minRr: config.guardrails.minRr,
        maxContracts: config.guardrails.maxContracts,
        maxTradesPerDay: config.guardrails.maxTradesPerDay,
        maxDailyLossR: config.guardrails.maxDailyLossR,
        maxConsecutiveLosses: config.guardrails.maxConsecutiveLosses
      }
    },
    data: {
      path: targetPath,
      requestedPath,
      preflight: {
        refreshed: prepared.refreshed,
        priorStatus: prepared.status,
        refreshReport: prepared.refreshReport,
        warnings: prepared.warnings
      },
      inspection,
      quality: dataQuality
    },
    tomorrow: {
      readyForPaperDemo: dataQuality.pass,
      readyForRoutedExecution: false,
      selectionMode: plan.selection.mode,
      reportStatus: plan.report.status,
      deployableNow: plan.report.deployableNow,
      selectedProfileId: plan.selection.selectedProfileId,
      selectedProfileDescription: plan.selection.selectedProfileDescription,
      preferredSymbols: plan.selection.preferredSymbols,
      enabledStrategies: plan.selection.enabledStrategies,
      strategyRoles: plan.selection.strategyRoles,
      selectedExecutionPlan: plan.selection.selectedExecutionPlan,
      councilDecision: plan.selection.councilDecision,
      evidencePlan: plan.selection.evidencePlan,
      researchStrategyFeed: plan.selection.researchStrategyFeed,
      whyNotTrading: plan.selection.whyNotTrading,
      learningActions: plan.report.learningActions,
      nextRunChecklist: plan.report.nextRunChecklist,
      operatorChecklist: buildTomorrowOperatorChecklist({ config, selection: plan.selection })
    },
    progressionPath: [
      {
        stage: "demo",
        goal: "Run the selected rehab lane in shadow/demo mode and preserve every decision, blocker, and regime read.",
        gate: "Data quality passes, risk rails hold, and daily review artifacts are complete."
      },
      {
        stage: "challenge",
        goal: "Promote only after repeated green evidence and then trade the prop evaluation conservatively.",
        gate: "promotionGate.ready, consecutive green challenge reports, and stable walk-forward behavior."
      },
      {
        stage: "funded",
        goal: "Tighten risk posture to protect consistency and avoid payout resets.",
        gate: "Passed challenge, funded defaults enabled, and payout survivability remains positive after costs."
      },
      {
        stage: "payout",
        goal: "Prove durable payout extraction before any broader escalation.",
        gate: "Real payouts received and the loop remains stable under funded limits."
      },
      {
        stage: "live",
        goal: "Consider any fuller live path only after payout proof exists.",
        gate: "Explicit approval after documented payout track record."
      }
    ],
    blockers
  }, null, 2));
}

async function runDemoOvernight(args: string[]): Promise<void> {
  const [csvPath] = args;
  const config = getConfig();
  const requestedPath = resolvePaperLoopCsvPath(csvPath);
  const prepared = await prepareFuturesLoopDataset({
    csvPath: requestedPath
  });
  const targetPath = prepared.selectedPath;
  const inspection = await inspectBarsFromCsv(targetPath);
  const bars = await loadBarsFromCsv(targetPath);
  maybeEnforceResearchQualityGate(bars);

  const dataQuality = assessBarsForResearch(bars, {
    requiredSymbols: config.guardrails.allowedSymbols
  });
  const latestResearcherRun = await readLatestResearcherRunReport();
  const researchStrategyFeed = await loadFreshResearchStrategyFeed(latestResearcherRun);
  const plan = await buildDailyStrategyPlan({
    bars: selectRecentPlanningBars(bars),
    baseConfig: config,
    newsGate: createNewsGate(config),
    researchStrategyFeed
  });
  const demoAccountLanes = buildDemoAccountStrategyLanes({
    config: config.live,
    enabledStrategies: plan.selection.enabledStrategies
  });
  const journalPath = resolve(process.env.BILL_FUTURES_DEMO_SAMPLES_JOURNAL_PATH ?? ".rumbling-hedge/logs/futures-demo-samples.jsonl");
  const latestPath = resolve(process.env.BILL_FUTURES_DEMO_SAMPLES_LATEST_PATH ?? ".rumbling-hedge/state/futures-demo.latest.json");
  const sampleSequence = await countJsonLines(journalPath);
  const snapshot = buildDemoStrategySampleSnapshot({
    ts: new Date().toISOString(),
    sampleSequence,
    lanes: demoAccountLanes,
    candidates: plan.selection.configuredStrategyCandidates,
    preferredSymbols: plan.selection.preferredSymbols,
    allowedSymbols: config.guardrails.allowedSymbols,
    availableSymbols: inspection.symbols,
    deployableNow: plan.report.deployableNow,
    whyNotTrading: plan.selection.whyNotTrading,
    evidencePlan: plan.selection.evidencePlan
  });
  const trades = await readJournal(config.journalPath);
  const killSwitchState = await readKillSwitch(config.killSwitchPath);
  const configuredMaxOrders = Number.parseInt(process.env.BILL_FUTURES_DEMO_MAX_ORDERS_PER_RUN ?? "1", 10);
  const demoExecutionEnabled = process.env.BILL_ENABLE_FUTURES_DEMO_EXECUTION === "true";
  const preflightExecutionBlockers = [
    ...(!dataQuality.pass ? ["Research dataset failed data-quality checks."] : []),
    ...(plan.report.deployableNow ? [] : plan.report.issues.map((issue) => issue.summary)),
    ...(plan.selection.selectedExecutionPlan.action === "paper-trade" ? [] : [plan.selection.selectedExecutionPlan.reason])
  ];
  const preExecutionPayload = {
    command: "demo-overnight",
    ts: snapshot.ts,
    journalPath,
    latestPath,
    data: {
      path: targetPath,
      requestedPath,
      preflight: {
        refreshed: prepared.refreshed,
        priorStatus: prepared.status,
        refreshReport: prepared.refreshReport,
        warnings: prepared.warnings
      },
      inspection,
      quality: dataQuality
    },
    posture: {
      mode: config.mode,
      accountPhase: config.accountPhase,
      demoOnly: config.live.demoOnly,
      readOnly: config.live.readOnly,
      deployableNow: plan.report.deployableNow,
      reportStatus: plan.report.status,
      selectedProfileId: plan.selection.selectedProfileId,
      selectedProfileDescription: plan.selection.selectedProfileDescription,
      selectedExecutionPlan: plan.selection.selectedExecutionPlan,
      preferredSymbols: plan.selection.preferredSymbols,
      enabledStrategies: plan.selection.enabledStrategies,
      evidencePlan: plan.selection.evidencePlan,
      researchStrategyFeed: plan.selection.researchStrategyFeed,
      whyNotTrading: plan.selection.whyNotTrading
    },
    sampling: snapshot,
    execution: {
      enabled: demoExecutionEnabled,
      mode: (!config.live.readOnly && demoExecutionEnabled) ? "demo-route" : "shadow-only",
      blockers: preflightExecutionBlockers,
      submittedCount: 0,
      skippedCount: snapshot.laneCount,
      maxOrdersPerRun: Number.isFinite(configuredMaxOrders) && configuredMaxOrders > 0 ? configuredMaxOrders : 1,
      lanes: snapshot.lanes.map((lane) => ({
        accountId: lane.accountId,
        label: lane.label,
        slot: lane.slot,
        primaryStrategy: lane.primaryStrategy,
        focusSymbol: lane.focusSymbol,
        status: "skipped" as const,
        reason: "Execution not attempted yet; posture snapshot persisted before the execution phase.",
        signal: null
      }))
    }
  };
  await writeJsonFile(latestPath, preExecutionPayload);
  const execution = await executeFuturesDemoLanes({
    bars,
    config,
    newsGate: createNewsGate(config),
    trades,
    sampleSnapshot: snapshot,
    killSwitchActive: killSwitchState.active,
    enabled: demoExecutionEnabled,
    maxOrdersPerRun: Number.isFinite(configuredMaxOrders) && configuredMaxOrders > 0 ? configuredMaxOrders : 1,
    preflightBlockers: preflightExecutionBlockers
  });

  const payload = {
    command: "demo-overnight",
    ts: snapshot.ts,
    journalPath,
    latestPath,
    data: {
      path: targetPath,
      requestedPath,
      preflight: {
        refreshed: prepared.refreshed,
        priorStatus: prepared.status,
        refreshReport: prepared.refreshReport,
        warnings: prepared.warnings
      },
      inspection,
      quality: dataQuality
    },
    posture: {
      mode: config.mode,
      accountPhase: config.accountPhase,
      demoOnly: config.live.demoOnly,
      readOnly: config.live.readOnly,
      deployableNow: plan.report.deployableNow,
      reportStatus: plan.report.status,
      selectedProfileId: plan.selection.selectedProfileId,
      selectedProfileDescription: plan.selection.selectedProfileDescription,
      selectedExecutionPlan: plan.selection.selectedExecutionPlan,
      preferredSymbols: plan.selection.preferredSymbols,
      enabledStrategies: plan.selection.enabledStrategies,
      evidencePlan: plan.selection.evidencePlan,
      researchStrategyFeed: plan.selection.researchStrategyFeed,
      whyNotTrading: plan.selection.whyNotTrading
    },
    sampling: snapshot,
    execution
  };

  await appendJsonLine(journalPath, payload);
  await writeJsonFile(latestPath, payload);
  console.log(JSON.stringify(payload, null, 2));
}

async function runRiskModel(args: string[]): Promise<void> {
  const [csvPath] = args;
  const config = getConfig();
  const bars = csvPath
    ? await loadBarsFromCsv(resolve(csvPath))
    : generateSyntheticBars({ symbols: collectResearchUniverse(config), days: 5, seed: 57 });

  if (csvPath) {
    maybeEnforceResearchQualityGate(bars);
  }

  const result = await runRiskTradeModel({
    bars,
    baseConfig: config,
    strategy: buildDefaultEnsemble(config),
    newsGate: createNewsGate(config)
  });

  console.log(JSON.stringify(result, null, 2));
}

function parsePredictionSnapshot(value: unknown): PredictionMarketSnapshot | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  if (typeof row.venue !== "string" || typeof row.externalId !== "string" || typeof row.eventTitle !== "string" || typeof row.marketQuestion !== "string" || typeof row.outcomeLabel !== "string" || typeof row.side !== "string" || typeof row.price !== "number") return null;
  return {
    venue: row.venue,
    externalId: row.externalId,
    eventTitle: row.eventTitle,
    marketQuestion: row.marketQuestion,
    outcomeLabel: row.outcomeLabel,
    side: row.side as "yes" | "no",
    expiry: typeof row.expiry === "string" ? row.expiry : undefined,
    settlementText: typeof row.settlementText === "string" ? row.settlementText : undefined,
    price: row.price,
    displayedSize: typeof row.displayedSize === "number" ? row.displayedSize : undefined
  };
}

async function runPredictionScan(args: string[]): Promise<void> {
  const [inputPath] = args;
  if (!inputPath) throw new Error("prediction-scan requires <inputPath>.");
  const raw = await import("node:fs/promises").then((fs) => fs.readFile(resolve(inputPath), "utf8"));
  const markets = JSON.parse(raw) as unknown[];
  const parsed = markets.map(parsePredictionSnapshot).filter((value): value is PredictionMarketSnapshot => Boolean(value));
  const scanPolicy = await resolvePredictionScanPolicy(process.env);
  const rows = scanPredictionCandidates({
    markets: parsed,
    fees: DEFAULT_PREDICTION_FEES,
    sizing: buildPredictionSizingConfigFromEnv(process.env),
    policy: scanPolicy
  });
  const diagnostics = diagnosePredictionScan({
    markets: parsed,
    fees: DEFAULT_PREDICTION_FEES,
    sizing: buildPredictionSizingConfigFromEnv(process.env),
    policy: scanPolicy
  });
  const journalPath = resolve(process.env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
  await writePredictionJournal(journalPath, rows);
  const report = buildPredictionReport(rows);
  console.log(JSON.stringify({ command: "prediction-scan", inputPath: resolve(inputPath), journalPath, scanPolicy, counts: report.counts, reasons: report.reasons, venuePairs: report.venuePairs, diagnostics, top10: report.top10 }, null, 2));
}

async function runPredictionTrain(args: string[]): Promise<void> {
  const [journalPathRaw] = args;
  const state = await runPredictionTraining({
    env: process.env,
    journalPath: journalPathRaw ? resolve(journalPathRaw) : undefined
  });
  console.log(JSON.stringify({
    command: "prediction-train",
    ts: state.ts,
    journalPath: state.journalPath,
    policyPath: state.policyPath,
    statePath: state.statePath,
    historyPath: state.historyPath,
    trainingSetPath: state.trainingSetPath,
    baselinePolicy: state.baselinePolicy,
    selectedPolicy: state.selectedPolicy,
    baselineEvaluation: state.baselineEvaluation,
    selectedEvaluation: state.selectedEvaluation,
    recentCycleSummary: state.recentCycleSummary,
    sourceSummary: state.sourceSummary,
    recommendations: state.recommendations
  }, null, 2));
}

async function runPredictionCollect(args: string[]): Promise<void> {
  const [sourceRaw, limitRaw, outPathRaw] = args;
  const source = (sourceRaw ?? "polymarket").toLowerCase();
  const limit = limitRaw ? Number.parseInt(limitRaw, 10) : 25;

  if (!Number.isFinite(limit) || limit <= 0) {
    throw new Error(`prediction-collect limit must be a positive integer: ${limitRaw}`);
  }

  const { markets, diagnostics, policy } = await collectPredictionSnapshots({
    source,
    limit,
    env: process.env
  });

  const outPath = resolve(outPathRaw ?? process.env.BILL_PREDICTION_COLLECT_OUTPUT_PATH ?? `.rumbling-hedge/runtime/prediction/${source}-live-snapshot.json`);
  const fs = await import("node:fs/promises");
  await fs.mkdir(dirname(outPath), { recursive: true });
  await fs.writeFile(outPath, `${JSON.stringify(markets, null, 2)}\n`, "utf8");
  const venueCounts = markets.reduce<Record<string, number>>((acc, market) => {
    acc[market.venue] = (acc[market.venue] ?? 0) + 1;
    return acc;
  }, {});

  console.log(JSON.stringify({
    command: "prediction-collect",
    source,
    policy,
    diagnostics,
    count: markets.length,
    limit,
    outPath,
    venueCounts,
    sample: markets.slice(0, 3)
  }, null, 2));
}

async function runPredictionReport(args: string[]): Promise<void> {
  const [journalPathRaw] = args;
  const journalPath = resolve(journalPathRaw ?? process.env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
  const rows = await readPredictionJournal(journalPath);
  const report = buildPredictionReport(rows);
  console.log(JSON.stringify({ command: "prediction-report", journalPath, counts: report.counts, reasons: report.reasons, venuePairs: report.venuePairs, top10: report.top10 }, null, 2));
}

async function runPredictionExecute(args: string[]): Promise<void> {
  const [journalPathRaw] = args;
  const journalPath = resolve(journalPathRaw ?? process.env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
  const rows = await readPredictionJournal(journalPath);
  const report = buildPredictionReport(rows);
  const eligible = report.top10.filter((row) => row.verdict === "paper-trade");
  const config = buildExecutionConfigFromEnv(process.env);
  const fillsPath = resolve(config.journalPath);
  const existing = await readFillsJournal(fillsPath);
  const reviewPath = resolve(process.env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
  const promotionPath = resolve(process.env.BILL_PROMOTION_STATE_PATH ?? ".rumbling-hedge/state/promotion-state.json");
  const review = await readJsonFile<PredictionCycleReview>(reviewPath);
  const promotion = await readJsonFile<BillPromotionState>(promotionPath);
  const authorization = authorizePredictionExecution({
    mode: config.mode,
    review,
    promotion
  });
  const routerInput =
    eligible.length === 0 && config.mode === "paper" && config.demoSeedFill
      ? report.top10
      : eligible;
  const outcome = authorization.ok
    ? routePredictionCandidates(routerInput, {
        config: { ...config, journalPath: fillsPath },
        existingFills: existing
      })
    : {
        placed: [],
        skipped: routerInput.map((row) => ({
          candidateId: row.candidateId,
          reason: authorization.reason ?? "prediction execution is not authorized"
        })),
        totalStake: 0,
        totalMaxLoss: 0,
        mode: config.mode
      };
  if (outcome.placed.length > 0) {
    await appendFills(fillsPath, outcome.placed);
  }
  const liveGate = config.mode === "live" ? evaluateLiveGate(process.env) : null;
  console.log(
    JSON.stringify(
      {
        command: "prediction-execute",
        journalPath,
        fillsJournalPath: fillsPath,
        mode: outcome.mode,
        liveGate,
        authorization,
        reviewPath,
        promotionPath,
        eligibleCount: eligible.length,
        placedCount: outcome.placed.length,
        skippedCount: outcome.skipped.length,
        totalStake: Number(outcome.totalStake.toFixed(4)),
        totalMaxLoss: Number(outcome.totalMaxLoss.toFixed(4)),
        stakeCurrency: config.stakeCurrency,
        placed: outcome.placed,
        skipped: outcome.skipped
      },
      null,
      2
    )
  );
}

async function runPredictionReview(args: string[]): Promise<void> {
  const [journalPathRaw, snapshotPathRaw] = args;
  const journalPath = resolve(journalPathRaw ?? process.env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
  const snapshotPath = resolve(snapshotPathRaw ?? process.env.BILL_PREDICTION_COLLECT_OUTPUT_PATH ?? ".rumbling-hedge/runtime/prediction/combined-live-snapshot.json");
  const cycleHistoryPath = resolve(process.env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl");
  const rows = await readPredictionJournal(journalPath);
  const report = buildPredictionReport(rows);
  const raw = await import("node:fs/promises").then((fs) => fs.readFile(snapshotPath, "utf8")).catch(() => "[]");
  const markets = JSON.parse(raw) as Array<{ venue?: string }>;
  const recentCycles = (await readJsonlRecords(cycleHistoryPath)).slice(-20);
  const venueCounts = markets.reduce<Record<string, number>>((acc, market) => {
    const venue = typeof market.venue === "string" ? market.venue : "unknown";
    acc[venue] = (acc[venue] ?? 0) + 1;
    return acc;
  }, {});
  const review = buildPredictionCycleReview({
    ts: new Date().toISOString(),
    policy: buildPredictionSourcePolicyFromEnv(process.env),
    venueCounts,
    counts: report.counts,
    rows,
    recentCycles
  });
  const reviewPath = resolve(process.env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
  const fs = await import("node:fs/promises");
  await fs.mkdir(dirname(reviewPath), { recursive: true });
  await fs.writeFile(reviewPath, `${JSON.stringify(review, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ command: "prediction-review", journalPath, snapshotPath, reviewPath, review }, null, 2));
}

async function runPredictionCopyDemo(): Promise<void> {
  const report = await buildPredictionCopyDemoReport();
  const reportPath = resolve(process.env.BILL_PREDICTION_COPY_DEMO_PATH ?? ".rumbling-hedge/state/prediction-copy-demo.latest.json");
  const historyPath = resolve(process.env.BILL_PREDICTION_COPY_DEMO_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-copy-demo-history.jsonl");
  await writeJsonFile(reportPath, report);
  await appendJsonLine(historyPath, report);
  console.log(JSON.stringify({
    command: "prediction-copy-demo",
    reportPath,
    historyPath,
    report
  }, null, 2));
}

async function runPromotionStatus(): Promise<void> {
  const state = await readPromotionState(process.env.BILL_PROMOTION_STATE_PATH);
  console.log(JSON.stringify({ command: "promotion-status", state }, null, 2));
}

async function runPromotionReview(args: string[]): Promise<void> {
  const [journalPathRaw, snapshotPathRaw] = args;
  const journalPath = resolve(journalPathRaw ?? process.env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
  const snapshotPath = resolve(snapshotPathRaw ?? process.env.BILL_PREDICTION_COLLECT_OUTPUT_PATH ?? ".rumbling-hedge/runtime/prediction/combined-live-snapshot.json");
  const cycleHistoryPath = resolve(process.env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl");
  const rows = await readPredictionJournal(journalPath);
  const report = buildPredictionReport(rows);
  const raw = await import("node:fs/promises").then((fs) => fs.readFile(snapshotPath, "utf8")).catch(() => "[]");
  const markets = JSON.parse(raw) as Array<{ venue?: string }>;
  const recentCycles = (await readJsonlRecords(cycleHistoryPath)).slice(-20);
  const venueCounts = markets.reduce<Record<string, number>>((acc, market) => {
    const venue = typeof market.venue === "string" ? market.venue : "unknown";
    acc[venue] = (acc[venue] ?? 0) + 1;
    return acc;
  }, {});
  const review = buildPredictionCycleReview({
    ts: new Date().toISOString(),
    policy: buildPredictionSourcePolicyFromEnv(process.env),
    venueCounts,
    counts: report.counts,
    rows,
    recentCycles
  });
  const prior = await readPromotionState(process.env.BILL_PROMOTION_STATE_PATH);
  const state = buildPromotionStateFromPredictionReview({ review, prior });
  const statePath = await writePromotionState(state, process.env.BILL_PROMOTION_STATE_PATH);
  console.log(JSON.stringify({ command: "promotion-review", statePath, state, review }, null, 2));
}

async function runResearchAgentCollect(): Promise<void> {
  const catalog = await collectResearchCatalog(process.env);
  console.log(JSON.stringify(buildResearchCatalogReport(catalog), null, 2));
}

async function runResearchAgentReport(): Promise<void> {
  const catalog = await readResearchCatalog(process.env);
  console.log(JSON.stringify(buildResearchCatalogReport(catalog), null, 2));
}

function parseResearcherRunArgs(args: string[]): {
  targetIds?: string[];
  maxTargets?: number;
  skipJudge?: boolean;
  skipEmbed?: boolean;
  policyPath?: string;
  targetsPath?: string;
  workspaceRoot?: string;
  latestReportPath?: string;
  reportRunsDir?: string;
} {
  const targetIds: string[] = [];
  let maxTargets: number | undefined;
  let skipJudge = false;
  let skipEmbed = false;
  let policyPath: string | undefined;
  let targetsPath: string | undefined;
  let workspaceRoot: string | undefined;
  let latestReportPath: string | undefined;
  let reportRunsDir: string | undefined;

  for (let i = 0; i < args.length; i++) {
    const value = args[i];
    switch (value) {
      case "--target":
        if (args[i + 1]) targetIds.push(args[++i]);
        break;
      case "--max-targets":
        if (args[i + 1]) {
          const parsed = Number.parseInt(args[++i], 10);
          if (Number.isFinite(parsed) && parsed > 0) maxTargets = parsed;
        }
        break;
      case "--skip-judge":
        skipJudge = true;
        break;
      case "--skip-embed":
        skipEmbed = true;
        break;
      case "--policy":
        if (args[i + 1]) policyPath = resolve(args[++i]);
        break;
      case "--targets":
        if (args[i + 1]) targetsPath = resolve(args[++i]);
        break;
      case "--workspace-root":
        if (args[i + 1]) workspaceRoot = resolve(args[++i]);
        break;
      case "--latest-report":
        if (args[i + 1]) latestReportPath = resolve(args[++i]);
        break;
      case "--report-runs-dir":
        if (args[i + 1]) reportRunsDir = resolve(args[++i]);
        break;
      default:
        break;
    }
  }

  return {
    targetIds: targetIds.length > 0 ? targetIds : undefined,
    maxTargets,
    skipJudge,
    skipEmbed,
    policyPath,
    targetsPath,
    workspaceRoot,
    latestReportPath,
    reportRunsDir
  };
}

async function runResearcherRun(args: string[]): Promise<void> {
  const options = parseResearcherRunArgs(args);
  const report = await runResearcherPipeline(options);
  console.log(JSON.stringify({ command: "researcher-run", options, report }, null, 2));
}

async function runResearcherReport(args: string[]): Promise<void> {
  const reportPath = args[0] ? resolve(args[0]) : undefined;
  const report = await readLatestResearcherRunReport(reportPath);
  console.log(JSON.stringify({ command: "researcher-report", reportPath: reportPath ?? "default", report }, null, 2));
}

async function runOllamaSmoke(args: string[]): Promise<void> {
  const { buildOllamaConfigFromEnv, generate, embed, listModels } = await import("./llm/ollama.js");
  const config = buildOllamaConfigFromEnv(process.env);
  const prompt = args[0] ?? "Reply with the single word: ok.";
  const started = Date.now();
  const [models, gen, emb] = await Promise.all([
    listModels(config).catch((e) => ({ error: (e as Error).message })),
    generate(prompt, { maxTokens: 32, temperature: 0 }, config).catch((e) => ({
      error: (e as Error).message
    })),
    embed("prediction-market arbitrage", {}, config).catch((e) => ({
      error: (e as Error).message
    }))
  ]);
  console.log(
    JSON.stringify(
      {
        command: "ollama-smoke",
        baseUrl: config.baseUrl,
        defaultModel: config.defaultModel,
        defaultEmbedModel: config.defaultEmbedModel,
        models: Array.isArray(models) ? models.map((m) => m.name) : models,
        generate: "error" in gen ? gen : { text: gen.text.trim(), durationMs: gen.durationMs, tokens: gen.completionTokens },
        embed: "error" in emb ? emb : { model: emb.model, dim: emb.embedding.length, durationMs: emb.durationMs },
        totalMs: Date.now() - started
      },
      null,
      2
    )
  );
}

async function runNimSmoke(args: string[]): Promise<void> {
  const { buildOpenAiCompatibleConfigFromEnv, generate, listModels } = await import("./llm/openaiCompatible.js");
  const config = buildOpenAiCompatibleConfigFromEnv(process.env);
  const prompt = args[0] ?? "Reply with the single word: ok.";
  const started = Date.now();
  const [models, gen] = await Promise.all([
    listModels(config).catch((e) => ({ error: (e as Error).message })),
    generate(prompt, { maxTokens: 32, temperature: 0 }, config).catch((e) => ({
      error: (e as Error).message
    }))
  ]);
  console.log(
    JSON.stringify(
      {
        command: "nim-smoke",
        provider: config.provider,
        baseUrl: config.baseUrl,
        defaultModel: config.defaultModel,
        models: Array.isArray(models) ? models.map((m) => m.id) : models,
        generate: "error" in gen ? gen : { text: gen.text.trim(), durationMs: gen.durationMs, tokens: gen.completionTokens },
        totalMs: Date.now() - started
      },
      null,
      2
    )
  );
}

async function runMarketTrackStatus(): Promise<void> {
  const policy = buildTrackPolicyFromEnv(process.env);
  const tools = buildBillToolRegistry(process.env, policy);
  const sources = buildBillSourceCatalog(process.env, policy);
  console.log(JSON.stringify({
    command: "market-track-status",
    policy,
    execution: {
      activeTrack: policy.activeTrack,
      activeTracks: policy.activeTracks,
      executionTracks: policy.executionTracks,
      researchTracks: policy.researchTracks
    },
    tools,
    sources
  }, null, 2));
}

async function runOpportunitySnapshot(): Promise<void> {
  const snapshot = await buildOpportunitySnapshot();
  console.log(JSON.stringify(snapshot, null, 2));
}

async function runOpenJarvisStatus(): Promise<void> {
  const status = await buildOpenJarvisStatus({ persistHermesSupervisor: true });
  console.log(JSON.stringify(status, null, 2));
}

async function runOpenJarvisBoard(): Promise<void> {
  const status = await buildOpenJarvisStatus({ persistHermesSupervisor: true });
  const artifacts = await writeOpenJarvisBoardArtifacts({ status });
  console.log(JSON.stringify({
    command: "openjarvis-board",
    generatedAt: status.timestamp,
    founder: status.founder,
    fundPlan: status.bill.fundPlan,
    artifacts
  }, null, 2));
}

async function runAutonomyStatus(): Promise<void> {
  const status = await writeAutonomyStatus();
  console.log(JSON.stringify(status, null, 2));
}

async function runForkIntakeCommand(args: string[]): Promise<void> {
  const [manifestPath, outputDir, maxReposRaw] = args;
  const maxRepos = maxReposRaw
    ? Number.parseInt(maxReposRaw, 10)
    : process.env.BILL_FORK_INTAKE_MAX_REPOS
      ? Number.parseInt(process.env.BILL_FORK_INTAKE_MAX_REPOS, 10)
      : undefined;
  const report = await runForkIntake({
    manifestPath: manifestPath ? resolve(manifestPath) : undefined,
    outputDir: outputDir ? resolve(outputDir) : undefined,
    maxRepos: Number.isFinite(maxRepos) ? maxRepos : undefined
  });
  console.log(JSON.stringify(report, null, 2));
}

async function runStrategyFactoryCommand(args: string[]): Promise<void> {
  const [csvPath, oosCsvPath, outputPath] = args;
  const report = await runStrategyFactory({
    csvPath: csvPath ? resolve(csvPath) : undefined,
    oosCsvPath: oosCsvPath ? resolve(oosCsvPath) : undefined,
    outputPath: outputPath ? resolve(outputPath) : undefined
  });
  console.log(JSON.stringify(report, null, 2));
}

async function runHermesSupervisorStatus(): Promise<void> {
  const status = await buildOpenJarvisStatus({ persistHermesSupervisor: true });
  console.log(JSON.stringify(status.orchestration, null, 2));
}

function requireSupervisorTaskId(args: string[], command: string): string {
  const taskId = args[0]?.trim();
  if (!taskId) {
    throw new Error(`${command} requires <taskId>.`);
  }
  return taskId;
}

async function runHermesSupervisorControl(action: HermesSupervisorDecisionAction, args: string[]): Promise<void> {
  const taskId = requireSupervisorTaskId(args, `hermes-supervisor-${action}`);
  const note = args.slice(1).join(" ").trim() || undefined;
  const initial = await buildOpenJarvisStatus({ persistHermesSupervisor: true });
  await applyHermesSupervisorDecision({
    filePath: initial.orchestration.statePath,
    action,
    taskId,
    note
  });
  const updated = await buildOpenJarvisStatus({
    persistHermesSupervisor: true,
    hermesSupervisorStatePath: initial.orchestration.statePath
  });
  console.log(JSON.stringify({
    command: `hermes-supervisor-${action}`,
    taskId,
    note,
    orchestration: updated.orchestration
  }, null, 2));
}

async function runHermesSupervisorWhy(args: string[]): Promise<void> {
  const taskId = requireSupervisorTaskId(args, "hermes-supervisor-why");
  const status = await buildOpenJarvisStatus({ persistHermesSupervisor: true });
  const artifact = await readHermesSupervisorArtifact(status.orchestration.statePath);
  const task = artifact ? findHermesSupervisorTask(artifact, taskId) : null;
  if (!artifact || !task) {
    throw new Error(`Task ${taskId} is not present in the current Hermes supervisor artifact.`);
  }

  console.log(JSON.stringify({
    command: "hermes-supervisor-why",
    taskId,
    task,
    controls: {
      isPaused: artifact.controls.pausedTaskIds.includes(taskId),
      isApproved: artifact.controls.approvedTaskIds.includes(taskId),
      isCompleted: artifact.controls.completedTaskIds.includes(taskId)
    },
    recentDecisions: artifact.controls.decisionLog.filter((entry) => entry.taskId === taskId).slice(-5)
  }, null, 2));
}

async function runDoctor(): Promise<void> {
  const config = getConfig();
  const policy = buildTrackPolicyFromEnv(process.env);
  const sources = buildBillSourceCatalog(process.env, policy);
  const allowedDemoAccounts = listAllowedDemoAccounts(config.live);
  const demoAccountLanes = buildDemoAccountStrategyLanes({
    config: config.live,
    enabledStrategies: config.enabledStrategies
  });
  const demoAccountLockSatisfied = isDemoAccountLockSatisfied(config.live);
  const warnings: string[] = [];

  if (config.enabledStrategies.length < 2) {
    warnings.push("Only one futures strategy is enabled. Bill will not diversify demo testing until RH_ENABLED_STRATEGIES includes multiple lanes.");
  }
  if (config.live.demoOnly && !demoAccountLockSatisfied) {
    warnings.push("Topstep demo-only lock is incomplete or mismatched. Configure RH_TOPSTEP_ALLOWED_ACCOUNT_ID or RH_TOPSTEP_ALLOWED_ACCOUNT_IDS.");
  }
  if (allowedDemoAccounts.length < 4) {
    warnings.push(`Only ${allowedDemoAccounts.length} Topstep demo account(s) are configured. Set the full four-account allowlist to spread strategy testing cleanly.`);
  }
  if (process.env.BILL_ENABLE_PREDICTION_COLLECT !== "true") {
    warnings.push("Prediction collection is disabled.");
  }
  if (process.env.BILL_ENABLE_PREDICTION_SCAN !== "true") {
    warnings.push("Prediction scan is disabled.");
  }
  if (process.env.BILL_ENABLE_PREDICTION_COPY_DEMO === "false") {
    warnings.push("Prediction copy-demo lane is disabled.");
  }
  if (process.env.BILL_ENABLE_RESEARCH_COLLECT !== "true") {
    warnings.push("Research collection is disabled.");
  }
  if (policy.executionTracks.includes("futures-core") && process.env.BILL_ENABLE_PAPER_LOOP !== "true") {
    warnings.push("Futures execution track is active but the scheduled paper loop is disabled.");
  }
  if (policy.executionTracks.includes("futures-core") && !config.live.username) {
    warnings.push("Futures execution track is active but RH_TOPSTEP_USERNAME is blank.");
  }
  if (policy.executionTracks.includes("futures-core") && !config.live.baseUrl) {
    warnings.push("Futures execution track is active but RH_TOPSTEP_BASE_URL is blank.");
  }
  if (
    policy.executionTracks.includes("futures-core")
    && process.env.RH_TOPSTEP_BASE_URL
    && resolveProjectXApiBaseUrl(process.env.RH_TOPSTEP_BASE_URL) !== process.env.RH_TOPSTEP_BASE_URL
  ) {
    warnings.push(`RH_TOPSTEP_BASE_URL points at a UI/docs URL and will be normalized to ${resolveProjectXApiBaseUrl(process.env.RH_TOPSTEP_BASE_URL)}.`);
  }
  if (policy.executionTracks.includes("futures-core") && process.env.BILL_ENABLE_FUTURES_DEMO_EXECUTION !== "true") {
    warnings.push("Futures execution track can sample lanes, but routed demo execution is still disabled (BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true).");
  }
  if (policy.executionTracks.includes("futures-core") && config.live.readOnly) {
    warnings.push("Futures execution track remains read-only. Bill cannot submit demo orders until RH_TOPSTEP_READ_ONLY=false.");
  }

  console.log(JSON.stringify({
    command: "doctor",
    config: redactConfigForDiagnostics(config),
    runtime: {
      tracks: {
        activeTrack: policy.activeTrack,
        activeTracks: policy.activeTracks,
        executionTracks: policy.executionTracks,
        researchTracks: policy.researchTracks
      },
      strategies: {
        supported: SUPPORTED_STRATEGY_IDS,
        enabled: config.enabledStrategies,
        diversified: config.enabledStrategies.length > 1
      },
      topstep: {
        liveExecutionEnabled: config.live.enabled,
        baseUrl: config.live.baseUrl ?? null,
        demoOnly: config.live.demoOnly,
        readOnly: config.live.readOnly,
        accountId: config.live.accountId ?? null,
        demoAccountLockSatisfied,
        allowedDemoAccounts,
        demoAccountLanes
      },
      billLoops: {
        paperLoopEnabled: process.env.BILL_ENABLE_PAPER_LOOP === "true",
        futuresDemoExecutionEnabled: process.env.BILL_ENABLE_FUTURES_DEMO_EXECUTION === "true",
        paperLoopCsvPath: resolvePaperLoopCsvPath(),
        predictionCollectEnabled: process.env.BILL_ENABLE_PREDICTION_COLLECT === "true",
        predictionScanEnabled: process.env.BILL_ENABLE_PREDICTION_SCAN === "true",
        predictionCopyDemoEnabled: process.env.BILL_ENABLE_PREDICTION_COPY_DEMO !== "false",
        predictionReportEnabled: process.env.BILL_ENABLE_PREDICTION_REPORT !== "false",
        predictionTrainingEnabled: process.env.BILL_ENABLE_PREDICTION_TRAINING !== "false",
        researchCollectEnabled: process.env.BILL_ENABLE_RESEARCH_COLLECT === "true",
        predictionExecutionEnabled: process.env.BILL_ENABLE_PREDICTION_EXECUTE === "true",
        predictionExecutionMode: process.env.BILL_PREDICTION_EXECUTION_MODE ?? "paper"
      },
      sources: {
        active: sources.filter((source) => source.mode === "active").map((source) => source.id),
        missingConfig: sources.filter((source) => source.mode === "missing-config").map((source) => source.id),
        missingForActiveTracks: sources
          .filter((source) => source.requiredForActiveTrack && !source.configured)
          .map((source) => source.id)
      }
    },
    warnings
  }, null, 2));
}

async function main(): Promise<void> {
  const [command, ...args] = process.argv.slice(2);

  switch (command) {
    case "doctor":
      await runDoctor();
      return;
    case "sim":
      await runSim();
      return;
    case "backtest":
      await runCsvBacktest(args[0]);
      return;
    case "evolve":
      await runEvolution();
      return;
    case "research":
      await runResearch(args[0]);
      return;
    case "day-plan":
      await runDayPlan(args[0]);
      return;
    case "dashboard":
      await runDashboard(args[0]);
      return;
    case "kill-switch":
      await runKillSwitch(args);
      return;
    case "inspect-csv":
      await runCsvInspect(args[0]);
      return;
    case "fetch-free":
      await runFetchFreeData(args);
      return;
    case "fetch-free-universe":
      await runFetchFreeUniverse(args);
      return;
    case "btc-5m-edge":
      await runBtcFiveMinuteEdge(args);
      return;
    case "options-1dte-report":
      await runOptionsOneDayToExpiryReport(args);
      return;
    case "data-quality":
      await runDataQuality(args);
      return;
    case "normalize-universe":
      await runNormalizeUniverse(args);
      return;
    case "oos-rolling":
      await runOosRolling(args);
      return;
    case "live-readiness":
      await runLiveReadiness(args);
      return;
    case "demo-tomorrow":
      await runTomorrowDemo(args);
      return;
    case "demo-overnight":
      await runDemoOvernight(args);
      return;
    case "risk-model":
      await runRiskModel(args);
      return;
    case "markov-return":
      await runMarkovReturn(args);
      return;
    case "markov-oos":
      await runMarkovOos(args);
      return;
    case "jarvis":
      await runJarvis(args[0]);
      return;
    case "jarvis-loop":
      await runJarvisLoop(args[0]);
      return;
    case "jarvis-brief":
      await runJarvisBrief(args);
      return;
    case "openjarvis-status":
      await runOpenJarvisStatus();
      return;
    case "openjarvis-board":
      await runOpenJarvisBoard();
      return;
    case "autonomy-status":
      await runAutonomyStatus();
      return;
    case "fork-intake":
      await runForkIntakeCommand(args);
      return;
    case "strategy-factory":
      await runStrategyFactoryCommand(args);
      return;
    case "hermes-supervisor-status":
      await runHermesSupervisorStatus();
      return;
    case "hermes-supervisor-approve":
      await runHermesSupervisorControl("approve", args);
      return;
    case "hermes-supervisor-pause":
      await runHermesSupervisorControl("pause", args);
      return;
    case "hermes-supervisor-resume":
      await runHermesSupervisorControl("resume", args);
      return;
    case "hermes-supervisor-complete":
      await runHermesSupervisorControl("complete", args);
      return;
    case "hermes-supervisor-why":
      await runHermesSupervisorWhy(args);
      return;
    case "prediction-scan":
      await runPredictionScan(args);
      return;
    case "prediction-train":
      await runPredictionTrain(args);
      return;
    case "prediction-collect":
      await runPredictionCollect(args);
      return;
    case "prediction-report":
      await runPredictionReport(args);
      return;
    case "prediction-execute":
      await runPredictionExecute(args);
      return;
    case "prediction-review":
      await runPredictionReview(args);
      return;
    case "prediction-copy-demo":
      await runPredictionCopyDemo();
      return;
    case "opportunity-snapshot":
      await runOpportunitySnapshot();
      return;
    case "promotion-status":
      await runPromotionStatus();
      return;
    case "promotion-review":
      await runPromotionReview(args);
      return;
    case "research-agent-collect":
      await runResearchAgentCollect();
      return;
    case "research-agent-report":
      await runResearchAgentReport();
      return;
    case "researcher-run":
      await runResearcherRun(args);
      return;
    case "researcher-report":
      await runResearcherReport(args);
      return;
    case "market-track-status":
      await runMarketTrackStatus();
      return;
    case "ollama-smoke":
      await runOllamaSmoke(args);
      return;
    case "nim-smoke":
      await runNimSmoke(args);
      return;
    case "prediction-resolve":
      await runPredictionResolve(args);
      return;
    case "prediction-calibration":
      await runPredictionCalibration(args);
      return;
    case "prediction-counterfactual":
      await runPredictionCounterfactual(args);
      return;
    case "prediction-market-analysis-status":
      await runPredictionMarketAnalysisStatus(args);
      return;
    case "flow-collect":
      await runFlowCollect(args);
      return;
    case "flow-scan":
      await runFlowScan(args);
      return;
    case "kronos-forecast":
      await runKronosForecast(args);
      return;
    case "kronos-health":
      await runKronosHealth();
      return;
    case "timesfm-status":
      await runTimesFmStatus(args);
      return;
    default:
      printUsage();
  }
}

async function runPredictionResolve(args: string[]): Promise<void> {
  const journalPath = resolve(args[0] ?? process.env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
  const outputPath = resolve(args[1] ?? process.env.BILL_PREDICTION_RESOLVED_PATH ?? ".rumbling-hedge/runtime/prediction/resolved.jsonl");
  const maxAgeDays = Number.parseInt(args[2] ?? process.env.BILL_PREDICTION_RESOLVE_MAX_AGE_DAYS ?? "60", 10);
  const result = await resolvePredictionJournal({ journalPath, outputPath, maxAgeDays });
  console.log(JSON.stringify({ command: "prediction-resolve", journalPath, outputPath, ...result }, null, 2));
}

async function runPredictionCalibration(args: string[]): Promise<void> {
  const path = resolve(args[0] ?? process.env.BILL_PREDICTION_RESOLVED_PATH ?? ".rumbling-hedge/runtime/prediction/resolved.jsonl");
  const report = await buildCalibrationReportFromJsonl(path);
  console.log(JSON.stringify({ command: "prediction-calibration", resolvedPath: path, report }, null, 2));
}

async function runPredictionCounterfactual(args: string[]): Promise<void> {
  const path = resolve(args[0] ?? process.env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
  const windowHours = Number.parseInt(args[1] ?? "24", 10);
  const report = await buildCounterfactualReport({ journalPath: path, windowHours });
  console.log(summarizeCounterfactual(report));
  console.log("\n---json---");
  console.log(JSON.stringify(report, null, 2));
}

async function runPredictionMarketAnalysisStatus(args: string[]): Promise<void> {
  const [dataRootRaw, reportPathRaw, markdownPathRaw] = args;
  const report = await inspectPredictionMarketAnalysisDataset({
    env: process.env,
    dataRoot: dataRootRaw ? resolve(dataRootRaw) : undefined
  });
  const written = await writePredictionMarketAnalysisReadiness({
    report,
    reportPath: reportPathRaw ? resolve(reportPathRaw) : undefined,
    markdownPath: markdownPathRaw ? resolve(markdownPathRaw) : undefined
  });
  console.log(JSON.stringify({
    ...report,
    reportPath: written.reportPath,
    markdownPath: written.markdownPath
  }, null, 2));
}

async function runFlowCollect(args: string[]): Promise<void> {
  const historyPath = resolve(args[0] ?? process.env.BILL_FLOW_HISTORY_PATH ?? "journals/prediction-flow-history.jsonl");
  const limit = Number.parseInt(args[1] ?? "100", 10);
  const rows = await collectFlowSnapshots({ limitPerVenue: limit });
  await appendFlowSnapshots(historyPath, rows);
  const byVenue: Record<string, number> = {};
  for (const r of rows) byVenue[r.venue] = (byVenue[r.venue] ?? 0) + 1;
  console.log(JSON.stringify({ command: "flow-collect", historyPath, total: rows.length, byVenue }, null, 2));
}

async function runFlowScan(args: string[]): Promise<void> {
  const historyPath = resolve(args[0] ?? process.env.BILL_FLOW_HISTORY_PATH ?? "journals/prediction-flow-history.jsonl");
  const outputPath = resolve(args[1] ?? process.env.BILL_FLOW_SIGNALS_PATH ?? "journals/prediction-flow-signals.json");
  const windowHours = Number.parseInt(args[2] ?? "24", 10);
  const minScore = Number.parseFloat(args[3] ?? "0.6");
  const result = await scanFlowAcceleration({ historyPath, outputPath, windowHours, minCompositeScore: minScore });
  console.log(JSON.stringify({ command: "flow-scan", historyPath, outputPath, ...result }, null, 2));
}

async function runKronosHealth(): Promise<void> {
  const res = await kronosHealth();
  console.log(JSON.stringify({ command: "kronos-health", ...res }, null, 2));
}

async function runTimesFmStatus(args: string[]): Promise<void> {
  const [reportPathRaw, markdownPathRaw] = args;
  const report = await inspectTimesFmReadiness({ env: process.env });
  const written = await writeTimesFmReadiness({
    report,
    reportPath: reportPathRaw ? resolve(reportPathRaw) : undefined,
    markdownPath: markdownPathRaw ? resolve(markdownPathRaw) : undefined
  });
  console.log(JSON.stringify({
    ...report,
    reportPath: written.reportPath,
    markdownPath: written.markdownPath
  }, null, 2));
}

async function runMarkovReturn(args: string[]): Promise<void> {
  const csvPath = args[0];
  if (!csvPath) {
    throw new Error("markov-return requires a CSV path. Usage: markov-return <csvPath> [minTrainingTransitions=60] [signalThreshold=0.001]");
  }
  const minTrainingTransitions = Number.parseInt(args[1] ?? process.env.BILL_MARKOV_MIN_TRAINING_TRANSITIONS ?? "60", 10);
  const signalThreshold = Number.parseFloat(args[2] ?? process.env.BILL_MARKOV_SIGNAL_THRESHOLD ?? "0.001");
  const thresholds = (process.env.BILL_MARKOV_THRESHOLDS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .map((value) => Number.parseFloat(value));
  const bars = await loadBarsFromCsv(resolve(csvPath));
  const report = runMarkovReturnBacktest(bars, {
    minTrainingTransitions,
    signalThreshold,
    thresholds: thresholds.length > 0 ? thresholds : undefined
  });
  console.log(JSON.stringify({ command: "markov-return", csvPath: resolve(csvPath), report }, null, 2));
}

async function findDailyResearchCsvs(root: string): Promise<string[]> {
  const resolvedRoot = resolve(root);
  const found: string[] = [];

  async function walk(dir: string): Promise<void> {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(path);
        continue;
      }
      if (!entry.isFile() || extname(entry.name).toLowerCase() !== ".csv") {
        continue;
      }
      if (/-1d-/.test(entry.name) || path.includes("/daily/")) {
        found.push(path);
      }
    }
  }

  await walk(resolvedRoot);
  return found.sort();
}

async function runMarkovOos(args: string[]): Promise<void> {
  const target = resolve(args[0] ?? process.env.BILL_MARKOV_OOS_PATH ?? "data/research");
  const trainReturns = Number.parseInt(args[1] ?? process.env.BILL_MARKOV_OOS_TRAIN_RETURNS ?? "20", 10);
  const testReturns = Number.parseInt(args[2] ?? process.env.BILL_MARKOV_OOS_TEST_RETURNS ?? "5", 10);
  const stepReturns = Number.parseInt(args[3] ?? process.env.BILL_MARKOV_OOS_STEP_RETURNS ?? `${testReturns}`, 10);
  const thresholds = (process.env.BILL_MARKOV_THRESHOLDS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .map((value) => Number.parseFloat(value));
  const fs = await import("node:fs/promises");
  const stat = await fs.stat(target);
  const csvPaths = stat.isDirectory() ? await findDailyResearchCsvs(target) : [target];
  const barsByPath = await Promise.all(csvPaths.map(async (csvPath) => ({
    csvPath,
    bars: await loadBarsFromCsv(csvPath)
  })));
  const bars = barsByPath.flatMap((item) => item.bars);
  const report = runMarkovOosReport(bars, {
    trainReturns,
    testReturns,
    stepReturns,
    thresholds: thresholds.length > 0 ? thresholds : undefined,
    signalThreshold: Number.parseFloat(process.env.BILL_MARKOV_SIGNAL_THRESHOLD ?? "0.001"),
    minTrainingTransitions: Number.parseInt(process.env.BILL_MARKOV_MIN_TRAINING_TRANSITIONS ?? "60", 10)
  });
  console.log(JSON.stringify({
    command: "markov-oos",
    target,
    csvPaths,
    report
  }, null, 2));
}

async function runKronosForecast(args: string[]): Promise<void> {
  const csvPath = args[0];
  if (!csvPath) {
    throw new Error("kronos-forecast requires a CSV path. Usage: kronos-forecast <csvPath> [lookback=400] [predLen=24]");
  }
  const lookback = Number.parseInt(args[1] ?? "400", 10);
  const predLen = Number.parseInt(args[2] ?? "24", 10);
  const bars = await loadBarsFromCsv(resolve(csvPath));
  if (bars.length < lookback + 1) {
    throw new Error(`kronos-forecast: need >=${lookback + 1} bars, got ${bars.length}`);
  }
  const slice = bars.slice(-lookback);
  const symbol = slice[0]?.symbol ?? "UNKNOWN";
  const history = slice.map((b) => ({
    ts: b.ts,
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
    volume: b.volume
  }));
  const lastTs = Date.parse(slice[slice.length - 1].ts);
  const prevTs = Date.parse(slice[slice.length - 2].ts);
  const stepMs = Math.max(lastTs - prevTs, 60_000);
  const future: string[] = [];
  for (let i = 1; i <= predLen; i++) {
    future.push(new Date(lastTs + i * stepMs).toISOString());
  }
  const predicted = await kronosForecast({
    symbol,
    history,
    futureTimestamps: future,
    maxContext: Number.parseInt(process.env.KRONOS_MAX_CONTEXT ?? "512", 10),
    temperature: 1.0,
    topP: 0.9,
    sampleCount: 1
  });
  console.log(JSON.stringify({ command: "kronos-forecast", symbol, lookback, predLen, predicted }, null, 2));
}

await main();
