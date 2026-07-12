#!/usr/bin/env node
import { accessSync, constants, existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join, parse, resolve } from "node:path";

const repoRoot = resolve(new URL("..", import.meta.url).pathname);
const defaultTarget = "/Volumes/Seagate Expansion Drive/BillColdStorage/hedge";
const args = new Set(process.argv.slice(2));
const targetArgIndex = process.argv.indexOf("--target");
const targetRoot = resolve(targetArgIndex >= 0 ? process.argv[targetArgIndex + 1] : process.env.BILL_COLD_STORAGE_ROOT ?? defaultTarget);
const execute = args.has("--execute");
const latestJsonPath = resolve(repoRoot, ".rumbling-hedge/state/storage-tier-plan.latest.json");
const latestMarkdownPath = resolve(repoRoot, ".rumbling-hedge/state/storage-tier-plan.latest.md");

function bytesToHuman(bytes) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${Number(value.toFixed(unit === 0 ? 0 : 2))}${units[unit]}`;
}

function pathSizeBytes(pathname) {
  if (!existsSync(pathname)) return 0;
  const stats = statSync(pathname);
  if (stats.isFile()) return stats.size;
  let total = 0;
  for (const entry of readdirSync(pathname, { withFileTypes: true })) {
    total += pathSizeBytes(join(pathname, entry.name));
  }
  return total;
}

function isWritableDirectory(pathname) {
  try {
    mkdirSync(pathname, { recursive: true });
    accessSync(pathname, constants.W_OK);
    return true;
  } catch {
    return false;
  }
}

function mountInfoFor(pathname) {
  try {
    const output = execFileSync("df", ["-h", existingAncestor(pathname)], { encoding: "utf8" }).trim().split("\n");
    return output.at(-1) ?? null;
  } catch {
    return null;
  }
}

function existingAncestor(pathname) {
  let current = resolve(pathname);
  const root = parse(current).root;
  while (!existsSync(current) && current !== root) {
    current = dirname(current);
  }
  return existsSync(current) ? current : root;
}

function candidate(relativePath, tier, action, reason) {
  const absolutePath = resolve(repoRoot, relativePath);
  const bytes = pathSizeBytes(absolutePath);
  return {
    relativePath,
    absolutePath,
    exists: existsSync(absolutePath),
    bytes,
    size: bytesToHuman(bytes),
    tier,
    action,
    reason
  };
}

const coldCandidates = [
  candidate(
    ".rumbling-hedge/external/prediction-market-analysis",
    "cold-hdd",
    "move-to-hdd-and-point-BILL_PREDICTION_MARKET_ANALYSIS_DATA_ROOT-or-symlink",
    "Historical parquet research corpus; not on the scheduled hot paper/prediction path."
  ),
  candidate(
    "data/kaggle_fallback",
    "cold-hdd",
    "move-to-hdd-and-restore-only-for-manual-research",
    "Static fallback BTC dataset; not required by current launchd defaults."
  ),
  candidate(
    "data/real_yahoo",
    "cold-hdd",
    "move-to-hdd-and-restore-only-for-manual-research",
    "Older fetched market bars; current launchd uses data/free normalized files."
  )
].filter((item) => item.exists && item.bytes > 0);

const warmCandidates = [
  candidate(
    "data/free/ALL-6MARKETS-1m-90d.csv",
    "warm-ssd-or-hdd-copy",
    "keep-on-ssd-until-OOS-dataset-policy-is-final",
    "Useful for extending OOS evidence; keep local until Bill has enough rolling windows."
  ),
  candidate(
    "data/free/ALL-6MARKETS-1m-90d-normalized.csv",
    "warm-ssd-or-hdd-copy",
    "keep-on-ssd-until-OOS-dataset-policy-is-final",
    "Useful for extending OOS evidence; keep local until Bill has enough rolling windows."
  ),
  candidate(
    ".rumbling-hedge/logs",
    "warm-ssd-rotated-archive",
    "archive-rotated-logs-only",
    "Current logs are hot; rotated logs can be copied off once the HDD is writable."
  )
].filter((item) => item.exists && item.bytes > 0);

const hotKeep = [
  "data/free/ALL-6MARKETS-1m-10d-normalized.csv",
  "data/free/ALL-6MARKETS-1m-30d-normalized.csv",
  ".rumbling-hedge/runtime",
  ".rumbling-hedge/state",
  ".rumbling-hedge/research/corpus",
  "node_modules"
].map((relativePath) => candidate(
  relativePath,
  "hot-ssd",
  "keep-on-ssd",
  "Used by scheduled prediction, futures, strategy-lab, researcher, or local dev loops."
)).filter((item) => item.exists && item.bytes > 0);

const writable = isWritableDirectory(targetRoot);
const plan = {
  command: "bill-storage-tier",
  generatedAt: new Date().toISOString(),
  repoRoot,
  targetRoot,
  targetWritable: writable,
  targetMount: mountInfoFor(targetRoot),
  executeRequested: execute,
  executeAllowed: execute && writable,
  totalColdBytes: coldCandidates.reduce((sum, item) => sum + item.bytes, 0),
  totalColdSize: bytesToHuman(coldCandidates.reduce((sum, item) => sum + item.bytes, 0)),
  totalWarmBytes: warmCandidates.reduce((sum, item) => sum + item.bytes, 0),
  totalWarmSize: bytesToHuman(warmCandidates.reduce((sum, item) => sum + item.bytes, 0)),
  coldCandidates,
  warmCandidates,
  hotKeep,
  nextActions: writable
    ? [
        `rsync -a --info=progress2 ${join(repoRoot, ".rumbling-hedge/external/prediction-market-analysis")}/ ${join(targetRoot, ".rumbling-hedge/external/prediction-market-analysis")}/`,
        "After copy verification, stop Bill launchd jobs, replace the SSD directory with a symlink or set BILL_PREDICTION_MARKET_ANALYSIS_DATA_ROOT to the HDD path, then restart jobs.",
        "Only remove SSD originals after a fresh bill-health and prediction-market-analysis-status pass."
      ]
    : [
        "Make the HDD writable first. It is currently not safe to migrate because macOS mounted it read-only.",
        "Use exFAT/APFS or install a trusted NTFS write driver, then rerun this script.",
        "Do not move hot runtime/state/data/free files to the HDD."
      ]
};

mkdirSync(dirname(latestJsonPath), { recursive: true });
writeFileSync(latestJsonPath, `${JSON.stringify(plan, null, 2)}\n`);
writeFileSync(
  latestMarkdownPath,
  [
    "# Bill Storage Tier Plan",
    "",
    `- Generated: ${plan.generatedAt}`,
    `- Target: ${plan.targetRoot}`,
    `- Target writable: ${plan.targetWritable}`,
    `- Cold move candidates: ${plan.totalColdSize}`,
    `- Warm/archive candidates: ${plan.totalWarmSize}`,
    "",
    "## Cold Candidates",
    ...plan.coldCandidates.map((item) => `- ${item.size} ${item.relativePath} — ${item.reason}`),
    "",
    "## Keep Hot On SSD",
    ...plan.hotKeep.map((item) => `- ${item.size} ${item.relativePath} — ${item.reason}`),
    "",
    "## Next Actions",
    ...plan.nextActions.map((item) => `- ${item}`)
  ].join("\n"),
  "utf8"
);

if (execute && !writable) {
  console.error(`Target is not writable: ${targetRoot}`);
  process.exitCode = 2;
}

console.log(JSON.stringify(plan, null, 2));
