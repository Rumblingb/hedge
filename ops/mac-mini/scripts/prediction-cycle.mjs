import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const historyPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl");
const latestPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_CYCLE_LATEST_PATH ?? ".rumbling-hedge/state/prediction-cycle.latest.json");
const latestReviewPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
const workspaceDir = process.env.BILL_WORKSPACE_DIR ?? path.join(os.homedir(), ".openclaw/workspace-bill");
const outboxPath = path.join(workspaceDir, "OUTBOX.md");
const inboxPath = path.join(workspaceDir, "INBOX.md");
const lastCyclePath = path.resolve(repoRoot, ".rumbling-hedge/state/prediction-cycle.last.json");
const ESCALATION_THRESHOLD = Number.parseInt(process.env.BILL_PREDICTION_ESCALATION_THRESHOLD ?? "3", 10);
const CHILD_TIMEOUT_MS = parsePositiveIntEnv("BILL_PREDICTION_CYCLE_CHILD_TIMEOUT_MS", 180_000);

function parsePositiveIntEnv(name, fallback) {
  const raw = Number.parseInt(process.env[name] ?? "", 10);
  return Number.isFinite(raw) && raw > 0 ? raw : fallback;
}

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
  if ((previous.copyTopIdeaId ?? null) !== (entry.copyDemo?.topActionableIdea?.id ?? null)) return true;
  if (Number(previous.copyShadowIdeas ?? 0) !== Number(entry.copyDemo?.actionableIdeaCount ?? 0)) return true;
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
  const copyDemo = entry.copyDemo ?? {};
  const copyLine = copyDemo.enabled === false
    ? "(disabled)"
    : `status=${copyDemo.status ?? "unknown"} leaders=${copyDemo.selectedLeaders ?? 0} ideas=${copyDemo.ideaCount ?? 0} shadow=${copyDemo.shadowIdeaCount ?? 0} actionable=${copyDemo.topIdea?.slug ?? "(none)"} watch=${copyDemo.topWatchIdea?.slug ?? "(none)"}`;
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
    `- copy demo: ${copyLine}`,
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

async function appendInboxRecovery(entry) {
  const counts = entry.scan?.counts ?? {};
  const body = [
    ``,
    `## ${new Date().toISOString()} — system-recovery`,
    `- reason: prediction cycle recovered to ${entry.posture} with ${entry.venuesHealthy ?? 0} healthy venue(s)`,
    `- counts: reject=${counts.reject ?? 0} watch=${counts.watch ?? 0} paper=${counts["paper-trade"] ?? 0}`,
    `- action: prior Bill escalation can be treated as resolved unless a newer cycle reopens it.`,
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

export function evaluateCopyDemoStatus(report) {
  const ideas = Array.isArray(report?.ideas) ? report.ideas : [];
  const actionableIdeas = ideas.filter((idea) => idea.action === "shadow-buy");
  const status = actionableIdeas.length > 0
    ? "actionable"
    : ideas.length > 0
      ? "watch-only"
      : "idle";
  return {
    status,
    actionableIdeaCount: actionableIdeas.length,
    totalIdeas: ideas.length,
    topActionableIdea: actionableIdeas[0] ?? null,
    topWatchIdea: ideas.length > 0 ? ideas[0] : null
  };
}

function summarizeTopCandidate(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const candidate = rows.find((row) => row?.verdict === "paper-trade")
    ?? rows.find((row) => row?.verdict === "watch")
    ?? rows[0];
  if (!candidate) return null;
  return {
    candidateId: candidate.candidateId,
    verdict: candidate.verdict,
    netEdgePct: candidate.netEdgePct,
    matchScore: candidate.matchScore,
    recommendedStake: candidate.sizing?.recommendedStake ?? 0,
    stakeCurrency: candidate.sizing?.bankrollCurrency ?? null
  };
}

function shouldRunPredictionExecute(review, promotion) {
  return review?.review?.readyForPaper === true && promotion?.state?.recommendedStage === "paper";
}

function buildSkippedExecute(reason, report) {
  const eligible = Array.isArray(report?.top10)
    ? report.top10.filter((row) => row?.verdict === "paper-trade")
    : [];
  const eligibleCount = eligible.length;
  return {
    command: "prediction-execute",
    status: "skipped",
    mode: process.env.BILL_PREDICTION_EXECUTION_MODE ?? "paper",
    reason,
    eligibleCount,
    placedCount: 0,
    skippedCount: eligibleCount,
    totalStake: 0,
    totalMaxLoss: 0,
    stakeCurrency: process.env.BILL_PREDICTION_BANKROLL_CURRENCY ?? null,
    fillsJournalPath: process.env.BILL_PREDICTION_FILLS_JOURNAL_PATH ?? null,
    liveGate: null,
    placed: [],
    skipped: eligible.map((row, index) => ({
      candidateId: row?.candidateId ?? `eligible-${index + 1}`,
      reason
    }))
  };
}

async function runJsonCommand(relativePath) {
  const commandPath = path.resolve(repoRoot, relativePath);
  const { stdout } = await execFileAsync(commandPath, [], {
    cwd: repoRoot,
    env: process.env,
    maxBuffer: 1024 * 1024 * 8,
    timeout: CHILD_TIMEOUT_MS,
    killSignal: "SIGTERM"
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
    maxBuffer: 1024 * 1024 * 8,
    timeout: CHILD_TIMEOUT_MS,
    killSignal: "SIGTERM"
  });
  const trimmed = stdout.trim();
  if (!trimmed) return {};
  return JSON.parse(trimmed);
}

async function runOptionalStep(label, fn, fallback) {
  try {
    return await fn();
  } catch (error) {
    return {
      ...fallback,
      status: "degraded",
      error: error instanceof Error ? error.message : String(error),
      blockers: [
        ...(Array.isArray(fallback?.blockers) ? fallback.blockers : []),
        `${label}-failed`
      ]
    };
  }
}

async function writeHistory(entry) {
  await mkdir(path.dirname(historyPath), { recursive: true });
  await appendFile(historyPath, `${JSON.stringify(entry)}\n`, "utf8");
}

async function writeLatestCycle(entry) {
  await mkdir(path.dirname(latestPath), { recursive: true });
  await writeFile(latestPath, `${JSON.stringify(entry, null, 2)}\n`, "utf8");
}

async function writeLatestReview(review) {
  await mkdir(path.dirname(latestReviewPath), { recursive: true });
  await writeFile(latestReviewPath, `${JSON.stringify(review, null, 2)}\n`, "utf8");
}

function shouldRunCopyDemo(previous) {
  if (process.env.BILL_ENABLE_PREDICTION_COPY_DEMO === "false") {
    return false;
  }
  const everyNthRun = parsePositiveIntEnv("BILL_PREDICTION_COPY_DEMO_EVERY_NTH_RUN", 12);
  if (everyNthRun <= 1 || !previous) {
    return true;
  }
  const previousCycleCount = Number(previous.cycleCount ?? 0);
  return (previousCycleCount + 1) % everyNthRun === 0;
}

const startedAt = new Date().toISOString();

try {
  const previous = await readLastCycle();
  const collect = await runJsonCommand("ops/mac-mini/bin/bill-prediction-collect-scheduled");
  const scan = await runJsonCommand("ops/mac-mini/bin/bill-prediction-scan-scheduled");
  const report = await runJsonCommand("ops/mac-mini/bin/bill-prediction-report-scheduled");
  const review = await runCliJson(["prediction-review"]);
  const promotion = await runCliJson(["promotion-review"]);
  const execute = shouldRunPredictionExecute(review, promotion)
    ? await runJsonCommand("ops/mac-mini/bin/bill-prediction-execute-scheduled")
    : buildSkippedExecute("promotion review is not ready for paper execution", report);
  const copyDemo = shouldRunCopyDemo(previous) === false
    ? null
    : await runOptionalStep("prediction-copy-demo", () => runCliJson(["prediction-copy-demo"]), {
        command: "prediction-copy-demo",
        reportPath: null,
        report: null,
        blockers: []
      });
  const training = process.env.BILL_ENABLE_PREDICTION_TRAINING === "false"
    ? null
    : await runOptionalStep("prediction-train", () => runCliJson(["prediction-train"]), {
        command: "prediction-train",
        selectedEvaluation: null,
        selectedPolicy: null,
        blockers: []
      });
  const counts = report.counts ?? scan.counts ?? { reject: 0, watch: 0, "paper-trade": 0 };
  const copyDemoSummary = evaluateCopyDemoStatus(copyDemo?.report ?? null);
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
      reason: execute.reason ?? null,
      placedCount: execute.placedCount ?? 0,
      skippedCount: execute.skippedCount ?? 0,
      totalStake: execute.totalStake ?? 0,
      stakeCurrency: execute.stakeCurrency ?? null,
      liveGate: execute.liveGate ?? null,
      fillsJournalPath: execute.fillsJournalPath ?? null
    },
    copyDemo: copyDemo
      ? {
          enabled: true,
          status: copyDemoSummary.status,
          reportPath: copyDemo.reportPath ?? null,
          selectedLeaders: copyDemo.report?.cohort?.selectedLeaders ?? 0,
          selectedWallets: copyDemo.report?.cohort?.selectedWallets ?? [],
          ideaCount: copyDemoSummary.totalIdeas,
          actionableIdeaCount: copyDemoSummary.actionableIdeaCount,
          shadowIdeaCount: copyDemoSummary.actionableIdeaCount,
          blockers: [...(copyDemo.report?.blockers ?? []), ...(copyDemo.blockers ?? [])],
          topActionableIdea: copyDemoSummary.topActionableIdea
            ? {
                id: copyDemoSummary.topActionableIdea.id,
                slug: copyDemoSummary.topActionableIdea.slug,
                outcome: copyDemoSummary.topActionableIdea.outcome,
                action: copyDemoSummary.topActionableIdea.action,
                supporterCount: copyDemoSummary.topActionableIdea.supporterCount
              }
            : null,
          topWatchIdea: copyDemoSummary.topWatchIdea
            ? {
                id: copyDemoSummary.topWatchIdea.id,
                slug: copyDemoSummary.topWatchIdea.slug,
                outcome: copyDemoSummary.topWatchIdea.outcome,
                action: copyDemoSummary.topWatchIdea.action,
                supporterCount: copyDemoSummary.topWatchIdea.supporterCount
              }
            : null
        }
      : {
          enabled: false,
          status: "disabled",
          reportPath: null,
          selectedLeaders: 0,
          selectedWallets: [],
          ideaCount: 0,
          actionableIdeaCount: 0,
          shadowIdeaCount: 0,
          blockers: ["copy-demo-disabled"],
          topActionableIdea: null,
          topWatchIdea: null
        },
    review: review.review ?? null,
    promotion: promotion.state ?? null,
    training,
    topCandidate: summarizeTopCandidate(report.top10)
  };
  const venuesHealthy = Object.values(entry.collect.venueCounts ?? {}).filter((n) => Number(n) > 0).length;
  entry.venuesHealthy = venuesHealthy;

  if (shouldWriteOutbox(previous, { ...entry, topCandidate: entry.topCandidate })) {
    try {
      await appendOutbox(entry);
    } catch (err) {
      console.error(`[prediction-cycle] failed to append outbox: ${err?.message ?? err}`);
    }
  }

  const previousStreak = previous?.noProgressStreak ?? 0;
  const noProgress = (entry.posture === "no-cross-venue-edge-yet" || venuesHealthy < 2)
    && Number(entry.copyDemo?.shadowIdeaCount ?? 0) === 0;
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
    if (previous?.escalatedAt) {
      try {
        await appendInboxRecovery(entry);
      } catch (err) {
        console.error(`[prediction-cycle] failed to append inbox recovery: ${err?.message ?? err}`);
      }
    }
    escalatedAt = null;
    escalatedStreak = 0;
  }

  await writeLastCycle({
    ts: entry.ts,
    posture: entry.posture,
    venuesHealthy,
    topCandidateId: entry.topCandidate?.candidateId ?? null,
    copyTopIdeaId: entry.copyDemo?.topActionableIdea?.id ?? null,
    copyShadowIdeas: entry.copyDemo?.shadowIdeaCount ?? 0,
    trainingObjectiveScore: entry.training?.selectedEvaluation?.objectiveScore ?? 0,
    cycleCount: Number(previous?.cycleCount ?? 0) + 1,
    noProgressStreak: nextStreak,
    escalatedAt,
    escalatedStreak
  });

  await writeLatestReview({ review: review.review ?? null, promotion: promotion.state ?? null });
  await writeLatestCycle(entry);
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
  await writeLatestCycle(entry);
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
