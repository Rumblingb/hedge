import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../../..");
const tsxPath = path.join(repoRoot, "node_modules/.bin/tsx");
const logDir = path.join(repoRoot, ".rumbling-hedge/logs");
const envPath = path.join(repoRoot, ".env");
const secureEnvPath = path.join(os.homedir(), "Library/Application Support/AgentPay/bill/bill.env");
const packageLockPath = path.join(repoRoot, "package-lock.json");
const predictionJournalPath = path.join(repoRoot, "journals/prediction-opportunities.jsonl");
const predictionSnapshotPath = path.join(repoRoot, process.env.BILL_PREDICTION_COLLECT_OUTPUT_PATH ?? "data/prediction/polymarket-live-snapshot.json");
const predictionCycleHistoryPath = path.join(repoRoot, process.env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl");
const predictionLearningHistoryPath = path.join(repoRoot, process.env.BILL_PREDICTION_LEARNING_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-learning-history.jsonl");
const promotionStatePath = path.join(repoRoot, process.env.BILL_PROMOTION_STATE_PATH ?? ".rumbling-hedge/state/promotion-state.json");
const predictionReviewPath = path.join(repoRoot, process.env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
const predictionLearningStatePath = path.join(repoRoot, process.env.BILL_PREDICTION_LEARNING_STATE_PATH ?? ".rumbling-hedge/state/prediction-learning.latest.json");
const predictionLearnedPolicyPath = path.join(repoRoot, process.env.BILL_PREDICTION_LEARNED_POLICY_PATH ?? ".rumbling-hedge/state/prediction-learned-policy.json");
const predictionTrainingSetPath = path.join(repoRoot, process.env.BILL_PREDICTION_TRAINING_SET_PATH ?? ".rumbling-hedge/research/prediction-training-set.json");
const researchCatalogPath = path.join(repoRoot, process.env.BILL_RESEARCH_CATALOG_PATH ?? ".rumbling-hedge/research/catalog.json");
const trackPolicyPath = path.join(repoRoot, ".rumbling-hedge/research/track-policy.json");
const toolRegistryPath = path.join(repoRoot, ".rumbling-hedge/research/tool-registry.json");
const sourceCatalogPath = path.join(repoRoot, ".rumbling-hedge/research/source-catalog.json");
const latestHealthPath = path.join(logDir, "bill-health.latest.json");

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
    dirty: run("git", ["status", "--porcelain"]).length > 0,
    status: run("git", ["status", "--short"]).split("\n").filter(Boolean)
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
    predictionLearningStatePath,
    predictionLearningStatePresent: existsSync(predictionLearningStatePath),
    predictionLearnedPolicyPath,
    predictionLearnedPolicyPresent: existsSync(predictionLearnedPolicyPath),
    predictionTrainingSetPath,
    predictionTrainingSetPresent: existsSync(predictionTrainingSetPath),
    researchCatalogPath,
    researchCatalogPresent: existsSync(researchCatalogPath),
    trackPolicyPath,
    trackPolicyPresent: existsSync(trackPolicyPath),
    toolRegistryPath,
    toolRegistryPresent: existsSync(toolRegistryPath),
    sourceCatalogPath,
    sourceCatalogPresent: existsSync(sourceCatalogPath)
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
health.commands.costProfile = tryRun(process.execPath, ["ops/mac-mini/scripts/cost-profile.mjs"]);
health.commands.researchReport = tryRun(tsxPath, ["src/cli.ts", "research-agent-report"]);
health.runtime.predictionJournalPresent = existsSync(predictionJournalPath);
health.runtime.predictionSnapshotPresent = existsSync(predictionSnapshotPath);
health.runtime.predictionSnapshotPath = predictionSnapshotPath;
health.runtime.latestPredictionCycle = readLatestJsonlEntry(predictionCycleHistoryPath);
health.runtime.doctorWarnings = Array.isArray(health.commands.doctor?.warnings)
  ? health.commands.doctor.warnings
  : [];
health.runtime.doctorRuntime = health.commands.doctor?.runtime ?? null;

const venueCounts = health.runtime.latestPredictionCycle?.collect?.venueCounts ?? {};
if (Object.keys(venueCounts).length < 2) {
  health.warnings.push(`Combined prediction feed collapsed to ${JSON.stringify(venueCounts)}.`);
}
if ((health.runtime.latestPredictionCycle?.scan?.counts?.watch ?? 0) === 0 && (health.runtime.latestPredictionCycle?.scan?.counts?.["paper-trade"] ?? 0) === 0) {
  health.warnings.push("Latest Bill cycle has no watch or paper-trade candidates.");
}
for (const warning of health.runtime.doctorWarnings) {
  health.warnings.push(`doctor: ${warning}`);
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

if (health.commands.predictionReport.ok === false) {
  health.recommendations.push("Prediction journal is missing or unreadable. Run a prediction scan before relying on report automation.");
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

if (process.env.BILL_ENABLE_PREDICTION_TRAINING !== "false" && !health.runtime.predictionLearnedPolicyPresent) {
  health.recommendations.push("Prediction training is enabled but the learned scan policy artifact is missing.");
}

if (billLoops.researchCollectEnabled === false) {
  health.recommendations.push("Enable BILL_ENABLE_RESEARCH_COLLECT=true so Bill refreshes the broader futures/options/macro research catalog.");
}

if (process.env.BILL_ENABLE_RESEARCH_COLLECT === "true" && !health.runtime.researchCatalogPresent) {
  health.recommendations.push("Research collection is enabled but the research catalog artifact is missing.");
}

if (Array.isArray(tracks.executionTracks) && tracks.executionTracks.includes("futures-core") && billLoops.paperLoopEnabled === false) {
  health.recommendations.push("Enable BILL_ENABLE_PAPER_LOOP=true so the futures execution track runs its scheduled demo/shadow loop.");
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

if (Array.isArray(sources.missingForActiveTracks) && sources.missingForActiveTracks.length > 0) {
  health.recommendations.push(`Active-track data sources still need configuration: ${sources.missingForActiveTracks.join(", ")}.`);
}

if (!health.runtime.trackPolicyPresent || !health.runtime.toolRegistryPresent || !health.runtime.sourceCatalogPresent) {
  health.recommendations.push("Track policy, tool registry, or source catalog artifacts are missing. Run Bill research collection to refresh them.");
}

if (!health.runtime.promotionStatePresent) {
  health.recommendations.push("Promotion state is missing. Run a Bill prediction cycle or 'promotion-review' to refresh the promotion ladder state.");
}

const rendered = JSON.stringify(health, null, 2);
writeFileSync(latestHealthPath, `${rendered}\n`);
console.log(rendered);

if (health.commands.doctor?.ok === false || health.commands.killSwitch?.ok === false) {
  process.exit(1);
}
