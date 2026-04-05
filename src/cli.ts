import "dotenv/config";
import { resolve } from "node:path";
import { getConfig } from "./config.js";
import { loadBarsFromCsv } from "./data/csv.js";
import { generateSyntheticBars } from "./data/synthetic.js";
import { runBacktest } from "./engine/backtest.js";
import { readJournal, writeJournal } from "./engine/journal.js";
import { summarizeTrades } from "./engine/report.js";
import { runWalkforwardResearch } from "./engine/walkforward.js";
import { proposeEvolution } from "./evolution/proposals.js";
import { MockNewsGate } from "./news/mockNewsGate.js";
import { collectResearchUniverse } from "./research/profiles.js";
import { buildDefaultEnsemble } from "./strategies/wctcEnsemble.js";

function printUsage(): void {
  console.log("Commands: doctor | sim | backtest [csvPath] | research [csvPath] | evolve");
}

async function runSim(): Promise<void> {
  const config = getConfig();
  const bars = generateSyntheticBars({ symbols: config.guardrails.allowedSymbols });
  const result = await runBacktest({
    bars,
    strategy: buildDefaultEnsemble(config),
    config,
    newsGate: new MockNewsGate()
  });

  const summary = summarizeTrades(result.trades);
  await writeJournal(config.journalPath, result.trades);
  console.log(JSON.stringify({ summary, rejectedSignals: result.rejectedSignals, journalPath: config.journalPath }, null, 2));
}

async function runCsvBacktest(csvPath?: string): Promise<void> {
  const config = getConfig();
  const targetPath = csvPath ? resolve(csvPath) : undefined;
  const bars = targetPath ? await loadBarsFromCsv(targetPath) : generateSyntheticBars({ symbols: config.guardrails.allowedSymbols });
  const result = await runBacktest({
    bars,
    strategy: buildDefaultEnsemble(config),
    config,
    newsGate: new MockNewsGate()
  });

  const summary = summarizeTrades(result.trades);
  await writeJournal(config.journalPath, result.trades);
  console.log(JSON.stringify({ summary, rejectedSignals: result.rejectedSignals, journalPath: config.journalPath }, null, 2));
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
  const result = await runWalkforwardResearch({
    baseConfig: config,
    bars,
    newsGate: new MockNewsGate()
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
    default:
      printUsage();
  }
}

await main();
