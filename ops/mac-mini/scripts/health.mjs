import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
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
    latestHealthPath
  },
  commands: {},
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
health.commands.costProfile = tryRun(process.execPath, ["ops/mac-mini/scripts/cost-profile.mjs"]);
health.runtime.predictionJournalPresent = existsSync(predictionJournalPath);

if (!health.runtime.secureEnvFilePresent) {
  health.recommendations.push("Create a secure env file at ~/Library/Application Support/AgentPay/bill/bill.env before using venue adapters.");
}

if (health.commands.predictionReport.ok === false) {
  health.recommendations.push("Prediction journal is missing or unreadable. Run a prediction scan before relying on report automation.");
}

const rendered = JSON.stringify(health, null, 2);
writeFileSync(latestHealthPath, `${rendered}\n`);
console.log(rendered);

if (health.commands.doctor?.ok === false || health.commands.killSwitch?.ok === false) {
  process.exit(1);
}
