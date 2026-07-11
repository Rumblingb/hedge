import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, statfsSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../../..");
const tsxPath = path.join(repoRoot, "node_modules/.bin/tsx");
const esbuildPath = path.join(repoRoot, "node_modules/.bin/esbuild");
const logDir = path.join(repoRoot, ".rumbling-hedge/logs");
const envPath = path.join(repoRoot, ".env");
const secureEnvPath = path.join(os.homedir(), "Library/Application Support/AgentPay/bill/bill.env");
const packageLockPath = path.join(repoRoot, "package-lock.json");
const predictionJournalPath = path.join(repoRoot, process.env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
const predictionSnapshotPath = path.join(repoRoot, process.env.BILL_PREDICTION_COLLECT_OUTPUT_PATH ?? ".rumbling-hedge/runtime/prediction/combined-live-snapshot.json");
const predictionCycleHistoryPath = path.join(repoRoot, process.env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl");
const predictionLearningHistoryPath = path.join(repoRoot, process.env.BILL_PREDICTION_LEARNING_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-learning-history.jsonl");
const promotionStatePath = path.join(repoRoot, process.env.BILL_PROMOTION_STATE_PATH ?? ".rumbling-hedge/state/promotion-state.json");
const predictionReviewPath = path.join(repoRoot, process.env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
const predictionCopyDemoPath = path.join(repoRoot, process.env.BILL_PREDICTION_COPY_DEMO_PATH ?? ".rumbling-hedge/state/prediction-copy-demo.latest.json");
const predictionCopyDemoHistoryPath = path.join(repoRoot, process.env.BILL_PREDICTION_COPY_DEMO_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-copy-demo-history.jsonl");
const predictionLearningStatePath = path.join(repoRoot, process.env.BILL_PREDICTION_LEARNING_STATE_PATH ?? ".rumbling-hedge/state/prediction-learning.latest.json");
const predictionLearnedPolicyPath = path.join(repoRoot, process.env.BILL_PREDICTION_LEARNED_POLICY_PATH ?? ".rumbling-hedge/state/prediction-learned-policy.json");
const predictionTrainingSetPath = path.join(repoRoot, process.env.BILL_PREDICTION_TRAINING_SET_PATH ?? ".rumbling-hedge/research/prediction-training-set.json");
const researchCatalogPath = path.join(repoRoot, process.env.BILL_RESEARCH_CATALOG_PATH ?? ".rumbling-hedge/research/catalog.json");
const futuresDemoSamplesJournalPath = path.join(repoRoot, process.env.BILL_FUTURES_DEMO_SAMPLES_JOURNAL_PATH ?? ".rumbling-hedge/logs/futures-demo-samples.jsonl");
const futuresDemoLatestPath = path.join(repoRoot, process.env.BILL_FUTURES_DEMO_SAMPLES_LATEST_PATH ?? ".rumbling-hedge/state/futures-demo.latest.json");
const trackPolicyPath = path.join(repoRoot, ".rumbling-hedge/research/track-policy.json");
const toolRegistryPath = path.join(repoRoot, ".rumbling-hedge/research/tool-registry.json");
const sourceCatalogPath = path.join(repoRoot, ".rumbling-hedge/research/source-catalog.json");
const researcherSchedulerLatestPath = path.join(repoRoot, process.env.BILL_RESEARCHER_SCHEDULER_LATEST_PATH ?? ".rumbling-hedge/state/researcher-scheduler.latest.json");
const strategyLabLatestPath = path.join(repoRoot, process.env.BILL_STRATEGY_LAB_LATEST_PATH ?? ".rumbling-hedge/state/strategy-lab.latest.json");
const openJarvisBoardHtmlPath = path.join(repoRoot, process.env.BILL_OPENJARVIS_BOARD_HTML_PATH ?? ".rumbling-hedge/state/openjarvis-board.html");
const openJarvisBoardMarkdownPath = path.join(repoRoot, process.env.BILL_OPENJARVIS_BOARD_MARKDOWN_PATH ?? ".rumbling-hedge/state/openjarvis-board.md");
const cloudBudgetLedgerPath = path.join(repoRoot, process.env.BILL_CLOUD_BUDGET_LEDGER_PATH ?? ".rumbling-hedge/state/cloud-budget-ledger.json");
const latestHealthPath = path.join(logDir, "bill-health.latest.json");
const runDeepHealth = process.env.BILL_HEALTH_DEEP === "true";

mkdirSync(logDir, { recursive: true });

function run(command, args, options = {}) {
  try {
    return execFileSync(command, args, {
      cwd: repoRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PATH: `/opt/homebrew/opt/node/bin:/opt/homebrew/bin:${process.env.PATH ?? "/usr/bin:/bin:/usr/sbin:/sbin"}`
      },
      ...options
    }).trim();
  } catch (error) {
    const stdout = typeof error.stdout === "string" ? error.stdout.trim() : "";
    const stderr = typeof error.stderr === "string" ? error.stderr.trim() : "";
    const message = stderr || stdout || error.message;
    throw new Error(message);
  }
}

function runJson(command, args) {
  const raw = run(command, args);
  return raw ? JSON.parse(raw) : null;
}

function tryRun(command, args) {
  try {
    return { ok: true, output: run(command, args) };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

function readLatestJsonlEntry(filePath) {
  if (!existsSync(filePath)) return null;
  const lines = readFileSync(filePath, "utf8").split(/\r?\n/).filter(Boolean);
  if (lines.length === 0) return null;
  return JSON.parse(lines.at(-1));
}

function readJson(filePath) {
  if (!existsSync(filePath)) return null;
  return JSON.parse(readFileSync(filePath, "utf8"));
}

function fileAgeSeconds(filePath) {
  if (!existsSync(filePath)) return null;
  return Math.max(0, Math.round(Date.now() / 1000 - statSync(filePath).mtimeMs / 1000));
}

function bytesToMb(value) {
  return Number((value / 1024 / 1024).toFixed(2));
}

function directorySizeBytes(dirPath) {
  if (!existsSync(dirPath)) return 0;
  let total = 0;
  for (const entry of readdirSync(dirPath, { withFileTypes: true })) {
    const entryPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      total += directorySizeBytes(entryPath);
    } else if (entry.isFile()) {
      total += statSync(entryPath).size;
    }
  }
  return total;
}

function diskUsage(dirPath) {
  try {
    const stats = statfsSync(dirPath);
    const totalBytes = stats.blocks * stats.bsize;
    const freeBytes = stats.bavail * stats.bsize;
    const usedPct = totalBytes > 0 ? ((totalBytes - freeBytes) / totalBytes) * 100 : 0;
    return {
      totalGb: Number((totalBytes / 1024 / 1024 / 1024).toFixed(2)),
      freeGb: Number((freeBytes / 1024 / 1024 / 1024).toFixed(2)),
      usedPct: Number(usedPct.toFixed(2))
    };
  } catch {
    return null;
  }
}

function firstNonEmptyString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }
  return null;
}

function trimTrailingPeriods(value) {
  return typeof value === "string"
    ? value.replace(/[.]+$/u, "")
    : null;
}

function gitStatusPath(line) {
  return line.slice(3).trim().replace(/^"|"$/g, "");
}

function isRuntimeStatusLine(line) {
  const filePath = gitStatusPath(line);
  return filePath.startsWith(".rumbling-hedge/")
    || filePath.startsWith("journals/")
    || filePath.startsWith("data/prediction/")
    || filePath.startsWith("data/research/")
    || filePath === "OUTBOX.md"
    || filePath.startsWith(".env.");
}

const gitStatusLines = run("git", ["status", "--short"]).split("\n").filter(Boolean);
const runtimeStatusLines = gitStatusLines.filter(isRuntimeStatusLine);
const sourceStatusLines = gitStatusLines.filter((line) => !isRuntimeStatusLine(line));

const health = {
  command: "bill-health",
  timestamp: new Date().toISOString(),
  repoRoot,
  host: {
    hostname: os.hostname(),
    platform: process.platform,
    arch: process.arch,
    nodeVersion: process.version
  },
  repo: {
    branch: run("git", ["rev-parse", "--abbrev-ref", "HEAD"]),
    head: run("git", ["rev-parse", "HEAD"]),
    dirty: gitStatusLines.length > 0,
    sourceDirty: sourceStatusLines.length > 0,
    runtimeDirty: runtimeStatusLines.length > 0,
    status: sourceStatusLines,
    runtimeStatus: runtimeStatusLines
  },
  runtime: {
    tsxInstalled: existsSync(tsxPath),
    envFilePresent: existsSync(envPath),
    secureEnvFilePresent: existsSync(secureEnvPath),
    packageLockPresent: existsSync(packageLockPath),
    logDir,
    latestHealthPath,
    predictionCycleHistoryPath,
    predictionCycleHistoryPresent: existsSync(predictionCycleHistoryPath),
    predictionLearningHistoryPath,
    predictionLearningHistoryPresent: existsSync(predictionLearningHistoryPath),
    promotionStatePath,
    promotionStatePresent: existsSync(promotionStatePath),
    predictionReviewPath,
    predictionReviewPresent: existsSync(predictionReviewPath),
    predictionCopyDemoPath,
    predictionCopyDemoPresent: existsSync(predictionCopyDemoPath),
    predictionCopyDemoHistoryPath,
    predictionCopyDemoHistoryPresent: existsSync(predictionCopyDemoHistoryPath),
    predictionLearningStatePath,
    predictionLearningStatePresent: existsSync(predictionLearningStatePath),
    predictionLearnedPolicyPath,
    predictionLearnedPolicyPresent: existsSync(predictionLearnedPolicyPath),
    predictionTrainingSetPath,
    predictionTrainingSetPresent: existsSync(predictionTrainingSetPath),
    researchCatalogPath,
    researchCatalogPresent: existsSync(researchCatalogPath),
    futuresDemoSamplesJournalPath,
    futuresDemoSamplesJournalPresent: existsSync(futuresDemoSamplesJournalPath),
    futuresDemoLatestPath,
    futuresDemoLatestPresent: existsSync(futuresDemoLatestPath),
    trackPolicyPath,
    trackPolicyPresent: existsSync(trackPolicyPath),
    toolRegistryPath,
    toolRegistryPresent: existsSync(toolRegistryPath),
    sourceCatalogPath,
    sourceCatalogPresent: existsSync(sourceCatalogPath),
    researcherSchedulerLatestPath,
    researcherSchedulerLatestPresent: existsSync(researcherSchedulerLatestPath),
    strategyLabLatestPath,
    strategyLabLatestPresent: existsSync(strategyLabLatestPath),
    openJarvisBoardHtmlPath,
    openJarvisBoardHtmlPresent: existsSync(openJarvisBoardHtmlPath),
    openJarvisBoardMarkdownPath,
    openJarvisBoardMarkdownPresent: existsSync(openJarvisBoardMarkdownPath),
    heavyCompute: {
      maxJobs: Number.parseInt(process.env.BILL_MAX_HEAVY_JOBS ?? "1", 10),
      staleLockSeconds: Number.parseInt(process.env.BILL_HEAVY_JOB_STALE_LOCK_SECONDS ?? "21600", 10)
    },
    cloudBudget: {
      maxHostedCallsPerDay: process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY ?? null,
      ledgerPath: cloudBudgetLedgerPath,
      ledgerPresent: existsSync(cloudBudgetLedgerPath),
      latestLedger: readJson(cloudBudgetLedgerPath)
    },
    logRetention: {
      logMaxMb: Number.parseInt(process.env.BILL_LOG_MAX_MB ?? "16", 10),
      jsonlMaxMb: Number.parseInt(process.env.BILL_JSONL_MAX_MB ?? "64", 10),
      rotations: Number.parseInt(process.env.BILL_LOG_ROTATIONS ?? "3", 10),
      logDirSizeMb: bytesToMb(directorySizeBytes(logDir))
    },
    disk: diskUsage(repoRoot)
  },
  commands: {},
  warnings: [],
  recommendations: []
};

if (!existsSync(tsxPath)) {
  health.recommendations.push("Run 'npm install' in the Bill repo before using launchd wrappers.");
  console.log(JSON.stringify(health, null, 2));
  process.exit(2);
}

try {
  health.commands.doctor = runJson(tsxPath, ["src/cli.ts", "doctor"]);
} catch (error) {
  health.commands.doctor = { ok: false, error: error.message };
  health.recommendations.push("Doctor command failed. Fix CLI/runtime before scheduling Bill jobs.");
}

try {
  health.commands.killSwitch = runJson(tsxPath, ["src/cli.ts", "kill-switch", "status"]);
} catch (error) {
  health.commands.killSwitch = { ok: false, error: error.message };
  health.recommendations.push("Kill-switch status is unreadable. Bill should fail closed until it is fixed.");
}

health.commands.predictionReport = tryRun(tsxPath, ["src/cli.ts", "prediction-report"]);
health.commands.predictionReview = tryRun(tsxPath, ["src/cli.ts", "prediction-review"]);
health.commands.promotionStatus = tryRun(tsxPath, ["src/cli.ts", "promotion-status"]);
health.commands.marketTrackStatus = tryRun(tsxPath, ["src/cli.ts", "market-track-status"]);
health.commands.typecheck = runDeepHealth
  ? tryRun("npm", ["run", "-s", "typecheck"])
  : { ok: true, skipped: true, reason: "BILL_HEALTH_DEEP is not true" };
health.commands.esbuildOpportunityBundle = runDeepHealth
  ? existsSync(esbuildPath)
    ? tryRun(esbuildPath, [
        "src/opportunity/orchestrator.ts",
        "--bundle",
        "--platform=node",
        "--format=esm",
        `--outfile=${path.join(os.tmpdir(), "bill-opportunity-orchestrator.mjs")}`
      ])
    : { ok: false, error: "esbuild binary is not installed" }
  : { ok: true, skipped: true, reason: "BILL_HEALTH_DEEP is not true" };
health.commands.costProfile = runDeepHealth
  ? tryRun(process.execPath, ["ops/mac-mini/scripts/cost-profile.mjs"])
  : { ok: true, skipped: true, reason: "BILL_HEALTH_DEEP is not true" };
health.commands.researchReport = runDeepHealth
  ? tryRun(tsxPath, ["src/cli.ts", "research-agent-report"])
  : { ok: true, skipped: true, reason: "BILL_HEALTH_DEEP is not true" };
health.runtime.predictionJournalPresent = existsSync(predictionJournalPath);
health.runtime.predictionSnapshotPresent = existsSync(predictionSnapshotPath);
health.runtime.predictionSnapshotPath = predictionSnapshotPath;
health.runtime.latestPredictionCycle = readLatestJsonlEntry(predictionCycleHistoryPath);
health.runtime.latestPredictionReview = readJson(predictionReviewPath);
health.runtime.latestPredictionCopyDemo = readJson(predictionCopyDemoPath);
health.runtime.latestFuturesDemo = readJson(futuresDemoLatestPath);
health.runtime.latestResearcherScheduler = readJson(researcherSchedulerLatestPath);
health.runtime.latestStrategyLab = readJson(strategyLabLatestPath);
health.runtime.researcherSchedulerAgeSeconds = fileAgeSeconds(researcherSchedulerLatestPath);
health.runtime.strategyLabAgeSeconds = fileAgeSeconds(strategyLabLatestPath);
health.runtime.openJarvisBoardAgeSeconds = fileAgeSeconds(openJarvisBoardMarkdownPath);
health.runtime.doctorWarnings = Array.isArray(health.commands.doctor?.warnings)
  ? health.commands.doctor.warnings
  : [];
health.runtime.doctorRuntime = health.commands.doctor?.runtime ?? null;

const venueCounts = health.runtime.latestPredictionCycle?.collect?.venueCounts ?? {};
if (Object.keys(venueCounts).length < 2) {
  health.warnings.push(`Combined prediction feed collapsed to ${JSON.stringify(venueCounts)}.`);
}
const latestReview = health.runtime.latestPredictionReview?.review ?? health.runtime.latestPredictionReview ?? null;
const latestReviewCounts = latestReview?.counts ?? health.runtime.latestPredictionCycle?.scan?.counts ?? {};
const latestResearcherScheduler = health.runtime.latestResearcherScheduler ?? null;
const latestResearcherReport = latestResearcherScheduler?.report ?? null;
const latestStrategyLab = health.runtime.latestStrategyLab ?? null;
if ((latestReviewCounts?.watch ?? 0) === 0 && (latestReviewCounts?.["paper-trade"] ?? 0) === 0) {
  health.warnings.push("Latest Bill cycle has no watch or paper-trade candidates.");
}
const latestCopyDemo = health.runtime.latestPredictionCopyDemo ?? null;
const latestFuturesDemo = health.runtime.latestFuturesDemo ?? null;
if (latestCopyDemo) {
  const shadowCount = latestCopyDemo.actionCounts?.["shadow-buy"] ?? 0;
  const ideaCount = Array.isArray(latestCopyDemo.ideas) ? latestCopyDemo.ideas.length : 0;
  const selectedLeaders = Number(latestCopyDemo.cohort?.selectedLeaders ?? 0);
  if (shadowCount === 0 && ideaCount > 0) {
    health.warnings.push("Copy-demo lane is watch-only. Consensus exists, but nothing is actionable yet.");
  }
  if (shadowCount === 0 && ideaCount === 0 && selectedLeaders === 0) {
    health.warnings.push("Copy-demo lane is idle under the founder-approved domain filter.");
  }
}
if (latestFuturesDemo?.execution?.enabled === true && Number(latestFuturesDemo.execution.submittedCount ?? 0) === 0) {
  const blocker = trimTrailingPeriods(firstNonEmptyString(
    latestFuturesDemo.posture?.whyNotTrading?.[0],
    latestFuturesDemo.posture?.selectedExecutionPlan?.reason,
    Array.isArray(latestFuturesDemo.execution.blockers) ? latestFuturesDemo.execution.blockers[0] : null
  ));
  const evidenceMode = latestFuturesDemo.posture?.evidencePlan?.mode;
  const shadowObserveCount = Array.isArray(latestFuturesDemo.sampling?.lanes)
    ? latestFuturesDemo.sampling.lanes.filter((lane) => lane?.action === "shadow-observe").length
    : 0;
  health.warnings.push(
    evidenceMode === "evidence-build" && shadowObserveCount > 0
      ? `Futures demo execution is correctly fail-closed while evidence is still building: ${blocker ?? "promotion remains gated"}.`
      : blocker
        ? `Futures demo execution is enabled but still blocked: ${blocker}`
        : "Futures demo execution is enabled, but the latest run did not submit any lane."
  );
}
if (latestResearcherReport?.status === "degraded") {
  health.warnings.push(`Researcher scheduler is degraded: ${latestResearcherReport.nextAction ?? "latest run needs attention"}`);
}
if (latestStrategyLab?.status === "failed") {
  health.warnings.push(`Strategy lab failed: ${latestStrategyLab.error ?? "latest scheduled run did not complete"}`);
}
if (latestStrategyLab?.liveReadiness?.status === "failed") {
  health.warnings.push(`Strategy lab live-readiness child failed: ${latestStrategyLab.liveReadiness.error ?? "latest child run did not complete"}`);
}
if (latestStrategyLab?.rollingOos?.status === "failed") {
  health.warnings.push(`Strategy lab rolling-OOS child failed: ${latestStrategyLab.rollingOos.error ?? "latest child run did not complete"}`);
}
const rollingOosRequestedWindows = Number(latestStrategyLab?.rollingOos?.config?.windows ?? 0);
const rollingOosEvaluatedWindows = Number(latestStrategyLab?.rollingOos?.aggregate?.windowsEvaluated ?? latestStrategyLab?.rollingOos?.windows?.length ?? 0);
if (
  Number.isFinite(rollingOosRequestedWindows)
  && Number.isFinite(rollingOosEvaluatedWindows)
  && rollingOosRequestedWindows > 0
  && rollingOosEvaluatedWindows > 0
  && rollingOosEvaluatedWindows < rollingOosRequestedWindows
) {
  health.warnings.push(`Strategy lab OOS evidence is thin: evaluated ${rollingOosEvaluatedWindows}/${rollingOosRequestedWindows} requested rolling window(s).`);
}
if (typeof health.runtime.researcherSchedulerAgeSeconds === "number" && health.runtime.researcherSchedulerAgeSeconds > 10800) {
  health.warnings.push(`Researcher scheduler artifact is stale (${health.runtime.researcherSchedulerAgeSeconds}s old).`);
}
if (typeof health.runtime.strategyLabAgeSeconds === "number" && health.runtime.strategyLabAgeSeconds > 21600) {
  health.warnings.push(`Strategy lab artifact is stale (${health.runtime.strategyLabAgeSeconds}s old).`);
}
if (typeof health.runtime.openJarvisBoardAgeSeconds === "number" && health.runtime.openJarvisBoardAgeSeconds > 21600) {
  health.warnings.push(`OpenJarvis board artifact is stale (${health.runtime.openJarvisBoardAgeSeconds}s old).`);
}
for (const warning of health.runtime.doctorWarnings) {
  health.warnings.push(`doctor: ${warning}`);
}
if (health.runtime.disk && health.runtime.disk.usedPct >= 88) {
  health.warnings.push(
    `Disk is ${health.runtime.disk.usedPct}% used with ${health.runtime.disk.freeGb}GB free. Keep logs/data bounded before running heavier strategy or research jobs.`
  );
}
if (health.runtime.logRetention.logDirSizeMb > health.runtime.logRetention.logMaxMb * 4) {
  health.warnings.push(
    `Bill log directory is ${health.runtime.logRetention.logDirSizeMb}MB. Rotation is configured, but old runtime logs may still need compaction.`
  );
}

const doctorRuntime = health.runtime.doctorRuntime ?? {};
const billLoops = doctorRuntime.billLoops ?? {};
const topstep = doctorRuntime.topstep ?? {};
const strategies = doctorRuntime.strategies ?? {};
const sources = doctorRuntime.sources ?? {};
const tracks = doctorRuntime.tracks ?? {};

if (!health.runtime.secureEnvFilePresent) {
  health.recommendations.push("Create a secure env file at ~/Library/Application Support/AgentPay/bill/bill.env before using venue adapters.");
}

if (health.runtime.disk && health.runtime.disk.freeGb < 30) {
  health.recommendations.push("Free disk headroom or reduce data/log retention before adding LiveKit, Paperclip, or more heavy research workers.");
}

if (health.commands.predictionReport.ok === false) {
  health.recommendations.push("Prediction journal is missing or unreadable. Run a prediction scan before relying on report automation.");
}

if (runDeepHealth && health.commands.typecheck.ok === false) {
  health.recommendations.push(`Current repo typecheck is failing: ${health.commands.typecheck.error}`);
}

if (runDeepHealth && health.commands.esbuildOpportunityBundle.ok === false) {
  health.recommendations.push(`Current esbuild bundle smoke is failing: ${health.commands.esbuildOpportunityBundle.error}`);
}

if (process.env.BILL_ENABLE_PREDICTION_COLLECT === "true" && !health.runtime.predictionSnapshotPresent) {
  health.recommendations.push("Prediction collection is enabled but the current snapshot artifact is missing.");
}

if (billLoops.predictionCollectEnabled === false) {
  health.recommendations.push("Enable BILL_ENABLE_PREDICTION_COLLECT=true so Bill keeps refreshing live venue data.");
}

if (billLoops.predictionScanEnabled === false) {
  health.recommendations.push("Enable BILL_ENABLE_PREDICTION_SCAN=true so collected prediction data is scored instead of just stored.");
}

if (billLoops.predictionCopyDemoEnabled === false) {
  health.recommendations.push("Enable BILL_ENABLE_PREDICTION_COPY_DEMO=true so Bill keeps tracking outsized-return prediction wallets and shadow copy ideas.");
}

if (billLoops.predictionCopyDemoEnabled === true && !health.runtime.predictionCopyDemoPresent) {
  health.recommendations.push("Prediction copy-demo lane is enabled but the latest copy-demo artifact is missing.");
}

if (process.env.BILL_ENABLE_PREDICTION_TRAINING !== "false" && !health.runtime.predictionLearnedPolicyPresent) {
  health.recommendations.push("Prediction training is enabled but the learned scan policy artifact is missing.");
}

if (billLoops.researchCollectEnabled === false) {
  health.recommendations.push("Enable BILL_ENABLE_RESEARCH_COLLECT=true so Bill refreshes the broader futures/options/macro research catalog.");
}

if (process.env.BILL_ENABLE_RESEARCH_COLLECT === "true" && !health.runtime.researchCatalogPresent) {
  health.recommendations.push("Research collection is enabled but the research catalog artifact is missing.");
}
if (process.env.BILL_ENABLE_RESEARCHER_RUN !== "false" && !health.runtime.researcherSchedulerLatestPresent) {
  health.recommendations.push("Researcher scheduler is enabled but its latest artifact is missing. Run bill-researcher-run-scheduled or reload launchd.");
}
if (process.env.BILL_ENABLE_STRATEGY_LAB !== "false" && !health.runtime.strategyLabLatestPresent) {
  health.recommendations.push("Strategy lab is enabled but its latest artifact is missing. Run bill-strategy-lab-scheduled or reload launchd.");
}
if (!health.runtime.openJarvisBoardMarkdownPresent) {
  health.recommendations.push("OpenJarvis board artifact is missing. Run openjarvis-board so the founder control surface matches runtime reality.");
}

if (Array.isArray(tracks.executionTracks) && tracks.executionTracks.includes("futures-core") && billLoops.paperLoopEnabled === false) {
  health.recommendations.push("Enable BILL_ENABLE_PAPER_LOOP=true so the futures execution track runs its scheduled demo/shadow loop.");
}
if (Array.isArray(tracks.executionTracks) && tracks.executionTracks.includes("futures-core") && billLoops.paperLoopEnabled === true && !health.runtime.futuresDemoLatestPresent) {
  health.recommendations.push("Futures paper loop is enabled but the overnight demo sample artifact is missing. Run bill-paper-loop or reload launchd.");
}
if (Array.isArray(tracks.executionTracks) && tracks.executionTracks.includes("futures-core") && billLoops.futuresDemoExecutionEnabled === false) {
  health.recommendations.push("Enable BILL_ENABLE_FUTURES_DEMO_EXECUTION=true when you are ready to test guarded ProjectX demo routing instead of shadow-only sampling.");
}
if (Array.isArray(tracks.executionTracks) && tracks.executionTracks.includes("futures-core") && topstep.readOnly === true) {
  health.recommendations.push("Futures demo routing remains blocked by RH_TOPSTEP_READ_ONLY=true. Keep it locked until you have reviewed the latest demo execution artifact and are ready to route to demo accounts.");
}

if (Number(strategies.enabled?.length ?? 0) < 2) {
  health.recommendations.push("Configure RH_ENABLED_STRATEGIES with multiple futures strategies so Bill is not stuck on a single lane.");
}

if (topstep.demoOnly === true && topstep.demoAccountLockSatisfied === false) {
  health.recommendations.push("Topstep demo-only mode is active but the allowed demo account lock is incomplete. Configure RH_TOPSTEP_ALLOWED_ACCOUNT_ID or RH_TOPSTEP_ALLOWED_ACCOUNT_IDS.");
}

if (Number(topstep.allowedDemoAccounts?.length ?? 0) < 4) {
  health.recommendations.push("Fewer than four Topstep demo accounts are configured. Add all demo account ids so Bill can split strategy testing across them.");
}
if (typeof topstep.baseUrl === "string" && topstep.baseUrl.length > 0 && !topstep.baseUrl.includes("api.thefuturesdesk.projectx.com")) {
  health.recommendations.push(`Topstep/ProjectX base URL should target the API gateway. Current normalized value is ${topstep.baseUrl}.`);
}

if (Array.isArray(sources.missingForActiveTracks) && sources.missingForActiveTracks.length > 0) {
  health.recommendations.push(`Active-track data sources still need configuration: ${sources.missingForActiveTracks.join(", ")}.`);
}

if (!health.runtime.trackPolicyPresent || !health.runtime.toolRegistryPresent || !health.runtime.sourceCatalogPresent) {
  health.recommendations.push("Track policy, tool registry, or source catalog artifacts are missing. Run Bill research collection to refresh them.");
}

if (!health.runtime.promotionStatePresent) {
  health.recommendations.push("Promotion state is missing. Run a Bill prediction cycle or 'promotion-review' to refresh the promotion ladder state.");
}

const committeeVotes = latestReview?.topCandidate?.committee?.votes ?? [];
const contractApprove = Array.isArray(committeeVotes) && committeeVotes.some((vote) => vote.analyst === "contract-analyst" && vote.stance === "approve");
const edgeReject = Array.isArray(committeeVotes) && committeeVotes.some((vote) => vote.analyst === "edge-analyst" && vote.stance === "reject");
const riskReject = Array.isArray(committeeVotes) && committeeVotes.some((vote) => vote.analyst === "risk-manager" && vote.stance === "reject");
if (contractApprove && (edgeReject || riskReject)) {
  const shortfall = Number(latestReview?.topCandidate?.edgeShortfallPct ?? 0);
  const gross = Number(latestReview?.topCandidate?.grossEdgePct ?? 0);
  const drag = Number(latestReview?.topCandidate?.feeDragPct ?? 0);
  health.recommendations.push(
    shortfall > 0
      ? `Prediction lane has a structurally real cross-venue watch, but economics still fail after costs. Current gross edge is ${gross}% versus ${drag}% cost drag, so Bill needs about ${shortfall}% more gross dislocation before paper deployment.`
      : "Prediction lane has a structurally real cross-venue watch, but economics still fail after costs. Focus on spread capture and venue dislocation, not matcher looseness."
  );
}

if (latestCopyDemo?.actionCounts?.["shadow-buy"] > 0) {
  const topIdea = Array.isArray(latestCopyDemo.ideas) ? latestCopyDemo.ideas[0] : null;
  health.recommendations.push(
    topIdea
      ? `Copy-demo lane has ${latestCopyDemo.actionCounts["shadow-buy"]} shadow-buy idea(s). Top idea is ${topIdea.slug} ${topIdea.outcome} with ${topIdea.supporterCount} leader supporters.`
      : `Copy-demo lane has ${latestCopyDemo.actionCounts["shadow-buy"]} shadow-buy idea(s).`
  );
} else if (latestCopyDemo) {
  const ideaCount = Array.isArray(latestCopyDemo.ideas) ? latestCopyDemo.ideas.length : 0;
  const selectedLeaders = Number(latestCopyDemo.cohort?.selectedLeaders ?? 0);
  if (ideaCount > 0) {
    const topIdea = latestCopyDemo.ideas[0];
    health.recommendations.push(
      topIdea
        ? `Copy-demo lane is watch-only. Top in-domain idea is ${topIdea.slug} ${topIdea.outcome}, but it still lacks enough consensus or live value for a shadow-buy.`
        : "Copy-demo lane is watch-only. In-domain consensus exists, but nothing is actionable yet."
    );
  } else if (selectedLeaders === 0) {
    health.recommendations.push("Copy-demo lane is correctly fail-closed: there are no active founder-approved leader positions worth shadowing right now.");
  }
}

if (latestFuturesDemo?.posture?.selectedProfileId) {
  const selectedProfile = latestFuturesDemo.posture.selectedProfileId;
  const preferredSymbols = Array.isArray(latestFuturesDemo.posture.preferredSymbols) && latestFuturesDemo.posture.preferredSymbols.length > 0
    ? latestFuturesDemo.posture.preferredSymbols.join(", ")
    : null;
  const blocker = trimTrailingPeriods(firstNonEmptyString(
    latestFuturesDemo.posture?.whyNotTrading?.[0],
    latestFuturesDemo.posture?.selectedExecutionPlan?.reason
  ));
  health.recommendations.push(
    `Futures profile focus is ${selectedProfile}${preferredSymbols ? ` on ${preferredSymbols}` : ""}.${blocker ? ` Current blocker: ${blocker}` : ""}`
  );

  const evidencePlan = latestFuturesDemo.posture?.evidencePlan ?? null;
  if (evidencePlan?.mode === "evidence-build") {
    const evidenceStrategies = Array.isArray(evidencePlan.focusStrategies) && evidencePlan.focusStrategies.length > 0
      ? evidencePlan.focusStrategies.join(", ")
      : "the strongest current lane";
    const evidenceSymbols = Array.isArray(evidencePlan.focusSymbols) && evidencePlan.focusSymbols.length > 0
      ? evidencePlan.focusSymbols.join(", ")
      : preferredSymbols;
    const shortfall = Number(evidencePlan.shortfallTrades ?? 0);
    health.recommendations.push(
      `Futures is in evidence-build mode. Borrow weak lanes into ${evidenceStrategies}${evidenceSymbols ? ` on ${evidenceSymbols}` : ""} until the promotion trade shortfall drops by about ${shortfall} trade(s).`
    );
  }
}
if (latestResearcherReport?.status === "degraded") {
  health.recommendations.push(
    latestResearcherReport.nextAction
      ? `Researcher lane needs cleanup before widening scope: ${latestResearcherReport.nextAction}`
      : "Researcher lane is degraded; fix failing targets before treating it as a healthy 24/7 research loop."
  );
}
if (latestStrategyLab?.mode === "light" || latestStrategyLab?.mode === "full") {
  health.recommendations.push(`Strategy lab is running in ${latestStrategyLab.mode} mode on ${latestStrategyLab.csvPath ?? "the default futures dataset"}. Keep it read-only and use its output to tighten OOS discipline, not to auto-promote execution.`);
  if (
    Number.isFinite(rollingOosRequestedWindows)
    && Number.isFinite(rollingOosEvaluatedWindows)
    && rollingOosRequestedWindows > 0
    && rollingOosEvaluatedWindows > 0
    && rollingOosEvaluatedWindows < rollingOosRequestedWindows
  ) {
    const trainDays = Number(latestStrategyLab.rollingOos?.config?.minTrainDays ?? 20);
    const testDays = Number(latestStrategyLab.rollingOos?.config?.testDays ?? 5);
    const embargoDays = Number(latestStrategyLab.rollingOos?.config?.embargoDays ?? 1);
    const roughDaysNeeded = rollingOosRequestedWindows * testDays + trainDays + embargoDays;
    health.recommendations.push(`Do not loosen futures gates for the green one-window result; extend ${latestStrategyLab.oosCsvPath ?? "the OOS dataset"} toward roughly ${roughDaysNeeded}+ distinct trading days so ${rollingOosRequestedWindows} independent ${trainDays}/${testDays}/${embargoDays} rolling window(s) can validate the current lane.`);
  }
}

const rendered = JSON.stringify(health, null, 2);
writeFileSync(latestHealthPath, `${rendered}\n`);
console.log(rendered);

if (health.commands.doctor?.ok === false || health.commands.killSwitch?.ok === false) {
  process.exit(1);
}
