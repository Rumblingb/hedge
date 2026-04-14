import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const historyPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl");

function cyclePosture(counts) {
  if ((counts?.["paper-trade"] ?? 0) > 0) return "paper-trade-candidates";
  if ((counts?.watch ?? 0) > 0) return "watch-only";
  if ((counts?.reject ?? 0) > 0) return "reject-only";
  return "no-cross-venue-edge-yet";
}

async function runJsonCommand(relativePath) {
  const commandPath = path.resolve(repoRoot, relativePath);
  const { stdout } = await execFileAsync(commandPath, [], {
    cwd: repoRoot,
    env: process.env,
    maxBuffer: 1024 * 1024 * 8
  });
  const trimmed = stdout.trim();
  if (!trimmed) return {};
  return JSON.parse(trimmed);
}

async function writeHistory(entry) {
  await mkdir(path.dirname(historyPath), { recursive: true });
  await appendFile(historyPath, `${JSON.stringify(entry)}\n`, "utf8");
}

const startedAt = new Date().toISOString();

try {
  const collect = await runJsonCommand("ops/mac-mini/bin/bill-prediction-collect-scheduled");
  const scan = await runJsonCommand("ops/mac-mini/bin/bill-prediction-scan-scheduled");
  const report = await runJsonCommand("ops/mac-mini/bin/bill-prediction-report-scheduled");
  const counts = report.counts ?? scan.counts ?? { reject: 0, watch: 0, "paper-trade": 0 };
  const entry = {
    ts: startedAt,
    command: "prediction-cycle",
    historyPath,
    posture: cyclePosture(counts),
    collect: {
      source: collect.source ?? null,
      count: collect.count ?? 0,
      limit: collect.limit ?? null,
      outPath: collect.outPath ?? null,
      venueCounts: collect.venueCounts ?? {}
    },
    scan: {
      inputPath: scan.inputPath ?? null,
      journalPath: scan.journalPath ?? null,
      counts
    },
    report: {
      journalPath: report.journalPath ?? null,
      top10Count: Array.isArray(report.top10) ? report.top10.length : 0
    },
    topCandidate: Array.isArray(report.top10) && report.top10.length > 0
      ? {
          candidateId: report.top10[0].candidateId,
          verdict: report.top10[0].verdict,
          netEdgePct: report.top10[0].netEdgePct,
          matchScore: report.top10[0].matchScore,
          recommendedStake: report.top10[0].sizing?.recommendedStake ?? 0,
          stakeCurrency: report.top10[0].sizing?.bankrollCurrency ?? null
        }
      : null
  };
  await writeHistory(entry);
  console.log(JSON.stringify(entry, null, 2));
} catch (error) {
  const entry = {
    ts: startedAt,
    command: "prediction-cycle",
    historyPath,
    posture: "failed",
    error: error instanceof Error ? error.message : String(error)
  };
  await writeHistory(entry);
  console.error(JSON.stringify(entry, null, 2));
  process.exitCode = 1;
}
