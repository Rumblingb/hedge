import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readdir, readFile, stat, statfs, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const execFileAsync = promisify(execFile);

export interface AutonomyStatus {
  command: "autonomy-status";
  generatedAt: string;
  mode: "paper-only";
  status: "healthy" | "degraded" | "critical";
  paths: {
    outputPath: string;
    boardMarkdownPath: string;
    boardHtmlPath: string;
  };
  git: {
    branch: string | null;
    head: string | null;
    sourceDirty: boolean;
    runtimeDirty: boolean;
    stagedForbidden: string[];
  };
  compute: {
    maxHeavyJobs: number;
    heavyLockPresent: boolean;
    heavyLockAgeSeconds: number | null;
    posture: "available" | "busy";
  };
  artifacts: {
    predictionCycle: ArtifactStatus;
    researcher: ArtifactStatus;
    strategyLab: ArtifactStatus;
    forkIntake: ArtifactStatus;
    openJarvisBoard: ArtifactStatus;
    health: ArtifactStatus;
  };
  paperGates: {
    liveTradingDisabled: boolean;
    futuresDemoExecutionDisabled: boolean;
    predictionExecutionMode: string;
    predictionPaperEnabled: boolean;
  };
  disk: {
    freeGb: number | null;
    usedPct: number | null;
    largeColdCorpusGb: number | null;
  };
  warnings: string[];
  nextActions: string[];
}

export interface ArtifactStatus {
  path: string;
  present: boolean;
  ageSeconds: number | null;
  status: "fresh" | "stale" | "missing";
  summary: string;
}

export interface BuildAutonomyStatusOptions {
  outputPath?: string;
  baseDir?: string;
  now?: () => string;
  env?: NodeJS.ProcessEnv;
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/autonomy-status.latest.json";

function parsePositiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

async function fileAgeSeconds(path: string, nowMs: number): Promise<number | null> {
  try {
    const info = await stat(path);
    return Math.max(0, Math.round((nowMs - info.mtimeMs) / 1000));
  } catch {
    return null;
  }
}

async function artifactStatus(args: {
  path: string;
  label: string;
  maxAgeSeconds: number;
  nowMs: number;
}): Promise<ArtifactStatus> {
  const ageSeconds = await fileAgeSeconds(args.path, args.nowMs);
  if (ageSeconds === null) {
    return {
      path: args.path,
      present: false,
      ageSeconds: null,
      status: "missing",
      summary: `${args.label} is missing`
    };
  }
  const status = ageSeconds <= args.maxAgeSeconds ? "fresh" : "stale";
  return {
    path: args.path,
    present: true,
    ageSeconds,
    status,
    summary: `${args.label} is ${status} (${ageSeconds}s old)`
  };
}

async function runGit(args: string[], cwd: string): Promise<string | null> {
  try {
    const { stdout } = await execFileAsync("git", args, { cwd, encoding: "utf8", timeout: 5000 });
    return stdout.trim();
  } catch {
    return null;
  }
}

function statusPath(line: string): string {
  return line.slice(3).trim().replace(/^"|"$/g, "");
}

function isRuntimePath(path: string): boolean {
  return path.startsWith(".rumbling-hedge/")
    || path.startsWith("data/")
    || path.startsWith("journals/")
    || path.endsWith(".csv")
    || path === "OUTBOX.md"
    || path === "databento"
    || path.startsWith("databento/");
}

async function directorySizeBytes(root: string): Promise<number | null> {
  try {
    let total = 0;
    const entries = await readdir(root, { withFileTypes: true });
    for (const entry of entries) {
      const path = resolve(root, entry.name);
      if (entry.isDirectory()) {
        const childSize = await directorySizeBytes(path);
        total += childSize ?? 0;
      } else if (entry.isFile()) {
        total += (await stat(path)).size;
      }
    }
    return total;
  } catch {
    return null;
  }
}

async function diskUsage(baseDir: string): Promise<{ freeGb: number | null; usedPct: number | null }> {
  try {
    const stats = await statfs(baseDir);
    const totalBytes = stats.blocks * stats.bsize;
    const freeBytes = stats.bavail * stats.bsize;
    return {
      freeGb: Number((freeBytes / 1024 / 1024 / 1024).toFixed(2)),
      usedPct: totalBytes > 0 ? Number((((totalBytes - freeBytes) / totalBytes) * 100).toFixed(2)) : null
    };
  } catch {
    return { freeGb: null, usedPct: null };
  }
}

export async function buildAutonomyStatus(options: BuildAutonomyStatusOptions = {}): Promise<AutonomyStatus> {
  const baseDir = resolve(options.baseDir ?? process.cwd());
  const env = options.env ?? process.env;
  const generatedAt = options.now?.() ?? new Date().toISOString();
  const nowMs = Date.parse(generatedAt);
  const outputPath = resolve(baseDir, options.outputPath ?? DEFAULT_OUTPUT_PATH);
  const stateDir = resolve(baseDir, ".rumbling-hedge/state");
  const researchDir = resolve(baseDir, ".rumbling-hedge/research");
  const logDir = resolve(baseDir, ".rumbling-hedge/logs");
  const heavyLockDir = resolve(baseDir, env.BILL_HEAVY_JOB_LOCK_DIR ?? ".rumbling-hedge/run/heavy-job.lock");

  const artifacts = {
    predictionCycle: await artifactStatus({
      path: resolve(stateDir, "prediction-cycle.latest.json"),
      label: "prediction cycle",
      maxAgeSeconds: 20 * 60,
      nowMs
    }),
    researcher: await artifactStatus({
      path: resolve(stateDir, "researcher-scheduler.latest.json"),
      label: "researcher scheduler",
      maxAgeSeconds: 3 * 60 * 60,
      nowMs
    }),
    strategyLab: await artifactStatus({
      path: resolve(stateDir, "strategy-lab.latest.json"),
      label: "strategy lab",
      maxAgeSeconds: 8 * 60 * 60,
      nowMs
    }),
    forkIntake: await artifactStatus({
      path: resolve(researchDir, "forks/_latest-report.json"),
      label: "fork intake",
      maxAgeSeconds: 7 * 24 * 60 * 60,
      nowMs
    }),
    openJarvisBoard: await artifactStatus({
      path: resolve(stateDir, "openjarvis-board.md"),
      label: "OpenJarvis board",
      maxAgeSeconds: 60 * 60,
      nowMs
    }),
    health: await artifactStatus({
      path: resolve(logDir, "bill-health.latest.json"),
      label: "Bill health",
      maxAgeSeconds: 60 * 60,
      nowMs
    })
  };

  const gitStatusRaw = await runGit(["status", "--porcelain=v1"], baseDir) ?? "";
  const gitLines = gitStatusRaw.split(/\r?\n/).filter(Boolean);
  const runtimeDirty = gitLines.some((line) => isRuntimePath(statusPath(line)));
  const sourceDirty = gitLines.some((line) => !isRuntimePath(statusPath(line)));
  const stagedForbidden = gitLines
    .filter((line) => /^[MADRCU]/.test(line[0] ?? ""))
    .map(statusPath)
    .filter(isRuntimePath);
  const heavyLockAgeSeconds = await fileAgeSeconds(heavyLockDir, nowMs);
  const disk = await diskUsage(baseDir);
  const coldCorpusBytes = await directorySizeBytes(resolve(baseDir, ".rumbling-hedge/external/prediction-market-analysis"));
  const predictionCycle = await readJsonSafe<any>(artifacts.predictionCycle.path);
  const strategyLab = await readJsonSafe<any>(artifacts.strategyLab.path);
  const researcher = await readJsonSafe<any>(artifacts.researcher.path);
  const forkIntake = await readJsonSafe<any>(artifacts.forkIntake.path);

  const warnings: string[] = [];
  for (const artifact of Object.values(artifacts)) {
    if (artifact.status !== "fresh") warnings.push(artifact.summary);
  }
  if (sourceDirty) warnings.push("source tree has uncommitted source changes");
  if (stagedForbidden.length > 0) warnings.push("runtime/data files are staged and must be unstaged before push");
  if (disk.freeGb !== null && disk.freeGb < 25) warnings.push(`SSD free space is low (${disk.freeGb}GB)`);
  if ((predictionCycle?.scan?.counts?.["paper-trade"] ?? 0) === 0) warnings.push("prediction cycle has zero paper-trade candidates");
  if ((researcher?.report?.report?.strategyHypothesesCount ?? 0) === 0) warnings.push("researcher kept no strategy hypotheses in latest run");
  if ((strategyLab?.rollingOos?.aggregate?.windowsEvaluated ?? 0) < 4) warnings.push("strategy lab OOS evidence is thin");
  if ((forkIntake?.written ?? 0) === 0) warnings.push("fork intake cards have not been generated");

  const liveTradingDisabled = env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED !== "true";
  const futuresDemoExecutionDisabled = env.BILL_ENABLE_FUTURES_DEMO_EXECUTION !== "true";
  const predictionExecutionMode = env.BILL_PREDICTION_EXECUTION_MODE ?? "paper";
  const paperGates = {
    liveTradingDisabled,
    futuresDemoExecutionDisabled,
    predictionExecutionMode,
    predictionPaperEnabled: predictionExecutionMode === "paper"
  };
  if (!liveTradingDisabled) warnings.push("live prediction execution is enabled; v1 autonomy expects paper-only mode");
  if (!futuresDemoExecutionDisabled) warnings.push("futures demo execution is enabled; v1 autonomy expects shadow/paper-only mode");

  const critical = stagedForbidden.length > 0 || !liveTradingDisabled;
  const status = critical ? "critical" : warnings.length > 0 ? "degraded" : "healthy";

  return {
    command: "autonomy-status",
    generatedAt,
    mode: "paper-only",
    status,
    paths: {
      outputPath,
      boardMarkdownPath: resolve(stateDir, "openjarvis-board.md"),
      boardHtmlPath: resolve(stateDir, "openjarvis-board.html")
    },
    git: {
      branch: await runGit(["branch", "--show-current"], baseDir),
      head: await runGit(["rev-parse", "--short", "HEAD"], baseDir),
      sourceDirty,
      runtimeDirty,
      stagedForbidden
    },
    compute: {
      maxHeavyJobs: parsePositiveInt(env.BILL_MAX_HEAVY_JOBS, 1),
      heavyLockPresent: heavyLockAgeSeconds !== null,
      heavyLockAgeSeconds,
      posture: heavyLockAgeSeconds === null ? "available" : "busy"
    },
    artifacts,
    paperGates,
    disk: {
      ...disk,
      largeColdCorpusGb: coldCorpusBytes === null ? null : Number((coldCorpusBytes / 1024 / 1024 / 1024).toFixed(2))
    },
    warnings: Array.from(new Set(warnings)),
    nextActions: [
      warnings.some((warning) => warning.includes("fork intake")) ? "Run npm run bill:fork-intake." : null,
      warnings.some((warning) => warning.includes("OOS evidence")) ? "Run npm run bill:strategy-factory after fresh data is available." : null,
      disk.freeGb !== null && disk.freeGb < 25 ? "Move cold corpora/logs only after HDD write support is available." : null,
      "Keep live routing disabled until paper/OOS evidence and founder approval are explicit."
    ].filter((value): value is string => Boolean(value))
  };
}

export async function writeAutonomyStatus(options: BuildAutonomyStatusOptions = {}): Promise<AutonomyStatus> {
  const status = await buildAutonomyStatus(options);
  await mkdir(dirname(status.paths.outputPath), { recursive: true });
  await writeFile(status.paths.outputPath, `${JSON.stringify(status, null, 2)}\n`, "utf8");
  return status;
}
