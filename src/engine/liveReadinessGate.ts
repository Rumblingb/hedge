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
  const topstepMonitor = await readJsonSafe<any>(resolve(stateDir, "topstep-100k-monitor.latest.json"));
  const brokerReconciliation = await readJsonSafe<any>(resolve(stateDir, "topstep-broker-reconciliation.latest.json"));
  const dataFreshness = await readJsonSafe<any>(resolve(stateDir, "data-freshness-gate.latest.json"));
  const futuresCostSlippage = await readJsonSafe<any>(resolve(stateDir, "futures-cost-slippage-gate.latest.json"));
  const predictionReview = await readJsonSafe<any>(resolve(stateDir, "prediction-review.latest.json"));
  const predictionPromotion = await readJsonSafe<any>(resolve(stateDir, "promotion-state.json"));
  const polymarketClobEdge = await readJsonSafe<any>(resolve(stateDir, "polymarket-clob-edge-gate.latest.json"));
  const predictionResolvedJoin = await readJsonSafe<any>(resolve(stateDir, "prediction-resolved-outcome-join.latest.json"));
  const signalQuality = await readJsonSafe<any>(resolve(stateDir, "signal-quality-advisor.latest.json"));
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
  const dataFreshnessChecks = Array.isArray(dataFreshness?.checks) ? dataFreshness.checks : [];
  const dataFreshnessPassed = dataFreshness?.verdict === "PASS"
    && dataFreshness?.action === "allow_trades"
    && dataFreshnessChecks.length > 0
    && dataFreshnessChecks.every((item: any) => item?.status === "PASS");
  const dataFreshnessSummary = dataFreshness
    ? dataFreshnessPassed
      ? `futures realtime data is fresh: ${dataFreshnessChecks.map((item: any) => `${item.symbol}:${item.source}`).join(", ")}`
      : `futures realtime data is not execution-grade: verdict=${dataFreshness.verdict ?? "missing"} action=${dataFreshness.action ?? "missing"}`
    : "futures realtime data freshness gate is missing";
  const costSlippageBacktrader = futuresCostSlippage?.backtrader ?? {};
  const costSlippageVolOos = futuresCostSlippage?.volRegimeOos ?? {};
  const costSlippageVolSurvivors = Number(costSlippageVolOos?.survivorCount ?? 0);
  const costSlippagePassed = Boolean(futuresCostSlippage)
    && futuresCostSlippage?.writesOrders === false
    && costSlippageVolSurvivors > 0;
  const costSlippageSummary = futuresCostSlippage
    ? costSlippagePassed
      ? `futures cost/slippage gate has ${costSlippageVolSurvivors} OOS survivor(s)`
      : `futures cost/slippage gate is not deployable: backtrader survivors=${costSlippageBacktrader?.survivorCount ?? "missing"} volOos survivors=${costSlippageVolSurvivors}`
    : "futures cost/slippage gate is missing";
  const predictionLiveEvidenceReady = predictionReview?.readyForPaper === true
    && (predictionPromotion?.currentStage === "live" || predictionPromotion?.recommendedStage === "live")
    && polymarketClobEdge?.writesOrders === false
    && polymarketClobEdge?.readyForPaper === true
    && predictionResolvedJoin?.writesOrders === false
    && predictionResolvedJoin?.readyForPaper === true;
  const predictionLiveEvidencePassed = autonomy.paperGates.liveTradingDisabled || predictionLiveEvidenceReady;
  const predictionLiveEvidenceSummary = autonomy.paperGates.liveTradingDisabled
    ? "live prediction execution is disabled; prediction evidence remains research-only"
    : predictionLiveEvidenceReady
      ? "prediction live evidence gates are ready"
      : [
          "prediction evidence is not live-ready:",
          `reviewReady=${predictionReview?.readyForPaper === true}`,
          `promotion=${predictionPromotion?.currentStage ?? "missing"}/${predictionPromotion?.recommendedStage ?? "missing"}`,
          `clobReady=${polymarketClobEdge?.readyForPaper === true}`,
          `resolvedReady=${predictionResolvedJoin?.readyForPaper === true}`
        ].join(" ");
  const signalQualityBlockers = Array.isArray(signalQuality?.blockers) ? signalQuality.blockers.map(String).filter(Boolean) : [];
  const signalQualityPassed = Boolean(signalQuality)
    && signalQuality?.writesOrders === false
    && signalQualityBlockers.length === 0;
  const signalQualitySummary = signalQuality
    ? signalQualityPassed
      ? `signal quality advisor clean: rating=${signalQuality.overallRating ?? "missing"}/10`
      : `signal quality advisor blocked: rating=${signalQuality.overallRating ?? "missing"}/10 blockers=${signalQualityBlockers.join("; ") || "missing"}`
    : "signal quality advisor artifact is missing";
  const monitorHardBlockers = Array.isArray(topstepMonitor?.hard_blockers)
    ? topstepMonitor.hard_blockers.map(String).filter(Boolean)
    : [];
  const monitorWarnings = Array.isArray(topstepMonitor?.warnings)
    ? topstepMonitor.warnings.map(String).filter(Boolean)
    : [];
  const brokerSnapshot = topstepMonitor?.broker_reconciliation ?? brokerReconciliation ?? {};
  const openPositions = Number(brokerSnapshot?.open_positions ?? 0);
  const brokerFlat = brokerSnapshot?.broker_flat;
  const topstepMonitorPassed = Boolean(topstepMonitor)
    && topstepMonitor?.status === "OK"
    && monitorHardBlockers.length === 0
    && monitorWarnings.length === 0
    && brokerFlat !== false
    && openPositions === 0;
  const topstepMonitorSummary = topstepMonitor
    ? topstepMonitorPassed
      ? "Topstep monitor is OK and broker reconciliation is flat"
      : [
          `Topstep monitor is not clear: status=${topstepMonitor.status ?? "missing"}`,
          monitorHardBlockers.length ? `hardBlockers=${monitorHardBlockers.join("; ")}` : "",
          monitorWarnings.length ? `warnings=${monitorWarnings.join("; ")}` : "",
          brokerFlat === false ? "brokerFlat=false" : "",
          openPositions > 0 ? `openPositions=${openPositions}` : ""
        ].filter(Boolean).join(" ")
    : "Topstep monitor artifact is missing";

  const checks: LiveReadinessGateCheck[] = [
    check("kill-switch", !autonomy.paperGates.killSwitchActive, "blocker", autonomy.paperGates.killSwitchActive ? `kill switch is ACTIVE${autonomy.paperGates.killSwitchReason ? ` — ${autonomy.paperGates.killSwitchReason}` : ""}` : "kill switch is clear"),
    check("source-clean", !sourceDirty, "blocker", sourceDirty ? "source tree has uncommitted source changes" : "source tree is clean"),
    check("board-fresh", autonomy.artifacts.openJarvisBoard.status === "fresh", "blocker", autonomy.artifacts.openJarvisBoard.summary),
    check("health-fresh", autonomy.artifacts.health.status === "fresh", "blocker", autonomy.artifacts.health.summary),
    check("topstep-monitor-clear", topstepMonitorPassed, "blocker", topstepMonitorSummary),
    check("futures-data-fresh", dataFreshnessPassed, "blocker", dataFreshnessSummary),
    check("futures-cost-slippage-deployable", costSlippagePassed, "blocker", costSlippageSummary),
    check("signal-quality-clean", signalQualityPassed, "blocker", signalQualitySummary),
    check("prediction-live-evidence-ready", predictionLiveEvidencePassed, "blocker", predictionLiveEvidenceSummary),
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
