import "dotenv/config";
import { resolve } from "node:path";
import { getConfig } from "./config.js";
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
import { runRiskTradeModel } from "./engine/riskModel.js";
import { readJournal, writeJournal } from "./engine/journal.js";
import { summarizeTrades } from "./engine/report.js";
import { runWalkforwardResearch } from "./engine/walkforward.js";
import { runRollingOosEvaluation } from "./engine/rollingOos.js";
import { proposeEvolution } from "./evolution/proposals.js";
import { MockNewsGate } from "./news/mockNewsGate.js";
import { collectResearchUniverse } from "./research/profiles.js";
import { buildDefaultEnsemble } from "./strategies/wctcEnsemble.js";

function printUsage(): void {
  console.log("Commands: doctor | sim | backtest [csvPath] | research [csvPath] | day-plan [csvPath] | dashboard [csvPath] | kill-switch [on|off|status] [reason] | inspect-csv <csvPath> | data-quality <csvPath> [minCoveragePct] [maxEndLagMinutes] | normalize-universe <csvPath> [outPath] | oos-rolling <csvPath> [windows] [minTrainDays] [testDays] [embargoDays] | live-readiness <csvPath> [iterations] | demo-tomorrow <csvPath> [iterations] | risk-model <csvPath> | fetch-free <symbol> [interval] [range] [outPath] [provider] | fetch-free-universe [interval] [range] [outDir] [provider] | evolve | jarvis [csvPath] | jarvis-loop [csvPath] | jarvis-brief [csvPath] [--note text]");
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
  const allowed: FreeDataProvider[] = ["auto", "yahoo", "stooq", "polygon"];
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

  const result = await buildDailyStrategyPlan({
    bars,
    baseConfig: config,
    newsGate: createNewsGate(config)
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
    windows: windowsRaw ? Number(windowsRaw) : 4,
    minTrainDays: minTrainRaw ? Number(minTrainRaw) : 2,
    testDays: testDaysRaw ? Number(testDaysRaw) : 1,
    embargoDays: embargoRaw ? Number(embargoRaw) : 0
  });

  console.log(JSON.stringify(result, null, 2));
}

async function runLiveReadiness(args: string[]): Promise<void> {
  const [csvPath, iterationsRaw] = args;
  if (!csvPath) {
    throw new Error("live-readiness requires <csvPath>.");
  }

  const config = getConfig();
  const targetPath = resolve(csvPath);
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
    agentStatus: result.final.report.agentStatus,
    evolutionPlan: result.final.report.evolutionPlan
  }, null, 2));
}

async function runTomorrowDemo(args: string[]): Promise<void> {
  await runLiveReadiness(args);
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

async function runDoctor(): Promise<void> {
  const config = getConfig();
  console.log(JSON.stringify(config, null, 2));
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
    case "risk-model":
      await runRiskModel(args);
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
    default:
      printUsage();
  }
}

await main();
