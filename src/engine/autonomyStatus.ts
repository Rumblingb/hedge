import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readdir, readFile, stat, statfs, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { assessLatestOperatorIntent, type OperatorIntentAssessment } from "./operatorIntent.js";
import { readKillSwitch } from "./killSwitch.js";

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
    sourceDirtyPaths: string[];
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
    liveReadinessGate: ArtifactStatus;
    quantAutonomy: ArtifactStatus;
    strategyIteration: ArtifactStatus;
    noEdgeLedger: ArtifactStatus;
    forkIntake: ArtifactStatus;
    forkSynthesis: ArtifactStatus;
    positioning: ArtifactStatus;
    strategyFeed: ArtifactStatus;
    openJarvisBoard: ArtifactStatus;
    health: ArtifactStatus;
  };
  paperGates: {
    liveTradingDisabled: boolean;
    predictionMicroLiveSandboxEnabled: boolean;
    predictionMicroLiveSandboxSafe: boolean;
    predictionLiveMaxStake: number;
    predictionLiveMaxRiskPct: number;
    predictionLiveMaxExposurePct: number;
    futuresDemoExecutionDisabled: boolean;
    futuresDemoExplorationSafe: boolean;
    predictionExecutionMode: string;
    predictionPaperEnabled: boolean;
    killSwitchActive: boolean;
    killSwitchReason: string | null;
  };
  disk: {
    freeGb: number | null;
    usedPct: number | null;
    largeColdCorpusGb: number | null;
  };
  trustBoundary: {
    voiceInputMode: "advisory-only";
    operatorIntent: OperatorIntentAssessment;
    executionWideningRequiresApproval: boolean;
    hallucinationControls: string[];
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

function parsePositiveNumber(value: string | undefined, fallback: number): number {
  const parsed = Number.parseFloat(value ?? "");
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

async function runGitRaw(args: string[], cwd: string): Promise<string | null> {
  try {
    const { stdout } = await execFileAsync("git", args, { cwd, encoding: "utf8", timeout: 5000 });
    return stdout;
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
    liveReadinessGate: await artifactStatus({
      path: resolve(stateDir, "live-readiness-gate.latest.json"),
      label: "live-readiness gate",
      maxAgeSeconds: 60 * 60,
      nowMs
    }),
    quantAutonomy: await artifactStatus({
      path: resolve(stateDir, "quant-autonomy.latest.json"),
      label: "quant autonomy",
      maxAgeSeconds: 12 * 60 * 60,
      nowMs
    }),
    strategyIteration: await artifactStatus({
      path: resolve(researchDir, "strategy-iterations/latest.json"),
      label: "strategy iteration",
      maxAgeSeconds: 7 * 24 * 60 * 60,
      nowMs
    }),
    noEdgeLedger: await artifactStatus({
      path: resolve(researchDir, "no-edge-ledger/latest.json"),
      label: "no-edge strategy ledger",
      maxAgeSeconds: 7 * 24 * 60 * 60,
      nowMs
    }),
    forkIntake: await artifactStatus({
      path: resolve(researchDir, "forks/_latest-report.json"),
      label: "fork intake",
      maxAgeSeconds: 7 * 24 * 60 * 60,
      nowMs
    }),
    forkSynthesis: await artifactStatus({
      path: resolve(researchDir, "forks/_synthesis.latest.json"),
      label: "fork synthesis",
      maxAgeSeconds: 7 * 24 * 60 * 60,
      nowMs
    }),
    positioning: await artifactStatus({
      path: resolve(researchDir, "positioning/latest.json"),
      label: "positioning context",
      maxAgeSeconds: 3 * 24 * 60 * 60,
      nowMs
    }),
    strategyFeed: await artifactStatus({
      path: resolve(researchDir, "researcher/strategy-feed.latest.json"),
      label: "research strategy feed",
      maxAgeSeconds: 3 * 24 * 60 * 60,
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

  const gitStatusRaw = await runGitRaw(["status", "--porcelain=v1"], baseDir) ?? "";
  const gitLines = gitStatusRaw.split(/\r?\n/).filter(Boolean);
  const runtimeDirty = gitLines.some((line) => isRuntimePath(statusPath(line)));
  const sourceDirtyPaths = gitLines
    .map(statusPath)
    .filter((path) => !isRuntimePath(path));
  const sourceDirty = sourceDirtyPaths.length > 0;
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
  const forkSynthesis = await readJsonSafe<any>(artifacts.forkSynthesis.path);
  const positioning = await readJsonSafe<any>(artifacts.positioning.path);
  const strategyFeed = await readJsonSafe<any>(artifacts.strategyFeed.path);
  const noEdgeLedger = await readJsonSafe<any>(artifacts.noEdgeLedger.path);
  const operatorIntent = await assessLatestOperatorIntent({ env });

  const warnings: string[] = [];
  for (const artifact of Object.values(artifacts)) {
    if (artifact.status !== "fresh") warnings.push(artifact.summary);
  }
  if (sourceDirty) warnings.push("source tree has uncommitted source changes");
  if (stagedForbidden.length > 0) warnings.push("runtime/data files are staged and must be unstaged before push");
  if (disk.freeGb !== null && disk.freeGb < 25) warnings.push(`SSD free space is low (${disk.freeGb}GB)`);
  if ((predictionCycle?.scan?.counts?.["paper-trade"] ?? 0) === 0) {
    const viablePairs = predictionCycle?.scan?.diagnostics?.viablePairs;
    warnings.push(
      viablePairs === 0
        ? "prediction cycle has zero paper-trade candidates because latest scan found no viable cross-venue pairs"
        : "prediction cycle has zero paper-trade candidates"
    );
  }
  if ((researcher?.report?.report?.strategyHypothesesCount ?? 0) === 0) warnings.push("researcher kept no strategy hypotheses in latest run");
  if ((strategyFeed?.directives?.length ?? 0) === 0) warnings.push("research strategy feed has no machine-testable directives");
  if (!noEdgeLedger || (noEdgeLedger.count ?? 0) === 0) warnings.push("no-edge ledger is missing; agents may rediscover already-failed strategies");
  if ((positioning?.cot?.symbols?.length ?? 0) === 0) warnings.push("positioning context is missing CFTC COT coverage");
  if ((strategyLab?.rollingOos?.aggregate?.windowsEvaluated ?? 0) < 4) warnings.push("strategy lab OOS evidence is thin");
  if ((forkIntake?.written ?? 0) === 0) warnings.push("fork intake cards have not been generated");
  if ((forkSynthesis?.adoptedCount ?? 0) === 0) warnings.push("fork synthesis has not produced adoptable Bill/Hedge patterns");
  if (operatorIntent.status === "requires-approval") warnings.push(operatorIntent.summary);

  const liveTradingDisabled = env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED !== "true";
  const predictionMicroLiveSandboxEnabled = env.BILL_PREDICTION_MICRO_LIVE_SANDBOX_ENABLED === "true";
  const predictionLiveMaxStake = parsePositiveNumber(env.BILL_PREDICTION_LIVE_MAX_STAKE, Number.POSITIVE_INFINITY);
  const predictionLiveMaxRiskPct = parsePositiveNumber(env.BILL_PREDICTION_MAX_RISK_PCT, Number.POSITIVE_INFINITY);
  const predictionLiveMaxExposurePct = parsePositiveNumber(env.BILL_PREDICTION_MAX_EXPOSURE_PCT, Number.POSITIVE_INFINITY);
  const predictionMicroLiveSandboxSafe = liveTradingDisabled || (
    predictionMicroLiveSandboxEnabled
    && predictionLiveMaxStake <= 2
    && predictionLiveMaxRiskPct <= 1
    && predictionLiveMaxExposurePct <= 1
  );
  const futuresDemoExecutionDisabled = env.BILL_ENABLE_FUTURES_DEMO_EXECUTION !== "true";
  const futuresDemoMaxOrders = Number.parseInt(env.BILL_FUTURES_DEMO_MAX_ORDERS_PER_RUN ?? "1", 10);
  const futuresDemoRouteConstrained = env.RH_TOPSTEP_DEMO_ONLY !== "false"
    && Number.isFinite(futuresDemoMaxOrders)
    && futuresDemoMaxOrders <= 1;
  const futuresDemoExplorationSafe = futuresDemoExecutionDisabled || futuresDemoRouteConstrained;
  const predictionExecutionMode = env.BILL_PREDICTION_EXECUTION_MODE ?? "paper";
  const killSwitchPath = resolve(baseDir, ".rumbling-hedge/state/kill-switch.json");
  const killSwitchState = await readKillSwitch(killSwitchPath);
  const paperGates = {
    liveTradingDisabled,
    predictionMicroLiveSandboxEnabled,
    predictionMicroLiveSandboxSafe,
    predictionLiveMaxStake,
    predictionLiveMaxRiskPct,
    predictionLiveMaxExposurePct,
    futuresDemoExecutionDisabled,
    futuresDemoExplorationSafe,
    predictionExecutionMode,
    predictionPaperEnabled: predictionExecutionMode === "paper",
    killSwitchActive: killSwitchState.active,
    killSwitchReason: killSwitchState.reason
  };
  if (killSwitchState.active) warnings.push(`kill switch ACTIVE — ${killSwitchState.reason ?? "no reason given"}`);
  if (!liveTradingDisabled && predictionMicroLiveSandboxSafe) {
    warnings.push(`prediction micro-live sandbox is enabled with max stake ${predictionLiveMaxStake}; this is not full live-readiness`);
  } else if (!liveTradingDisabled) {
    warnings.push("live prediction execution is enabled outside the approved micro-live sandbox");
  }
  if (!futuresDemoExecutionDisabled && !futuresDemoRouteConstrained) warnings.push("futures demo execution is enabled without the demo-only max-one-order routing envelope");

  const critical = stagedForbidden.length > 0 || !predictionMicroLiveSandboxSafe;
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
      sourceDirtyPaths,
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
    trustBoundary: {
      voiceInputMode: "advisory-only",
      operatorIntent,
      executionWideningRequiresApproval: true,
      hallucinationControls: [
        "voice/operator input cannot bypass OOS, paper, risk, or kill-switch gates",
        "research transcripts and forked repos are distilled into compact cards before strategy tests",
        "full live routing remains disabled unless promotion state and explicit approval both agree",
        "daily loss, trailing drawdown, consecutive-loss, session, news, and contract limits are programmatic guardrails"
      ]
    },
    warnings: Array.from(new Set(warnings)),
    nextActions: [
      warnings.some((warning) => warning.includes("fork intake")) ? "Run npm run bill:fork-intake." : null,
      warnings.some((warning) => warning.includes("fork synthesis")) ? "Run npm run bill:fork-synthesis." : null,
      warnings.some((warning) => warning.includes("positioning context")) ? "Run npm run bill:positioning-status." : null,
      warnings.some((warning) => warning.includes("no-edge ledger")) ? "Run npm run bill:strategy-factory to refresh negative-edge memory." : null,
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
