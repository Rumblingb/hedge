import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const tsxPath = path.resolve(repoRoot, "node_modules/.bin/tsx");
const statePath = path.resolve(repoRoot, process.env.BILL_RESEARCHER_SCHEDULER_STATE_PATH ?? ".rumbling-hedge/state/researcher-scheduler.json");
const latestPath = path.resolve(repoRoot, process.env.BILL_RESEARCHER_SCHEDULER_LATEST_PATH ?? ".rumbling-hedge/state/researcher-scheduler.latest.json");
const workspaceTargetsPath = path.resolve(path.join(process.env.OPENCLAW_HOME ?? path.join(process.env.HOME ?? "", ".openclaw"), "workspace-researcher", "targets.json"));
const canonicalTargetsPath = path.resolve(repoRoot, "config/researcher-targets.bill.json");
const workspacePolicyPath = path.resolve(path.join(process.env.OPENCLAW_HOME ?? path.join(process.env.HOME ?? "", ".openclaw"), "workspace-researcher", "policy.json"));
const canonicalPolicyPath = path.resolve(repoRoot, "config/researcher-policy.bill.json");
const targetsPath = path.resolve(process.env.RESEARCHER_TARGETS_PATH ?? workspaceTargetsPath);

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

async function loadTargetsDoc() {
  if (process.env.RESEARCHER_TARGETS_PATH) {
    return {
      path: targetsPath,
      doc: await readJson(targetsPath, { targets: [] })
    };
  }

  const workspaceDoc = await readJson(workspaceTargetsPath, null);
  const workspaceTargets = Array.isArray(workspaceDoc?.targets) ? workspaceDoc.targets : [];
  if (workspaceTargets.some((target) => target?.enabled !== false)) {
    return { path: workspaceTargetsPath, doc: workspaceDoc };
  }

  return {
    path: canonicalTargetsPath,
    doc: await readJson(canonicalTargetsPath, { targets: [] })
  };
}

async function resolveResearcherPolicyPath() {
  if (process.env.RESEARCHER_POLICY_PATH) return path.resolve(process.env.RESEARCHER_POLICY_PATH);
  try {
    await readFile(workspacePolicyPath, "utf8");
    return workspacePolicyPath;
  } catch {
    return canonicalPolicyPath;
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
  const youtubeEvery = parsePositiveInt(process.env.BILL_RESEARCHER_YOUTUBE_EVERY_NTH_RUN, 3);
  const nextRun = (state.runCount ?? 0) + 1;
  const fullRun = nextRun % fullEvery === 0;
  const includeYouTube = nextRun % youtubeEvery === 0;

  const enabledTargets = targets.filter((target) => target?.enabled !== false);
  const sorted = [...enabledTargets].sort(compareTargets);
  const youtubeTargets = sorted.filter((target) => target.kind === "youtube-transcript");
  const regularTargets = sorted.filter((target) => target.kind !== "youtube-transcript");
  const cursor = Number.isFinite(state.cursor) ? state.cursor : 0;
  const batch = [];

  const reserveYouTubeSlot = includeYouTube && youtubeTargets.length > 0 && maxTargets > 1;
  const regularLimit = reserveYouTubeSlot ? maxTargets - 1 : maxTargets;

  for (let i = 0; i < regularTargets.length && batch.length < regularLimit; i += 1) {
    const target = regularTargets[(cursor + i) % regularTargets.length];
    batch.push(target);
  }

  if (includeYouTube && youtubeTargets.length > 0) {
    const youtubeCursor = Number.isFinite(state.youtubeCursor) ? state.youtubeCursor : 0;
    batch.push(youtubeTargets[youtubeCursor % youtubeTargets.length]);
  }

  return {
    nextRun,
    fullRun,
    includeYouTube,
    maxTargets,
    batch,
    nextCursor: regularTargets.length > 0 ? (cursor + regularLimit) % regularTargets.length : 0,
    nextYouTubeCursor: includeYouTube && youtubeTargets.length > 0
      ? ((Number.isFinite(state.youtubeCursor) ? state.youtubeCursor : 0) + 1) % youtubeTargets.length
      : (Number.isFinite(state.youtubeCursor) ? state.youtubeCursor : 0)
  };
}

async function runResearcher(args) {
  const commandArgs = ["src/cli.ts", "researcher-run"];
  const policyPath = await resolveResearcherPolicyPath();
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
    env: {
      ...process.env,
      RESEARCHER_TARGETS_PATH: args.targetsPath,
      RESEARCHER_POLICY_PATH: policyPath
    },
    maxBuffer: 1024 * 1024 * 16
  });
  return stdout.trim() ? JSON.parse(stdout) : {};
}

const startedAt = new Date().toISOString();

try {
  const [loadedTargets, previous] = await Promise.all([
    loadTargetsDoc(),
    readJson(statePath, { runCount: 0, cursor: 0 })
  ]);
  const targetsDoc = loadedTargets.doc;
  const targets = Array.isArray(targetsDoc.targets) ? targetsDoc.targets : [];
  const batch = chooseBatch(targets, previous);
  if (batch.batch.length === 0) {
    throw new Error(`no enabled researcher targets available in ${loadedTargets.path}`);
  }
  const report = await runResearcher({ ...batch, targetsPath: loadedTargets.path });

  const nextState = {
    runCount: batch.nextRun,
    cursor: batch.nextCursor,
    lastRunAt: startedAt,
    lastMode: batch.fullRun ? "full" : "light",
    lastTargets: batch.batch.map((target) => target.id),
    lastIncludeYouTube: batch.includeYouTube,
    youtubeCursor: batch.nextYouTubeCursor
  };

  const payload = {
    command: "bill-researcher-run-scheduled",
    startedAt,
    mode: batch.fullRun ? "full" : "light",
    targetsPath: loadedTargets.path,
    policyPath: await resolveResearcherPolicyPath(),
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
