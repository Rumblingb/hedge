#!/usr/bin/env node
/**
 * Research-only Polymarket CLOB quote-persistence lab.
 *
 * Consumes JSONL written by scripts/polymarket_clob_recorder.mjs and measures
 * whether top-of-book quotes persist over fixed horizons. This is intentionally
 * feature/evidence generation only: no private keys, no orders, no execution.
 */
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const DEFAULT_INPUT = path.resolve(REPO_ROOT, ".rumbling-hedge/prediction/clob", `${new Date().toISOString().slice(0, 10)}-market-channel.jsonl`);
const DEFAULT_OUTPUT = path.resolve(REPO_ROOT, ".rumbling-hedge/state/polymarket-clob-persistence.latest.json");
const DEFAULT_SAMPLES_OUTPUT = path.resolve(REPO_ROOT, ".rumbling-hedge/prediction/clob", `${new Date().toISOString().slice(0, 10)}-persistence-samples.jsonl`);
const DEFAULT_WINDOWS = [5, 15, 30, 60];

function parseArgs(argv) {
  const out = {
    input: process.env.BILL_POLYMARKET_CLOB_JSONL || DEFAULT_INPUT,
    output: process.env.BILL_POLYMARKET_CLOB_PERSISTENCE_PATH || DEFAULT_OUTPUT,
    samplesOutput: process.env.BILL_POLYMARKET_CLOB_PERSISTENCE_SAMPLES || DEFAULT_SAMPLES_OUTPUT,
    windows: (process.env.BILL_POLYMARKET_CLOB_WINDOWS || DEFAULT_WINDOWS.join(","))
      .split(",")
      .map((value) => Number.parseInt(value.trim(), 10))
      .filter((value) => Number.isFinite(value) && value > 0),
    minObservations: Number.parseInt(process.env.BILL_POLYMARKET_CLOB_MIN_OBS || "3", 10)
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--input" && next) out.input = path.resolve(next), i += 1;
    else if (arg === "--output" && next) out.output = path.resolve(next), i += 1;
    else if (arg === "--samples-output" && next) out.samplesOutput = path.resolve(next), i += 1;
    else if (arg === "--windows" && next) out.windows = next.split(",").map((value) => Number.parseInt(value.trim(), 10)).filter((value) => Number.isFinite(value) && value > 0), i += 1;
    else if (arg === "--min-observations" && next) out.minObservations = Number.parseInt(next, 10), i += 1;
  }

  if (out.windows.length === 0) out.windows = DEFAULT_WINDOWS;
  if (!Number.isFinite(out.minObservations) || out.minObservations <= 0) out.minObservations = 3;
  return out;
}

function toNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function parseTimeMs(record) {
  const local = Date.parse(record.localTs || "");
  if (Number.isFinite(local)) return local;
  const exchange = Number(record.exchangeTs);
  return Number.isFinite(exchange) ? exchange : null;
}

async function readJsonl(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  const rows = [];
  for (const [index, line] of raw.split(/\r?\n/).entries()) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      rows.push(JSON.parse(trimmed));
    } catch (error) {
      rows.push({
        localTs: new Date().toISOString(),
        eventType: "parse_error",
        line: index + 1,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }
  return rows;
}

function quoteObservation(args) {
  const { record, assetId, bestBid, bestAsk, source } = args;
  const bid = toNumber(bestBid);
  const ask = toNumber(bestAsk);
  const tsMs = parseTimeMs(record);
  if (!assetId || bid == null || ask == null || tsMs == null) return null;
  if (!(bid > 0 && bid < 1 && ask > 0 && ask < 1 && ask >= bid)) return null;
  const spread = ask - bid;
  return {
    tsMs,
    ts: new Date(tsMs).toISOString(),
    assetId: String(assetId),
    market: record.market,
    source,
    bestBid: bid,
    bestAsk: ask,
    mid: (bid + ask) / 2,
    spread
  };
}

function extractQuoteObservations(records) {
  const out = [];
  for (const record of records) {
    if (record.eventType === "best_bid_ask") {
      const obs = quoteObservation({
        record,
        assetId: record.assetId || record.asset_id,
        bestBid: record.bestBid ?? record.best_bid,
        bestAsk: record.bestAsk ?? record.best_ask,
        source: "best_bid_ask"
      });
      if (obs) out.push(obs);
      continue;
    }

    if (record.eventType === "price_change" && Array.isArray(record.priceChanges)) {
      for (const change of record.priceChanges) {
        const obs = quoteObservation({
          record,
          assetId: change.asset_id || change.assetId,
          bestBid: change.best_bid ?? change.bestBid,
          bestAsk: change.best_ask ?? change.bestAsk,
          source: "price_change"
        });
        if (obs) out.push(obs);
      }
    }
  }

  out.sort((left, right) => left.tsMs - right.tsMs || left.assetId.localeCompare(right.assetId));
  return out;
}

function groupByAsset(observations) {
  const map = new Map();
  for (const obs of observations) {
    const list = map.get(obs.assetId);
    if (list) list.push(obs);
    else map.set(obs.assetId, [obs]);
  }
  return map;
}

function findFutureObservation(rows, startIndex, horizonMs) {
  const start = rows[startIndex];
  const target = start.tsMs + horizonMs;
  for (let i = startIndex + 1; i < rows.length; i += 1) {
    const row = rows[i];
    if (row.tsMs >= target) return row;
  }
  return null;
}

function average(values) {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function round(value, digits = 6) {
  if (value == null || !Number.isFinite(value)) return null;
  return Number(value.toFixed(digits));
}

function evaluateWindow(observationsByAsset, windowSec) {
  const horizonMs = windowSec * 1000;
  const samples = [];

  for (const rows of observationsByAsset.values()) {
    for (let i = 0; i < rows.length - 1; i += 1) {
      const start = rows[i];
      const future = findFutureObservation(rows, i, horizonMs);
      if (!future || future.tsMs <= start.tsMs) continue;
      const midChange = future.mid - start.mid;
      const spreadChange = future.spread - start.spread;
      samples.push({
        windowSec,
        assetId: start.assetId,
        market: start.market,
        startTs: start.ts,
        futureTs: future.ts,
        dtSec: (future.tsMs - start.tsMs) / 1000,
        startMid: start.mid,
        futureMid: future.mid,
        midChange,
        absMidChange: Math.abs(midChange),
        startSpread: start.spread,
        futureSpread: future.spread,
        spreadChange,
        quoteUnchanged: start.bestBid === future.bestBid && start.bestAsk === future.bestAsk,
        spreadStable: Math.abs(spreadChange) <= 0.001,
        midStable: Math.abs(midChange) <= 0.001
      });
    }
  }

  const midChanges = samples.map((sample) => sample.midChange);
  const absMidChanges = samples.map((sample) => sample.absMidChange);
  const spreadChanges = samples.map((sample) => sample.spreadChange);
  const quoteUnchangedCount = samples.filter((sample) => sample.quoteUnchanged).length;
  const spreadStableCount = samples.filter((sample) => sample.spreadStable).length;
  const midStableCount = samples.filter((sample) => sample.midStable).length;

  const summary = {
    windowSec,
    samples: samples.length,
    quoteUnchangedRate: samples.length ? round(quoteUnchangedCount / samples.length, 4) : null,
    spreadStableRate: samples.length ? round(spreadStableCount / samples.length, 4) : null,
    midStableRate: samples.length ? round(midStableCount / samples.length, 4) : null,
    meanMidChange: round(average(midChanges)),
    medianAbsMidChange: round(median(absMidChanges)),
    meanSpreadChange: round(average(spreadChanges)),
    medianSpreadChange: round(median(spreadChanges))
  };
  return { summary, samples };
}

function buildReport(args) {
  const observations = extractQuoteObservations(args.records);
  const byAsset = groupByAsset(observations);
  const activeAssets = Array.from(byAsset.entries())
    .map(([assetId, rows]) => ({
      assetId,
      observations: rows.length,
      firstTs: rows[0]?.ts,
      lastTs: rows[rows.length - 1]?.ts,
      firstMid: round(rows[0]?.mid),
      lastMid: round(rows[rows.length - 1]?.mid),
      firstSpread: round(rows[0]?.spread),
      lastSpread: round(rows[rows.length - 1]?.spread)
    }))
    .sort((left, right) => right.observations - left.observations);
  const eligible = new Map(
    Array.from(byAsset.entries()).filter(([, rows]) => rows.length >= args.minObservations)
  );
  const evaluatedWindows = args.windows.map((windowSec) => evaluateWindow(eligible, windowSec));
  const windows = evaluatedWindows.map((item) => item.summary);
  const sampleRows = evaluatedWindows.flatMap((item) => item.samples);
  const enoughData = windows.some((window) => window.samples >= 20);

  return {
    command: "polymarket-clob-persistence-lab",
    generatedAt: new Date().toISOString(),
    researchOnly: true,
    writesOrders: false,
    inputPath: args.input,
    outputPath: args.output,
    samplesOutputPath: args.samplesOutput,
    recordsRead: args.records.length,
    quoteObservations: observations.length,
    assetsObserved: byAsset.size,
    assetsEligible: eligible.size,
    minObservationsPerAsset: args.minObservations,
    windows,
    samplesWritten: sampleRows.length,
    sampleRows,
    activeAssets: activeAssets.slice(0, 50),
    decision: enoughData
      ? "research-data-ready-for-offline-feature-test"
      : "insufficient-samples-collect-more-clob-data",
    nextAction: enoughData
      ? "Join persistence features to resolved outcomes or next-event drift; keep execution disabled."
      : "Run the recorder longer during active market windows before evaluating edge."
  };
}

function buildMissingInputReport(opts) {
  return {
    command: "polymarket-clob-persistence-lab",
    generatedAt: new Date().toISOString(),
    researchOnly: true,
    writesOrders: false,
    touchesBroker: false,
    inputPath: opts.input,
    outputPath: opts.output,
    samplesOutputPath: opts.samplesOutput,
    recordsRead: 0,
    quoteObservations: 0,
    assetsObserved: 0,
    assetsEligible: 0,
    minObservationsPerAsset: opts.minObservations,
    windows: opts.windows.map((windowSec) => ({
      windowSec,
      samples: 0,
      quoteUnchangedRate: null,
      spreadStableRate: null,
      midStableRate: null,
      meanMidChange: null,
      medianAbsMidChange: null,
      meanSpreadChange: null,
      medianSpreadChange: null
    })),
    samplesWritten: 0,
    activeAssets: [],
    decision: "missing-capture-file-collect-forward-clob-data",
    blocker: "input-jsonl-missing",
    nextAction: "Run the read-only CLOB recorder during active market windows before evaluating persistence edge."
  };
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  let records = [];
  let missingInput = false;
  try {
    records = await readJsonl(opts.input);
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
      missingInput = true;
    } else {
      throw error;
    }
  }
  const report = missingInput ? buildMissingInputReport(opts) : buildReport({ ...opts, records });
  await fs.mkdir(path.dirname(opts.output), { recursive: true });
  await fs.mkdir(path.dirname(opts.samplesOutput), { recursive: true });
  const { sampleRows = [], ...reportWithoutSamples } = report;
  await fs.writeFile(opts.samplesOutput, sampleRows.map((row) => JSON.stringify(row)).join("\n") + (sampleRows.length ? "\n" : ""), "utf8");
  await fs.writeFile(opts.output, `${JSON.stringify(reportWithoutSamples, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(reportWithoutSamples, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
