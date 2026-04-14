import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const workspaceMemoryDir = process.env.BILL_WORKSPACE_MEMORY_DIR ?? "/Users/baskar_viji/.openclaw/workspace-bill/memory";
const predictionJournalPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_JOURNAL_PATH ?? "journals/prediction-opportunities.jsonl");
const predictionSnapshotPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_COLLECT_OUTPUT_PATH ?? "data/prediction/polymarket-live-snapshot.json");
const timezone = process.env.BILL_TIMEZONE ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
const today = new Intl.DateTimeFormat("en-CA", {
  timeZone: timezone,
  year: "numeric",
  month: "2-digit",
  day: "2-digit"
}).format(new Date());
const outPath = path.join(workspaceMemoryDir, `native-prediction-loop-${today}.md`);

async function readJsonLines(filePath) {
  if (!existsSync(filePath)) return [];
  const raw = await readFile(filePath, "utf8");
  return raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => JSON.parse(line));
}

async function readSnapshotCount(filePath) {
  if (!existsSync(filePath)) return 0;
  const raw = await readFile(filePath, "utf8");
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.length : 0;
  } catch {
    return 0;
  }
}

const rows = await readJsonLines(predictionJournalPath);
const snapshotCount = await readSnapshotCount(predictionSnapshotPath);
const counts = { reject: 0, watch: 0, "paper-trade": 0 };
for (const row of rows) counts[row.verdict] = (counts[row.verdict] ?? 0) + 1;
const posture = counts["paper-trade"] > 0
  ? "paper-trade-candidates"
  : counts.watch > 0
    ? "watch-only"
    : "no-cross-venue-edge-yet";
const now = new Date().toISOString();
const block = [
  `## ${now}`,
  `- host: ${os.hostname()}`,
  `- timezone: ${timezone}`,
  `- posture: ${posture}`,
  `- snapshot_path: ${predictionSnapshotPath}`,
  `- snapshot_count: ${snapshotCount}`,
  `- journal_path: ${predictionJournalPath}`,
  `- counts: reject=${counts.reject}, watch=${counts.watch}, paper-trade=${counts["paper-trade"]}`,
  `- note: native Bill prediction cycle completed through collector, scan, and report.`
].join("\n");

await mkdir(workspaceMemoryDir, { recursive: true });
const prefix = existsSync(outPath) ? "\n\n" : `# Native Prediction Loop ${today}\n\n`;
await writeFile(outPath, `${prefix}${block}`, { encoding: "utf8", flag: existsSync(outPath) ? "a" : "w" });
console.log(JSON.stringify({ command: "bill-native-summary", outPath, posture, counts, snapshotCount }, null, 2));
