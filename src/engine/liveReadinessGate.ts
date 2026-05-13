import { execFile } from "node:child_process";
import { readdir, readFile, stat, writeFile, mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { buildAutonomyStatus, type AutonomyStatus } from "./autonomyStatus.js";

const execFileAsync = promisify(execFile);

export interface LiveReadinessGateCheck {
  name: string;
  passed: boolean;
  severity: "blocker" | "warning";
  summary: string;
}

export interface LiveReadinessGateReport {
  command: "live-readiness-gate";
  generatedAt: string;
  readyForLive: boolean;
  readyForDemoExpansion: boolean;
  checks: LiveReadinessGateCheck[];
  blockers: string[];
  warnings: string[];
  autonomy: Pick<AutonomyStatus, "status" | "paperGates" | "compute" | "artifacts" | "git">;
}

export interface LiveReadinessGateOptions {
  baseDir?: string;
  outputPath?: string;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function check(name: string, passed: boolean, severity: LiveReadinessGateCheck["severity"], summary: string): LiveReadinessGateCheck {
  return { name, passed, severity, summary };
}

function artifactTimeMs(artifact: any): number {
  const raw = artifact?.generatedAt ?? artifact?.startedAt ?? artifact?.timestamp ?? artifact?.lastRunAt;
  const parsed = Date.parse(String(raw ?? ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

async function findPathLeaks(baseDir: string): Promise<string[]> {
  const roots = ["src", "ops", "config", "package.json", "package-lock.json"];
  const matches: string[] = [];
  const legacyUserPath = "/Users/" + "baskar_viji";

  async function scan(pathname: string): Promise<void> {
    let info;
    try {
      info = await stat(pathname);
    } catch {
      return;
    }
    if (info.isDirectory()) {
      for (const entry of await readdir(pathname, { withFileTypes: true })) {
        if (entry.name === "node_modules" || entry.name === ".git") continue;
        await scan(join(pathname, entry.name));
      }
      return;
    }
    if (!info.isFile() || info.size > 1024 * 1024) return;
    const text = await readFile(pathname, "utf8").catch(() => "");
    if (text.includes(legacyUserPath)) {
      matches.push(pathname);
    }
  }

  for (const root of roots) {
    await scan(resolve(baseDir, root));
  }
  return matches;
}

async function gitSourceDirty(baseDir: string): Promise<boolean> {
  try {
    const { stdout } = await execFileAsync("git", ["status", "--porcelain=v1"], { cwd: baseDir, encoding: "utf8", timeout: 5000 });
    return stdout
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => line.slice(3).trim().replace(/^"|"$/g, ""))
      .some((path) =>
        !path.startsWith(".rumbling-hedge/")
        && !path.startsWith("data/")
        && !path.startsWith("journals/")
        && !path.endsWith(".csv")
      );
  } catch {
    return true;
  }
}

export async function buildLiveReadinessGate(options: LiveReadinessGateOptions = {}): Promise<LiveReadinessGateReport> {
  const baseDir = resolve(options.baseDir ?? process.cwd());
  const env = options.env ?? process.env;
  const generatedAt = options.now?.() ?? new Date().toISOString();
  const autonomy = await buildAutonomyStatus({ baseDir, env, now: () => generatedAt });
  const stateDir = resolve(baseDir, ".rumbling-hedge/state");
  const researchDir = resolve(baseDir, ".rumbling-hedge/research");
  const strategyFactory = await readJsonSafe<any>(resolve(stateDir, "strategy-factory.latest.json"));
  const strategyLab = await readJsonSafe<any>(resolve(stateDir, "strategy-lab.latest.json"));
  const futuresDemo = await readJsonSafe<any>(resolve(stateDir, "futures-demo.latest.json"));
  const noEdgeLedger = await readJsonSafe<any>(resolve(researchDir, "no-edge-ledger/latest.json"));
  const strategyFeed = await readJsonSafe<any>(resolve(researchDir, "researcher/strategy-feed.latest.json"));
  const pathLeaks = await findPathLeaks(baseDir);
  const sourceDirty = await gitSourceDirty(baseDir);

  const scheduledFactory = strategyLab?.strategyFactory?.gates ? strategyLab.strategyFactory : null;
  const useScheduledFactory = scheduledFactory && artifactTimeMs(strategyLab) >= artifactTimeMs(strategyFactory);
  const gates = {
    ...(strategyFactory?.gates ?? {}),
    ...(useScheduledFactory ? scheduledFactory.gates : {})
  };
  const rollingWindows = Number(gates.rollingOosWindows ?? 0);
  const minRollingWindows = Number(gates.minRollingOosWindows ?? 4);
  const deployableWindows = Number(gates.rollingOosDeployableWindows ?? 0);
  const submitted = Number(futuresDemo?.execution?.submittedCount ?? 0);
  const rejectedFallback = (futuresDemo?.execution?.submitted ?? [])
    .some((entry: any) => String(entry?.signal?.strategyId ?? entry?.strategyId ?? "").includes("demo-fallback"));
  const feedStrategies = new Set<string>((strategyFeed?.preferredStrategies ?? []).map(String));
  const blockedStrategies = new Set<string>((noEdgeLedger?.nonPromotableStrategies ?? noEdgeLedger?.blockedStrategies ?? []).map(String));
  const feedBlockedOverlap = [...feedStrategies].filter((strategy) => blockedStrategies.has(strategy));

  const checks: LiveReadinessGateCheck[] = [
    check("kill-switch", !autonomy.paperGates.killSwitchActive, "blocker", autonomy.paperGates.killSwitchActive ? `kill switch is ACTIVE${autonomy.paperGates.killSwitchReason ? ` — ${autonomy.paperGates.killSwitchReason}` : ""}` : "kill switch is clear"),
    check("source-clean", !sourceDirty, "blocker", sourceDirty ? "source tree has uncommitted source changes" : "source tree is clean"),
    check("board-fresh", autonomy.artifacts.openJarvisBoard.status === "fresh", "blocker", autonomy.artifacts.openJarvisBoard.summary),
    check("health-fresh", autonomy.artifacts.health.status === "fresh", "blocker", autonomy.artifacts.health.summary),
    check("researcher-fresh", autonomy.artifacts.researcher.status === "fresh", "blocker", autonomy.artifacts.researcher.summary),
    check("strategy-factory-present", Boolean(strategyFactory || scheduledFactory), "blocker", strategyFactory || scheduledFactory ? useScheduledFactory ? "scheduled strategy-lab factory gate exists" : "strategy factory artifact exists" : "strategy factory artifact is missing"),
    check("walkforward-deployable", gates.walkforwardDeployable === true, "blocker", gates.walkforwardDeployable === true ? "walk-forward gate passed" : "walk-forward gate is not deployable"),
    check(
      "rolling-oos-depth",
      rollingWindows >= minRollingWindows && deployableWindows >= minRollingWindows,
      "blocker",
      `rolling OOS deployable windows ${deployableWindows}/${minRollingWindows} across ${rollingWindows} evaluated`
    ),
    check("live-readiness-deployable", gates.liveReadinessDeployable === true, "blocker", gates.liveReadinessDeployable === true ? "stressed live-readiness passed" : "stressed live-readiness is not deployable"),
    check("no-edge-ledger-present", Boolean(noEdgeLedger?.count), "blocker", noEdgeLedger?.count ? `no-edge ledger has ${noEdgeLedger.count} entries` : "no-edge ledger is missing/empty"),
    check("research-feed-not-blocked", feedBlockedOverlap.length === 0, "blocker", feedBlockedOverlap.length === 0 ? "research feed does not prefer no-edge strategies" : `research feed overlaps no-edge ledger: ${feedBlockedOverlap.join(", ")}`),
    check("heavy-lock-clear", !autonomy.compute.heavyLockPresent || (autonomy.compute.heavyLockAgeSeconds ?? 0) < 30 * 60, "blocker", autonomy.compute.heavyLockPresent ? `heavy lock age ${autonomy.compute.heavyLockAgeSeconds}s` : "heavy slot is clear"),
    check("old-user-path-clean", pathLeaks.length === 0, "blocker", pathLeaks.length === 0 ? "no legacy-user runtime path leaks in source/ops/config" : `old user path leaks: ${pathLeaks.slice(0, 5).join(", ")}`),
    check(
      "live-routing-disabled-or-micro-sandboxed",
      autonomy.paperGates.predictionMicroLiveSandboxSafe,
      "blocker",
      autonomy.paperGates.liveTradingDisabled
        ? "live prediction execution remains disabled"
        : autonomy.paperGates.predictionMicroLiveSandboxSafe
          ? `prediction micro-live sandbox is capped at ${autonomy.paperGates.predictionLiveMaxStake}`
          : "live prediction execution is enabled outside the approved micro-live sandbox"
    ),
    check("demo-safe-envelope", autonomy.paperGates.futuresDemoExplorationSafe, "blocker", autonomy.paperGates.futuresDemoExplorationSafe ? "futures demo is disabled or capped to safe envelope" : "futures demo routing is outside safe envelope"),
    check("demo-no-fallback-submit", !rejectedFallback, "blocker", rejectedFallback ? "demo fallback signal was submitted" : `latest demo submitted ${submitted} order(s), no fallback submissions detected`)
  ];

  const blockers = checks.filter((item) => !item.passed && item.severity === "blocker").map((item) => item.summary);
  const warnings = [
    ...checks.filter((item) => !item.passed && item.severity === "warning").map((item) => item.summary),
    ...autonomy.warnings.filter((warning) => !blockers.includes(warning))
  ];

  return {
    command: "live-readiness-gate",
    generatedAt,
    readyForLive: blockers.length === 0,
    readyForDemoExpansion: blockers.length === 0,
    checks,
    blockers,
    warnings: Array.from(new Set(warnings)),
    autonomy: {
      status: autonomy.status,
      paperGates: autonomy.paperGates,
      compute: autonomy.compute,
      artifacts: autonomy.artifacts,
      git: autonomy.git
    }
  };
}

export async function writeLiveReadinessGate(options: LiveReadinessGateOptions = {}): Promise<LiveReadinessGateReport> {
  const report = await buildLiveReadinessGate(options);
  const outputPath = resolve(options.baseDir ?? process.cwd(), options.outputPath ?? ".rumbling-hedge/state/live-readiness-gate.latest.json");
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
