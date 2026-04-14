import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const historyPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl");
const latestReviewPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
const workspaceDir = process.env.BILL_WORKSPACE_DIR ?? "/Users/baskar_viji/.openclaw/workspace-bill";
const outboxPath = path.join(workspaceDir, "OUTBOX.md");
const inboxPath = path.join(workspaceDir, "INBOX.md");
const lastCyclePath = path.resolve(repoRoot, ".rumbling-hedge/state/prediction-cycle.last.json");
const ESCALATION_THRESHOLD = Number.parseInt(process.env.BILL_PREDICTION_ESCALATION_THRESHOLD ?? "3", 10);

async function readLastCycle() {
  try {
    const raw = await readFile(lastCyclePath, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function writeLastCycle(state) {
  await mkdir(path.dirname(lastCyclePath), { recursive: true });
  await writeFile(lastCyclePath, `${JSON.stringify(state, null, 2)}\n`, "utf8");
}

function shouldWriteOutbox(previous, entry) {
  if (!previous) return true;
  if (previous.posture !== entry.posture) return true;
  if ((previous.venuesHealthy ?? 0) !== entry.venuesHealthy) return true;
  if ((previous.topCandidateId ?? null) !== (entry.topCandidate?.candidateId ?? null)) return true;
  if (Number(previous.trainingObjectiveScore ?? 0) !== Number(entry.training?.selectedEvaluation?.objectiveScore ?? 0)) return true;
  return false;
}

async function appendOutbox(entry) {
  const venueLine = Object.entries(entry.collect.venueCounts ?? {})
    .map(([venue, count]) => `${venue}=${count}`)
    .join(" ") || "(none)";
  const candLine = entry.topCandidate
    ? `${entry.topCandidate.candidateId} verdict=${entry.topCandidate.verdict} edge=${entry.topCandidate.netEdgePct}%`
    : "(no candidate)";
  const exec = entry.execute ?? {};
  const execLine = exec.status === "skipped"
    ? `(skipped: ${exec.mode ?? "n/a"})`
    : `mode=${exec.mode ?? "n/a"} placed=${exec.placedCount ?? 0} skipped=${exec.skippedCount ?? 0} stake=${exec.totalStake ?? 0}${exec.stakeCurrency ? " " + exec.stakeCurrency : ""}`;
  const train = entry.training ?? {};
  const trainLine = train.selectedEvaluation
    ? `objective=${train.selectedEvaluation.objectiveScore} paper=${train.selectedEvaluation.paperCount} watch=${train.selectedEvaluation.watchCount} minMatch=${train.selectedPolicy?.minMatchScore ?? "n/a"} paperMatch=${train.selectedPolicy?.paperMatchScore ?? "n/a"} paperEdge=${train.selectedPolicy?.paperEdgeThresholdPct ?? "n/a"}`
    : "(training skipped)";
  const body = [
    ``,
    `## ${entry.ts}`,
    `- posture: ${entry.posture}`,
    `- venues: ${venueLine}`,
    `- counts: reject=${entry.scan.counts.reject ?? 0} watch=${entry.scan.counts.watch ?? 0} paper=${entry.scan.counts["paper-trade"] ?? 0}`,
    `- top candidate: ${candLine}`,
    `- execute: ${execLine}`,
    `- train: ${trainLine}`,
    ``
  ].join("\n");
  await appendFile(outboxPath, body, "utf8");
}

async function appendInboxEscalation(reason, streak) {
  const body = [
    ``,
    `## ${new Date().toISOString()} — system-escalation`,
    `- reason: ${reason}`,
    `- streak: ${streak} consecutive cycles`,
    `- action: founder input needed; Bill will keep cycling but is not making progress.`,
    ``
  ].join("\n");
  await appendFile(inboxPath, body, "utf8");
}

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

async function runCliJson(args) {
  const nodePath = process.execPath;
  const tsxPath = path.resolve(repoRoot, "node_modules/.bin/tsx");
  const { stdout } = await execFileAsync(nodePath, [tsxPath, "src/cli.ts", ...args], {
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

async function writeLatestReview(review) {
  await mkdir(path.dirname(latestReviewPath), { recursive: true });
  await writeFile(latestReviewPath, `${JSON.stringify(review, null, 2)}\n`, "utf8");
}

const startedAt = new Date().toISOString();

try {
  const collect = await runJsonCommand("ops/mac-mini/bin/bill-prediction-collect-scheduled");
  const scan = await runJsonCommand("ops/mac-mini/bin/bill-prediction-scan-scheduled");
  const report = await runJsonCommand("ops/mac-mini/bin/bill-prediction-report-scheduled");
  const execute = await runJsonCommand("ops/mac-mini/bin/bill-prediction-execute-scheduled");
  const review = await runCliJson(["prediction-review"]);
  const promotion = await runCliJson(["promotion-review"]);
  const training = process.env.BILL_ENABLE_PREDICTION_TRAINING === "false" ? null : await runCliJson(["prediction-train"]);
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
    execute: {
      status: execute.status ?? null,
      mode: execute.mode ?? null,
      placedCount: execute.placedCount ?? 0,
      skippedCount: execute.skippedCount ?? 0,
      totalStake: execute.totalStake ?? 0,
      stakeCurrency: execute.stakeCurrency ?? null,
      liveGate: execute.liveGate ?? null,
      fillsJournalPath: execute.fillsJournalPath ?? null
    },
    review: review.review ?? null,
    promotion: promotion.state ?? null,
    training,
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
  const venuesHealthy = Object.values(entry.collect.venueCounts ?? {}).filter((n) => Number(n) > 0).length;
  entry.venuesHealthy = venuesHealthy;

  const previous = await readLastCycle();

  if (shouldWriteOutbox(previous, { ...entry, topCandidate: entry.topCandidate })) {
    try {
      await appendOutbox(entry);
    } catch (err) {
      console.error(`[prediction-cycle] failed to append outbox: ${err?.message ?? err}`);
    }
  }

  const previousStreak = previous?.noProgressStreak ?? 0;
  const noProgress = entry.posture === "no-cross-venue-edge-yet" || venuesHealthy < 2;
  const nextStreak = noProgress ? previousStreak + 1 : 0;

  const alreadyEscalated = previous?.escalatedAt && previous.escalatedStreak >= ESCALATION_THRESHOLD;
  let escalatedAt = previous?.escalatedAt ?? null;
  let escalatedStreak = previous?.escalatedStreak ?? 0;
  if (nextStreak === ESCALATION_THRESHOLD && !alreadyEscalated) {
    try {
      await appendInboxEscalation(
        venuesHealthy < 2
          ? `only ${venuesHealthy} healthy venue(s): ${JSON.stringify(entry.collect.venueCounts)}`
          : `posture stuck at no-cross-venue-edge-yet for ${nextStreak} cycles`,
        nextStreak
      );
      escalatedAt = new Date().toISOString();
      escalatedStreak = nextStreak;
    } catch (err) {
      console.error(`[prediction-cycle] failed to append inbox escalation: ${err?.message ?? err}`);
    }
  }
  if (!noProgress) {
    escalatedAt = null;
    escalatedStreak = 0;
  }

  await writeLastCycle({
    ts: entry.ts,
    posture: entry.posture,
    venuesHealthy,
    topCandidateId: entry.topCandidate?.candidateId ?? null,
    trainingObjectiveScore: entry.training?.selectedEvaluation?.objectiveScore ?? 0,
    noProgressStreak: nextStreak,
    escalatedAt,
    escalatedStreak
  });

  await writeLatestReview({ review: review.review ?? null, promotion: promotion.state ?? null });
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
  try {
    await appendFile(
      outboxPath,
      `\n## ${startedAt}\n- posture: failed\n- error: ${entry.error}\n`,
      "utf8"
    );
  } catch {}
  console.error(JSON.stringify(entry, null, 2));
  process.exitCode = 1;
}
