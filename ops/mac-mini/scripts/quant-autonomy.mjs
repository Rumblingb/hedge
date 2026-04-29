import { access, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const tsxPath = path.resolve(repoRoot, "node_modules/.bin/tsx");
const outputPath = path.resolve(repoRoot, process.env.BILL_QUANT_AUTONOMY_LATEST_PATH ?? ".rumbling-hedge/state/quant-autonomy.latest.json");
const childTimeoutMs = Number.parseInt(process.env.BILL_QUANT_AUTONOMY_CHILD_TIMEOUT_MS ?? "900000", 10);
const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run") || process.env.BILL_QUANT_AUTONOMY_DRY_RUN === "true";
const force = args.has("--force") || process.env.BILL_QUANT_AUTONOMY_FORCE === "true";

function asMs(hours) {
  return hours * 60 * 60 * 1000;
}

async function fileAgeMs(pathname) {
  try {
    const info = await stat(pathname);
    return Date.now() - info.mtimeMs;
  } catch {
    return null;
  }
}

async function exists(pathname) {
  try {
    await access(pathname);
    return true;
  } catch {
    return false;
  }
}

async function readJson(pathname) {
  try {
    return JSON.parse(await readFile(pathname, "utf8"));
  } catch {
    return null;
  }
}

async function runNodeTask(task) {
  const startedAt = new Date().toISOString();
  if (dryRun) {
    return {
      ...task,
      status: "planned",
      startedAt,
      finishedAt: startedAt,
      stdoutBytes: 0,
      summary: "dry-run planned; no command executed"
    };
  }
  try {
    const { stdout, stderr } = await execFileAsync(task.file, task.args, {
      cwd: repoRoot,
      env: process.env,
      maxBuffer: 1024 * 1024 * 32,
      timeout: task.timeoutMs ?? childTimeoutMs
    });
    return {
      ...task,
      status: "completed",
      startedAt,
      finishedAt: new Date().toISOString(),
      stdoutBytes: Buffer.byteLength(stdout),
      stderrBytes: Buffer.byteLength(stderr),
      summary: stdout.trim().slice(0, 1000)
    };
  } catch (error) {
    return {
      ...task,
      status: "failed",
      startedAt,
      finishedAt: new Date().toISOString(),
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

function tsxTask(id, lane, priority, cliArgs, reason, timeoutMs) {
  return {
    id,
    lane,
    priority,
    heavy: true,
    file: process.execPath,
    args: [tsxPath, "src/cli.ts", ...cliArgs],
    reason,
    timeoutMs
  };
}

function nodeTask(id, lane, priority, scriptPath, reason, timeoutMs) {
  return {
    id,
    lane,
    priority,
    heavy: true,
    file: process.execPath,
    args: [scriptPath],
    reason,
    timeoutMs
  };
}

async function buildTaskQueue() {
  const taskSpecs = [
    {
      path: path.resolve(repoRoot, ".rumbling-hedge/research/forks/_latest-report.json"),
      maxAgeMs: asMs(Number.parseFloat(process.env.BILL_QUANT_FORK_INTAKE_MAX_AGE_HOURS ?? "168")),
      task: tsxTask("fork-intake", "research", 20, ["fork-intake"], "distill forked trading repos into compact cards instead of cloning heavy repos", asMs(1))
    },
    {
      path: path.resolve(repoRoot, ".rumbling-hedge/state/researcher-scheduler.latest.json"),
      maxAgeMs: asMs(Number.parseFloat(process.env.BILL_QUANT_RESEARCHER_MAX_AGE_HOURS ?? "3")),
      task: nodeTask("researcher-scheduled", "research", 30, "ops/mac-mini/scripts/researcher-scheduled.mjs", "refresh transcript/web/repo research and delete raw transcript artifacts after strategy cards", asMs(2))
    },
    {
      path: path.resolve(repoRoot, ".rumbling-hedge/state/strategy-lab.latest.json"),
      maxAgeMs: asMs(Number.parseFloat(process.env.BILL_QUANT_STRATEGY_LAB_MAX_AGE_HOURS ?? "8")),
      task: nodeTask("strategy-lab", "strategy-testing", 40, "ops/mac-mini/scripts/strategy-lab.mjs", "run walk-forward/OOS/stress gates and keep strategy promotion fail-closed", asMs(2))
    },
    {
      path: path.resolve(repoRoot, ".rumbling-hedge/state/futures-demo.latest.json"),
      maxAgeMs: asMs(Number.parseFloat(process.env.BILL_QUANT_PAPER_LOOP_MAX_AGE_HOURS ?? "12")),
      task: tsxTask("paper-loop-shadow-sample", "paper-demo", 50, ["demo-overnight", process.env.BILL_PAPER_LOOP_CSV_PATH ?? "data/free/ALL-6MARKETS-1m-10d-normalized.csv"], "rotate strategy samples only after gates remain paper/shadow safe", asMs(1))
    }
  ];

  const queue = [];
  for (const spec of taskSpecs) {
    if (spec.task.id === "paper-loop-shadow-sample" && process.env.BILL_QUANT_AUTONOMY_RUN_PAPER_LOOP !== "true") {
      continue;
    }
    const ageMs = await fileAgeMs(spec.path);
    const due = force || ageMs === null || ageMs > spec.maxAgeMs;
    queue.push({
      ...spec.task,
      artifactPath: spec.path,
      artifactPresent: ageMs !== null,
      artifactAgeSeconds: ageMs === null ? null : Math.round(ageMs / 1000),
      due
    });
  }
  return queue.sort((left, right) => left.priority - right.priority);
}

const startedAt = new Date().toISOString();
const taskQueue = await buildTaskQueue();
const dueTasks = taskQueue.filter((task) => task.due);
const executed = [];

for (const task of dueTasks) {
  executed.push(await runNodeTask(task));
}

const status = executed.some((task) => task.status === "failed")
  ? "degraded"
  : dueTasks.length === 0
    ? "idle"
    : dryRun
      ? "planned"
      : "completed";

await runNodeTask(tsxTask("autonomy-status", "dashboard", 90, ["autonomy-status"], "refresh machine-readable health surface", asMs(0.25)));
await runNodeTask(tsxTask("openjarvis-board", "dashboard", 91, ["openjarvis-board"], "refresh founder dashboard after machine work", asMs(0.25)));

const strategyFactory = await readJson(path.resolve(repoRoot, ".rumbling-hedge/state/strategy-factory.latest.json"));
const autonomyStatus = await readJson(path.resolve(repoRoot, ".rumbling-hedge/state/autonomy-status.latest.json"));
const payload = {
  command: "bill-quant-autonomy",
  startedAt,
  finishedAt: new Date().toISOString(),
  status,
  dryRun,
  force,
  maxHeavyJobs: Number.parseInt(process.env.BILL_MAX_HEAVY_JOBS ?? "1", 10),
  posture: "machine-first-token-lean",
  tokenPolicy: [
    "run local CLI/scripts for research, OOS, paper/demo, and dashboard work",
    "persist compact JSON cards/reports instead of raw transcripts, browser pages, or cloned repos",
    "use cloud/hosted models only behind configured daily call/token budgets"
  ],
  taskQueue: taskQueue.map(({ file, args, ...task }) => ({
    ...task,
    command: `${path.basename(file)} ${args.join(" ")}`
  })),
  executed: executed.map(({ file, args, ...task }) => ({
    ...task,
    command: `${path.basename(file)} ${args.join(" ")}`
  })),
  quantState: {
    strategyFactoryStatus: strategyFactory?.status ?? null,
    blockers: strategyFactory?.blockers ?? [],
    quantCoverage: strategyFactory?.quantCoverage ?? null,
    researchContext: strategyFactory?.researchContext
      ? {
          researchFeedStrategyCount: strategyFactory.researchContext.researchFeedStrategyCount,
          redFolderEvents: strategyFactory.researchContext.redFolderEvents,
          traderIntuitionSummary: strategyFactory.researchContext.traderIntuition?.summaryLines ?? []
        }
      : null,
    autonomyStatus: autonomyStatus?.status ?? null,
    autonomyWarnings: autonomyStatus?.warnings ?? []
  },
  nextAction: status === "idle"
    ? "No heavy quant task is due; keep launchd cadence running and preserve SSD headroom."
    : "Review strategy-factory blockers and let the next scheduled pass focus on the highest-priority due lane."
};

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
console.log(JSON.stringify(payload, null, 2));

if (status === "degraded") {
  process.exitCode = 1;
}
