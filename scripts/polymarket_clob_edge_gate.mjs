#!/usr/bin/env node
/**
 * Research-only Polymarket CLOB edge gate.
 *
 * Reads persistence sample JSONL and decides whether any simple top-of-book
 * persistence hypothesis is even worth paper-research. This is a hard no-trade
 * gate: it never routes orders and defaults to reject unless there are enough
 * observations and post-spread drift is positive by a meaningful buffer.
 */
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const TODAY = new Date().toISOString().slice(0, 10);
const DEFAULT_INPUT = path.resolve(REPO_ROOT, ".rumbling-hedge/prediction/clob", `${TODAY}-persistence-samples.jsonl`);
const DEFAULT_SNAPSHOT = path.resolve(REPO_ROOT, ".rumbling-hedge/runtime/prediction/latest-combined-snapshot.json");
const DEFAULT_OUTPUT = path.resolve(REPO_ROOT, ".rumbling-hedge/state/polymarket-clob-edge-gate.latest.json");

function parseArgs(argv) {
  const out = {
    input: process.env.BILL_POLYMARKET_CLOB_PERSISTENCE_SAMPLES || DEFAULT_INPUT,
    snapshot: process.env.BILL_POLYMARKET_SNAPSHOT_PATH || DEFAULT_SNAPSHOT,
    output: process.env.BILL_POLYMARKET_CLOB_EDGE_GATE_PATH || DEFAULT_OUTPUT,
    minSamples: Number.parseInt(process.env.BILL_POLYMARKET_CLOB_EDGE_MIN_SAMPLES || "30", 10),
    minNetDrift: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_EDGE_MIN_NET_DRIFT || "0.0025"),
    maxMedianSpread: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_EDGE_MAX_MEDIAN_SPREAD || "0.02"),
    minDirectionalHitRate: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_EDGE_MIN_HIT_RATE || "0.55")
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--input" && next) out.input = path.resolve(next), i += 1;
    else if (arg === "--snapshot" && next) out.snapshot = path.resolve(next), i += 1;
    else if (arg === "--output" && next) out.output = path.resolve(next), i += 1;
    else if (arg === "--min-samples" && next) out.minSamples = Number.parseInt(next, 10), i += 1;
    else if (arg === "--min-net-drift" && next) out.minNetDrift = Number.parseFloat(next), i += 1;
    else if (arg === "--max-median-spread" && next) out.maxMedianSpread = Number.parseFloat(next), i += 1;
    else if (arg === "--min-directional-hit-rate" && next) out.minDirectionalHitRate = Number.parseFloat(next), i += 1;
  }

  if (!Number.isFinite(out.minSamples) || out.minSamples <= 0) out.minSamples = 30;
  if (!Number.isFinite(out.minNetDrift) || out.minNetDrift < 0) out.minNetDrift = 0.0025;
  if (!Number.isFinite(out.maxMedianSpread) || out.maxMedianSpread <= 0) out.maxMedianSpread = 0.02;
  if (!Number.isFinite(out.minDirectionalHitRate) || out.minDirectionalHitRate < 0.5) out.minDirectionalHitRate = 0.55;
  return out;
}

async function readJsonl(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

async function loadSnapshotQuestions(snapshotPath) {
  try {
    const raw = await fs.readFile(snapshotPath, "utf8");
    const parsed = JSON.parse(raw);
    const rows = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.markets) ? parsed.markets : [];
    const out = new Map();
    for (const row of rows) {
      if (!row?.clobTokenId) continue;
      out.set(String(row.clobTokenId), {
        question: row.marketQuestion || row.eventTitle || "unknown",
        price: row.price,
        displayedSize: row.displayedSize,
        bestBid: row.bestBid,
        bestAsk: row.bestAsk
      });
    }
    return out;
  } catch {
    return new Map();
  }
}

function round(value, digits = 6) {
  if (value == null || !Number.isFinite(value)) return null;
  return Number(value.toFixed(digits));
}

function average(values) {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function groupKey(row) {
  return `${row.windowSec}:${row.assetId}`;
}

function scoreGroup(rows, meta, opts) {
  const midChanges = rows.map((row) => Number(row.midChange || 0));
  const spreads = rows.map((row) => Number(row.startSpread || 0)).filter((value) => Number.isFinite(value));
  const meanDrift = average(midChanges);
  const medianSpread = median(spreads);
  const longNetDrift = meanDrift - medianSpread;
  const shortNetDrift = -meanDrift - medianSpread;
  const direction = longNetDrift >= shortNetDrift ? "long-yes" : "short-yes";
  const netDrift = Math.max(longNetDrift, shortNetDrift);
  const directionalHits = midChanges.filter((value) => direction === "long-yes" ? value > 0 : value < 0).length;
  const directionalHitRate = rows.length ? directionalHits / rows.length : 0;
  const unchangedRate = rows.filter((row) => row.quoteUnchanged).length / Math.max(1, rows.length);
  const spreadStableRate = rows.filter((row) => row.spreadStable).length / Math.max(1, rows.length);

  const blockers = [];
  if (rows.length < opts.minSamples) blockers.push("too-few-samples");
  if (medianSpread > opts.maxMedianSpread) blockers.push("spread-too-wide");
  if (netDrift < opts.minNetDrift) blockers.push("net-drift-below-threshold");
  if (directionalHitRate < opts.minDirectionalHitRate) blockers.push("directional-hit-rate-too-low");

  return {
    assetId: rows[0]?.assetId,
    market: rows[0]?.market,
    question: meta?.question,
    windowSec: Number(rows[0]?.windowSec),
    samples: rows.length,
    direction,
    meanDrift: round(meanDrift),
    medianSpread: round(medianSpread),
    netDriftAfterSpread: round(netDrift),
    directionalHitRate: round(directionalHitRate, 4),
    quoteUnchangedRate: round(unchangedRate, 4),
    spreadStableRate: round(spreadStableRate, 4),
    displayedSize: meta?.displayedSize,
    snapshotPrice: meta?.price,
    verdict: blockers.length === 0 ? "watch-research" : "reject",
    blockers
  };
}

function summarize(rows, questionByAsset, opts) {
  const grouped = new Map();
  for (const row of rows) {
    const key = groupKey(row);
    const list = grouped.get(key);
    if (list) list.push(row);
    else grouped.set(key, [row]);
  }
  const scored = Array.from(grouped.values())
    .map((groupRows) => scoreGroup(groupRows, questionByAsset.get(String(groupRows[0]?.assetId)), opts))
    .sort((left, right) =>
      (right.verdict === "watch-research" ? 1 : 0) - (left.verdict === "watch-research" ? 1 : 0)
      || Number(right.netDriftAfterSpread || -Infinity) - Number(left.netDriftAfterSpread || -Infinity)
      || right.samples - left.samples
    );
  const watch = scored.filter((row) => row.verdict === "watch-research");
  const blockerCounts = {};
  for (const row of scored) {
    for (const blocker of row.blockers) {
      blockerCounts[blocker] = (blockerCounts[blocker] || 0) + 1;
    }
  }

  return {
    scoredGroups: scored.length,
    watchResearchGroups: watch.length,
    blockerCounts,
    topGroups: scored.slice(0, 25)
  };
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const [rows, questionByAsset] = await Promise.all([
    readJsonl(opts.input),
    loadSnapshotQuestions(opts.snapshot)
  ]);
  const summary = summarize(rows, questionByAsset, opts);
  const status = summary.watchResearchGroups > 0 ? "WATCH_RESEARCH_ONLY" : "REJECT_NO_EDGE";
  const report = {
    command: "polymarket-clob-edge-gate",
    generatedAt: new Date().toISOString(),
    status,
    researchOnly: true,
    writesOrders: false,
    readyForPaper: false,
    inputPath: opts.input,
    snapshotPath: opts.snapshot,
    outputPath: opts.output,
    thresholds: {
      minSamples: opts.minSamples,
      minNetDrift: opts.minNetDrift,
      maxMedianSpread: opts.maxMedianSpread,
      minDirectionalHitRate: opts.minDirectionalHitRate
    },
    rowsRead: rows.length,
    ...summary,
    decision: status === "WATCH_RESEARCH_ONLY"
      ? "Candidates may be studied offline, but no paper/live execution is approved."
      : "No CLOB persistence edge candidate cleared the post-spread research gate.",
    nextAction: "Collect longer windows and join with resolved outcomes before promotion."
  };
  await fs.mkdir(path.dirname(opts.output), { recursive: true });
  await fs.writeFile(opts.output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
