import "dotenv/config";
import { dirname, resolve } from "node:path";
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
import { scanPredictionCandidates } from "./prediction/matcher.js";
import { readPredictionJournal, writePredictionJournal } from "./prediction/journal.js";
import { buildPredictionReport } from "./prediction/report.js";
import { DEFAULT_PREDICTION_FEES } from "./prediction/fees.js";
import type { PredictionMarketSnapshot } from "./prediction/types.js";
import { fetchPolymarketLiveSnapshot } from "./prediction/adapters/polymarket.js";
import { fetchKalshiLiveSnapshot } from "./prediction/adapters/kalshi.js";

function printUsage(): void {
  console.log("Commands: doctor | sim | backtest [csvPath] | research [csvPath] | day-plan [csvPath] | dashboard [csvPath] | kill-switch [on|off|status] [reason] | inspect-csv <csvPath> | data-quality <csvPath> [minCoveragePct] [maxEndLagMinutes] | normalize-universe <csvPath> [outPath] | oos-rolling <csvPath> [windows] [minTrainDays] [testDays] [embargoDays] | live-readiness <csvPath> [iterations] | demo-tomorrow <csvPath> [iterations] | risk-model <csvPath> | fetch-free <symbol> [interval] [range] [outPath] [provider] | fetch-free-universe [interval] [range] [outDir] [provider] | evolve | jarvis [csvPath] | jarvis-loop [csvPath] | jarvis-brief [csvPath] [--note text] | prediction-collect [source] [limit] [outPath] | prediction-scan [inputPath] | prediction-report [journalPath]");
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

function buildTomorrowOperatorChecklist(args: {
  config: ReturnType<typeof getConfig>;
  selection: Awaited<ReturnType<typeof buildDailyStrategyPlan>>["selection"];
}): string[] {
  const { config, selection } = args;

  return [
    `Keep the lane constrained to ${config.guardrails.allowedSymbols.join(", ")} in ${config.mode} mode.`,
    `Trade only during ${config.guardrails.sessionStartCt} CT to ${config.guardrails.lastEntryCt} CT, flat by ${config.guardrails.flatByCt} CT.`,
    `Respect hard risk rails: min RR ${config.guardrails.minRr}, max ${config.guardrails.maxContracts} contract(s), max ${config.guardrails.maxTradesPerDay} trade(s), max daily loss ${config.guardrails.maxDailyLossR}R.`,
    selection.selectedExecutionPlan.action === "paper-trade"
      ? `Paper-trade only the top regime-aligned candidate on ${selection.selectedExecutionPlan.candidate?.symbol ?? selection.preferredSymbols[0] ?? "NQ"}.`
      : "Stand down on execution if the promotion gate is still failing. Use the session for shadow decisions, screenshots, and journal capture only.",
    config.live.readOnly
      ? "Keep Topstep integration read-only. Do not submit orders through the adapter yet."
      : "If read-only is lifted later, keep demo-only account lock enforced.",
    "Capture every candidate, rejection reason, and session outcome so the next research pass can learn from tomorrow."
  ];
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
  const [csvPath] = args;
  if (!csvPath) {
    throw new Error("demo-tomorrow requires <csvPath>.");
  }

  const config = getConfig();
  const targetPath = resolve(csvPath);
  const inspection = await inspectBarsFromCsv(targetPath);
  const bars = await loadBarsFromCsv(targetPath);
  maybeEnforceResearchQualityGate(bars);

  const dataQuality = assessBarsForResearch(bars);
  const plan = await buildDailyStrategyPlan({
    bars,
    baseConfig: config,
    newsGate: createNewsGate(config)
  });

  const demoAccountLocked = !config.live.demoOnly
    ? true
    : Boolean(config.live.allowedAccountId) && (!config.live.accountId || config.live.accountId === config.live.allowedAccountId);

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
  const rows = scanPredictionCandidates({ markets: parsed, fees: DEFAULT_PREDICTION_FEES });
  const journalPath = resolve("journals/prediction-opportunities.jsonl");
  await writePredictionJournal(journalPath, rows);
  const report = buildPredictionReport(rows);
  console.log(JSON.stringify({ command: "prediction-scan", inputPath: resolve(inputPath), journalPath, counts: report.counts, top10: report.top10 }, null, 2));
}

async function runPredictionCollect(args: string[]): Promise<void> {
  const [sourceRaw, limitRaw, outPathRaw] = args;
  const source = (sourceRaw ?? "polymarket").toLowerCase();
  const limit = limitRaw ? Number.parseInt(limitRaw, 10) : 25;

  if (!Number.isFinite(limit) || limit <= 0) {
    throw new Error(`prediction-collect limit must be a positive integer: ${limitRaw}`);
  }

  let markets: PredictionMarketSnapshot[];
  switch (source) {
    case "polymarket":
      markets = await fetchPolymarketLiveSnapshot(limit);
      break;
    case "kalshi":
      markets = await fetchKalshiLiveSnapshot(limit);
      break;
    case "combined":
    case "all": {
      const [polymarket, kalshi] = await Promise.all([
        fetchPolymarketLiveSnapshot(limit),
        fetchKalshiLiveSnapshot(limit)
      ]);
      markets = [...polymarket, ...kalshi];
      break;
    }
    default:
      throw new Error(`Unsupported prediction source: ${source}`);
  }

  const outPath = resolve(outPathRaw ?? `data/prediction/${source}-live-snapshot.json`);
  const fs = await import("node:fs/promises");
  await fs.mkdir(dirname(outPath), { recursive: true });
  await fs.writeFile(outPath, `${JSON.stringify(markets, null, 2)}\n`, "utf8");

  console.log(JSON.stringify({
    command: "prediction-collect",
    source,
    count: markets.length,
    limit,
    outPath,
    sample: markets.slice(0, 3)
  }, null, 2));
}

async function runPredictionReport(args: string[]): Promise<void> {
  const [journalPathRaw] = args;
  const journalPath = resolve(journalPathRaw ?? "journals/prediction-opportunities.jsonl");
  const rows = await readPredictionJournal(journalPath);
  const report = buildPredictionReport(rows);
  console.log(JSON.stringify({ command: "prediction-report", journalPath, counts: report.counts, top10: report.top10 }, null, 2));
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
    case "prediction-scan":
      await runPredictionScan(args);
      return;
    case "prediction-collect":
      await runPredictionCollect(args);
      return;
    case "prediction-report":
      await runPredictionReport(args);
      return;
    default:
      printUsage();
  }
}

await main();
