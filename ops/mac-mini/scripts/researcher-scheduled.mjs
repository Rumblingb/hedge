import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const tsxPath = path.resolve(repoRoot, "node_modules/.bin/tsx");
const statePath = path.resolve(repoRoot, process.env.BILL_RESEARCHER_SCHEDULER_STATE_PATH ?? ".rumbling-hedge/state/researcher-scheduler.json");
const latestPath = path.resolve(repoRoot, process.env.BILL_RESEARCHER_SCHEDULER_LATEST_PATH ?? ".rumbling-hedge/state/researcher-scheduler.latest.json");
const targetsPath = path.resolve(process.env.RESEARCHER_TARGETS_PATH ?? path.join(process.env.OPENCLAW_HOME ?? path.join(process.env.HOME ?? "", ".openclaw"), "workspace-researcher", "targets.json"));

function parsePositiveInt(value, fallback) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

async function readJson(pathname, fallback) {
  try {
    return JSON.parse(await readFile(pathname, "utf8"));
  } catch {
    return fallback;
  }
}

function compareTargets(left, right) {
  const priorityDelta = (left.priority ?? 5) - (right.priority ?? 5);
  if (priorityDelta !== 0) return priorityDelta;
  return left.id.localeCompare(right.id);
}

function chooseBatch(targets, state) {
  const maxTargets = parsePositiveInt(process.env.BILL_RESEARCHER_MAX_TARGETS, 5);
  const fullEvery = parsePositiveInt(process.env.BILL_RESEARCHER_FULL_EVERY_NTH_RUN, 6);
  const youtubeEvery = parsePositiveInt(process.env.BILL_RESEARCHER_YOUTUBE_EVERY_NTH_RUN, 12);
  const nextRun = (state.runCount ?? 0) + 1;
  const fullRun = nextRun % fullEvery === 0;
  const includeYouTube = nextRun % youtubeEvery === 0;

  const enabledTargets = targets.filter((target) => target?.enabled !== false);
  const sorted = [...enabledTargets].sort(compareTargets);
  const youtubeTargets = sorted.filter((target) => target.kind === "youtube-transcript");
  const regularTargets = sorted.filter((target) => target.kind !== "youtube-transcript");
  const cursor = Number.isFinite(state.cursor) ? state.cursor : 0;
  const batch = [];

  for (let i = 0; i < regularTargets.length && batch.length < maxTargets; i += 1) {
    const target = regularTargets[(cursor + i) % regularTargets.length];
    batch.push(target);
  }

  if (includeYouTube && youtubeTargets.length > 0) {
    batch.push(youtubeTargets[0]);
  }

  return {
    nextRun,
    fullRun,
    includeYouTube,
    maxTargets,
    batch,
    nextCursor: regularTargets.length > 0 ? (cursor + maxTargets) % regularTargets.length : 0
  };
}

async function runResearcher(args) {
  const commandArgs = ["src/cli.ts", "researcher-run"];
  for (const target of args.batch) {
    commandArgs.push("--target", target.id);
  }
  if (!args.fullRun || `${process.env.BILL_RESEARCHER_SKIP_JUDGE_LIGHT ?? "true"}` === "true") {
    commandArgs.push("--skip-judge");
  }
  if (!args.fullRun || `${process.env.BILL_RESEARCHER_SKIP_EMBED_LIGHT ?? "true"}` === "true") {
    commandArgs.push("--skip-embed");
  }
  const { stdout } = await execFileAsync(process.execPath, [tsxPath, ...commandArgs], {
    cwd: repoRoot,
    env: process.env,
    maxBuffer: 1024 * 1024 * 16
  });
  return stdout.trim() ? JSON.parse(stdout) : {};
}

const startedAt = new Date().toISOString();

try {
  const [targetsDoc, previous] = await Promise.all([
    readJson(targetsPath, { targets: [] }),
    readJson(statePath, { runCount: 0, cursor: 0 })
  ]);
  const targets = Array.isArray(targetsDoc.targets) ? targetsDoc.targets : [];
  const batch = chooseBatch(targets, previous);
  if (batch.batch.length === 0) {
    throw new Error(`no enabled researcher targets available in ${targetsPath}`);
  }
  const report = await runResearcher(batch);

  const nextState = {
    runCount: batch.nextRun,
    cursor: batch.nextCursor,
    lastRunAt: startedAt,
    lastMode: batch.fullRun ? "full" : "light",
    lastTargets: batch.batch.map((target) => target.id),
    lastIncludeYouTube: batch.includeYouTube
  };

  const payload = {
    command: "bill-researcher-run-scheduled",
    startedAt,
    mode: batch.fullRun ? "full" : "light",
    targetCount: batch.batch.length,
    targets: batch.batch.map((target) => target.id),
    includeYouTube: batch.includeYouTube,
    skippedJudge: !batch.fullRun || `${process.env.BILL_RESEARCHER_SKIP_JUDGE_LIGHT ?? "true"}` === "true",
    skippedEmbed: !batch.fullRun || `${process.env.BILL_RESEARCHER_SKIP_EMBED_LIGHT ?? "true"}` === "true",
    report
  };

  await mkdir(path.dirname(statePath), { recursive: true });
  await mkdir(path.dirname(latestPath), { recursive: true });
  await Promise.all([
    writeFile(statePath, `${JSON.stringify(nextState, null, 2)}\n`, "utf8"),
    writeFile(latestPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8")
  ]);

  console.log(JSON.stringify(payload, null, 2));
} catch (error) {
  const payload = {
    command: "bill-researcher-run-scheduled",
    startedAt,
    status: "failed",
    error: error instanceof Error ? error.message : String(error)
  };
  await mkdir(path.dirname(latestPath), { recursive: true });
  await writeFile(latestPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(payload, null, 2));
  process.exitCode = 1;
}
