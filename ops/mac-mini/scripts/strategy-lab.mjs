import { access, mkdir, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const tsxPath = path.resolve(repoRoot, "node_modules/.bin/tsx");
const latestPath = path.resolve(repoRoot, process.env.BILL_STRATEGY_LAB_LATEST_PATH ?? ".rumbling-hedge/state/strategy-lab.latest.json");
const statePath = path.resolve(repoRoot, process.env.BILL_STRATEGY_LAB_STATE_PATH ?? ".rumbling-hedge/state/strategy-lab.scheduler.json");
const childTimeoutMs = parsePositiveInt(process.env.BILL_STRATEGY_LAB_CHILD_TIMEOUT_MS, 120_000);

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

async function runCli(args) {
  const { stdout } = await execFileAsync(process.execPath, [tsxPath, "src/cli.ts", ...args], {
    cwd: repoRoot,
    env: process.env,
    maxBuffer: 1024 * 1024 * 16,
    timeout: childTimeoutMs
  });
  const trimmed = stdout.trim();
  return trimmed ? JSON.parse(trimmed) : {};
}

async function runCliOptional(args, command) {
  try {
    return await runCli(args);
  } catch (error) {
    return {
      command,
      status: "failed",
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

async function fileExists(pathname) {
  try {
    await access(pathname);
    return true;
  } catch {
    return false;
  }
}

function buildScheduledStrategyFactoryGate(args) {
  const rollingAggregate = args.rollingOos?.aggregate ?? {};
  const minOosWindows = parsePositiveInt(process.env.BILL_STRATEGY_FACTORY_MIN_OOS_WINDOWS, 4);
  const gates = {
    rollingOosWindows: Number(rollingAggregate.windowsEvaluated ?? 0),
    minRollingOosWindows: minOosWindows,
    rollingOosDeployableWindows: Number(rollingAggregate.tunedDeployableWindows ?? 0),
    liveReadinessDeployable: args.liveReadiness?.final?.report?.deployableNow === true,
    liveDisabled: process.env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED !== "true",
    futuresDemoDisabled: process.env.BILL_ENABLE_FUTURES_DEMO_EXECUTION !== "true"
  };
  const blockers = [
    ...(gates.rollingOosWindows < gates.minRollingOosWindows ? [`rolling OOS evidence is thin (${gates.rollingOosWindows}/${gates.minRollingOosWindows} windows)`] : []),
    ...(gates.rollingOosDeployableWindows < gates.minRollingOosWindows ? ["not all rolling OOS windows are deployable"] : []),
    ...(!gates.liveReadinessDeployable ? ["stressed live-readiness pass is not deployable or was skipped this light cycle"] : []),
    ...(!gates.liveDisabled ? ["live prediction execution must remain disabled for v1"] : []),
    ...(!gates.futuresDemoDisabled ? ["futures demo execution must remain disabled for v1 paper-only autonomy"] : [])
  ];
  return {
    command: "strategy-factory",
    mode: "paper-only",
    source: "scheduled-strategy-lab-existing-artifacts",
    status: blockers.length === 0 ? "promotable-to-paper" : "blocked",
    gates,
    blockers
  };
}

const startedAt = new Date().toISOString();

try {
  const previous = await readJson(statePath, { runCount: 0 });
  const fullEvery = parsePositiveInt(process.env.BILL_STRATEGY_LAB_FULL_EVERY_NTH_RUN, 4);
  const liveEvery = parsePositiveInt(process.env.BILL_STRATEGY_LAB_LIVE_READINESS_EVERY_NTH_RUN, fullEvery);
  const runCount = (previous.runCount ?? 0) + 1;
  const fullRun = runCount % fullEvery === 0;
  const liveReadinessRun = runCount % liveEvery === 0;
  const csvPath = process.env.BILL_STRATEGY_LAB_CSV_PATH
    ?? "data/free/ALL-6MARKETS-1m-10d-normalized.csv";
  const oosCsvPath = process.env.BILL_STRATEGY_LAB_OOS_CSV_PATH
    ?? "data/free/ALL-6MARKETS-1m-30d-normalized.csv";

  const liveReadiness = liveReadinessRun
    ? await runCliOptional(["live-readiness", csvPath, "1"], "live-readiness")
    : {
        command: "live-readiness",
        status: "skipped",
        reason: `Runs every ${liveEvery} strategy-lab cycle(s); skipped light cadence to preserve CPU.`
      };
  const rollingOos = await fileExists(path.resolve(repoRoot, oosCsvPath))
    ? await runCliOptional([
        "oos-rolling",
        oosCsvPath,
        process.env.BILL_STRATEGY_LAB_OOS_WINDOWS ?? "4",
        process.env.BILL_STRATEGY_LAB_OOS_MIN_TRAIN_DAYS ?? "20",
        process.env.BILL_STRATEGY_LAB_OOS_TEST_DAYS ?? "5",
        process.env.BILL_STRATEGY_LAB_OOS_EMBARGO_DAYS ?? "1"
      ], "oos-rolling")
    : {
        command: "oos-rolling",
        status: "skipped",
        reason: `OOS dataset not found: ${oosCsvPath}`
      };
  const jarvisLoop = fullRun ? await runCliOptional(["jarvis-loop", csvPath], "jarvis-loop") : null;
  const markovOos = fullRun ? await runCliOptional(["markov-oos", "data/research", "20", "5", "5"], "markov-oos") : null;
  const strategyFactory = buildScheduledStrategyFactoryGate({ liveReadiness, rollingOos });
  const autonomyStatus = await runCliOptional(["autonomy-status"], "autonomy-status");
  const board = await runCliOptional(["openjarvis-board"], "openjarvis-board");

  const state = {
    runCount,
    lastRunAt: startedAt,
    lastMode: fullRun ? "full" : "light",
    lastLiveReadinessMode: liveReadinessRun ? "run" : "skipped",
    lastCsvPath: csvPath,
    lastOosCsvPath: oosCsvPath
  };
  const payload = {
    command: "bill-strategy-lab-scheduled",
    startedAt,
    mode: fullRun ? "full" : "light",
    csvPath,
    oosCsvPath,
    childTimeoutMs,
    liveReadinessEveryNthRun: liveEvery,
    liveReadiness,
    rollingOos,
    strategyFactory,
    jarvisLoop,
    markovOos,
    autonomyStatus,
    board
  };

  await mkdir(path.dirname(latestPath), { recursive: true });
  await mkdir(path.dirname(statePath), { recursive: true });
  await Promise.all([
    writeFile(latestPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8"),
    writeFile(statePath, `${JSON.stringify(state, null, 2)}\n`, "utf8")
  ]);

  console.log(JSON.stringify(payload, null, 2));
} catch (error) {
  const payload = {
    command: "bill-strategy-lab-scheduled",
    startedAt,
    status: "failed",
    error: error instanceof Error ? error.message : String(error)
  };
  await mkdir(path.dirname(latestPath), { recursive: true });
  await writeFile(latestPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(payload, null, 2));
  process.exitCode = 1;
}
