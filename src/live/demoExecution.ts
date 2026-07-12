import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { execFileSync } from "node:child_process";
import { getClassification, SUPPORTED_STRATEGY_IDS, type Bar, type LabConfig, type TradeRecord, type StrategySignal } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { applyTradeToRiskState, createInitialRiskState, evaluateSignalGuardrails } from "../risk/guardrails.js";
import { chicagoDateKey } from "../utils/time.js";
import { isDemoAccountLockSatisfied } from "./demoAccounts.js";
import type { DemoStrategySampleSnapshot } from "./demoSampling.js";
import { buildStrategyCatalog } from "../strategies/wctcEnsemble.js";
import { classifyRegime, STRATEGY_SESSION_PREFERENCE } from "../engine/strategyFusion.js";
import type { ExecutionReceipt, ExecutionAdapter } from "../adapters/topstep/topstepAdapter.js";
import { ProjectXLiveAdapter } from "../adapters/projectx/projectxAdapter.js";
import { loadNQChallengeState, saveNQChallengeStateStrict } from "../risk/nqChallengeState.js";
import { DailyLock, chicagoToday } from "../risk/dailyLock.js";
import type { NQChallengeState } from "../risk/nqChallengeEngine.js";

const STATE_DIR = join(process.cwd(), ".rumbling-hedge/state");

export interface DemoExecutionSignalSummary {
  symbol: string;
  strategyId: string;
  side: "long" | "short";
  entry: number;
  stop: number;
  target: number;
  rr: number;
  confidence: number;
  contracts: number;
  timestamp: string;
}

export interface DemoExecutionLaneResult {
  accountId: string;
  label: string | null;
  slot: number;
  primaryStrategy: string | null;
  focusSymbol: string;
  status: "submitted" | "skipped";
  reason: string;
  signal: DemoExecutionSignalSummary | null;
  receipt?: ExecutionReceipt;
}

export interface FuturesDemoExecutionTelemetry {
  laneCount: number;
  signalCount: number;
  noSignalCount: number;
  routedBlockerCount: number;
  byStrategy: Record<string, {
    lanes: number;
    signals: number;
    noSignals: number;
    submitted: number;
    skipped: number;
  }>;
}

export interface FuturesDemoExecutionReport {
  enabled: boolean;
  mode: "demo-route" | "shadow-only";
  blockers: string[];
  submittedCount: number;
  skippedCount: number;
  maxOrdersPerRun: number;
  telemetry: FuturesDemoExecutionTelemetry;
  lanes: DemoExecutionLaneResult[];
}

export interface ExecuteFuturesDemoLanesOptions {
  bars: Bar[];
  config: LabConfig;
  newsGate: NewsGate;
  trades: TradeRecord[];
  sampleSnapshot: DemoStrategySampleSnapshot;
  killSwitchActive: boolean;
  enabled: boolean;
  maxOrdersPerRun: number;
  preflightBlockers?: string[];
  adapterFactory?: (config: LabConfig["live"]) => ExecutionAdapter;
  nqChallengeState?: NQChallengeState | null;
}

function buildAdapter(config: LabConfig["live"]): ExecutionAdapter {
  return new ProjectXLiveAdapter(config);
}

function buildDailyRiskState(trades: TradeRecord[], chicagoDay: string) {
  let state = createInitialRiskState();

  for (const trade of trades) {
    if (chicagoDateKey(trade.exitTs) !== chicagoDay) {
      continue;
    }
    state = applyTradeToRiskState(state, trade.netRMultiple);
  }

  return state;
}

function runtimeRiskPolicyBlockers(env: NodeJS.ProcessEnv = process.env): string[] {
  const maxTrades = Number(env.RH_MAX_TRADES_PER_DAY ?? "1");
  const maxDailyLoss = Number(env.RH_MAX_DAILY_LOSS_R ?? "1");
  const maxConsecutiveLosses = Number(env.RH_MAX_CONSECUTIVE_LOSSES ?? "1");
  const approvalId = env.BILL_LIVE_APPROVAL_ID?.trim();
  const demoApprovalId = env.BILL_FUTURES_DEMO_APPROVAL_ID?.trim();
  const demoApproved = env.BILL_ENABLE_FUTURES_DEMO_EXECUTION === "true" && env.RH_TOPSTEP_DEMO_ONLY !== "false" && Boolean(demoApprovalId);
  const maxTradesThreshold = demoApproved ? 4 : 1;
  const maxDailyLossThreshold = demoApproved ? 2 : 1;
  const maxConsecutiveLossThreshold = demoApproved ? 2 : 1;
  return [
    ...(env.RH_LIVE_EXECUTION_ENABLED === "true" && !approvalId && !demoApproved ? ["risk-policy:futuresLiveApproval"] : []),
    ...(env.BILL_ENABLE_FUTURES_DEMO_EXECUTION === "true" && env.RH_TOPSTEP_READ_ONLY !== "true" && !approvalId && !demoApproved ? ["risk-policy:futuresDemoReadOnly"] : []),
    ...(Number.isFinite(maxTrades) && maxTrades > maxTradesThreshold ? ["risk-policy:starterMaxTradesPerDay"] : []),
    ...(Number.isFinite(maxDailyLoss) && maxDailyLoss > maxDailyLossThreshold ? ["risk-policy:starterMaxDailyLossR"] : []),
    ...(Number.isFinite(maxConsecutiveLosses) && maxConsecutiveLosses > maxConsecutiveLossThreshold ? ["risk-policy:starterMaxConsecutiveLosses"] : [])
  ];
}

function executionClassificationBlocker(strategyId: string): string | null {
  if (!(SUPPORTED_STRATEGY_IDS as readonly string[]).includes(strategyId)) {
    return `strategy classification: ${strategyId} is not a registered executable strategy`;
  }
  const classification = getClassification(strategyId as (typeof SUPPORTED_STRATEGY_IDS)[number]);
  if (classification !== "GOLD" && classification !== "SILVER") {
    return `strategy classification: ${strategyId} is ${classification}, not executable`;
  }
  return null;
}

function buildLatestContext(args: {
  bars: Bar[];
  symbol: string;
  config: LabConfig;
  newsGate: NewsGate;
  dailyTradeCount: number;
}) {
  const symbolBars = args.bars
    .filter((bar) => bar.symbol === args.symbol)
    .sort((left, right) => left.ts.localeCompare(right.ts));

  const currentBar = symbolBars.at(-1);
  if (!currentBar) {
    return null;
  }

  const history = symbolBars.slice(0, -1);
  const currentDay = chicagoDateKey(currentBar.ts);
  const sessionHistory = history.filter((bar) => chicagoDateKey(bar.ts) === currentDay);
  const news = args.newsGate.score({
    symbol: args.symbol,
    ts: currentBar.ts,
    bar: currentBar
  });

  return {
    symbol: args.symbol,
    bar: currentBar,
    history,
    sessionHistory,
    config: args.config,
    news,
    dailyTradeCount: args.dailyTradeCount
  };
}

function summarizeSignal(args: {
  timestamp: string;
  signal: StrategySignal;
}): DemoExecutionSignalSummary {
  return {
    symbol: args.signal.symbol,
    strategyId: args.signal.strategyId,
    side: args.signal.side,
    entry: Number(args.signal.entry.toFixed(4)),
    stop: Number(args.signal.stop.toFixed(4)),
    target: Number(args.signal.target.toFixed(4)),
    rr: Number(args.signal.rr.toFixed(4)),
    confidence: Number(args.signal.confidence.toFixed(4)),
    contracts: args.signal.contracts,
    timestamp: args.timestamp
  };
}

function summarizeTelemetry(args: {
  blockers: string[];
  lanes: DemoExecutionLaneResult[];
}): FuturesDemoExecutionTelemetry {
  const byStrategy: FuturesDemoExecutionTelemetry["byStrategy"] = {};

  for (const lane of args.lanes) {
    const strategyId = lane.primaryStrategy ?? "standby";
    const current = byStrategy[strategyId] ?? {
      lanes: 0,
      signals: 0,
      noSignals: 0,
      submitted: 0,
      skipped: 0
    };
    current.lanes += 1;
    if (lane.signal) {
      current.signals += 1;
    } else {
      current.noSignals += 1;
    }
    if (lane.status === "submitted") {
      current.submitted += 1;
    } else {
      current.skipped += 1;
    }
    byStrategy[strategyId] = current;
  }

  const signalCount = args.lanes.filter((lane) => lane.signal !== null).length;
  return {
    laneCount: args.lanes.length,
    signalCount,
    noSignalCount: args.lanes.length - signalCount,
    routedBlockerCount: args.blockers.length,
    byStrategy
  };
}

function isDemoFallbackSignal(signal: StrategySignal): boolean {
  return signal.meta?.source === "demo-fallback";
}

function readTextSafe(path: string): string {
  try {
    return existsSync(path) ? readFileSync(path, "utf8") : "";
  } catch {
    return "";
  }
}

function readJsonSafe(path: string): any {
  try {
    return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : {};
  } catch {
    return {};
  }
}

function billTradingDateKey(now = new Date(), timeZone = process.env.BILL_TRADING_TIMEZONE || "Europe/London"): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  return year && month && day ? `${year}-${month}-${day}` : now.toISOString().slice(0, 10);
}

function todayDailyPlanPath(env: NodeJS.ProcessEnv = process.env, now = new Date()): string {
  const day = billTradingDateKey(now, env.BILL_TRADING_TIMEZONE || "Europe/London");
  return env.BILL_DAILY_PLAN_PATH
    ?? `/Users/brain/Documents/memorybrain/Agent-Hermes/daily/${day}-bill-trading-plan.md`;
}

function machineControlLines(text: string): Set<string> {
  return new Set(text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
}

function numericEnv(value: string | undefined, fallback: number): number {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function demoCanaryEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.BILL_FUTURES_DEMO_CANARY_ENABLED === "true";
}

const RECONCILIATION_MAX_AGE_MINUTES = 30;

function reconciliationArtifactPath(env: NodeJS.ProcessEnv = process.env): string {
  const stateDir = env.BILL_STATE_DIR ?? STATE_DIR;
  return join(stateDir, "topstep-broker-reconciliation.latest.json");
}

function reconciliationAgeMinutes(reconciliation: any, now: Date): number {
  const ts = reconciliation?.ts;
  if (!ts) {
    return Number.POSITIVE_INFINITY;
  }
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) {
    return Number.POSITIVE_INFINITY;
  }
  return (now.getTime() - parsed.getTime()) / 60000;
}

function reconciliationStatus(reconciliation: any, now: Date): { fresh: boolean; flat: boolean; ageMinutes: number } {
  const ageMinutes = reconciliationAgeMinutes(reconciliation, now);
  const fresh = ageMinutes <= RECONCILIATION_MAX_AGE_MINUTES;
  const flat = reconciliation?.broker_flat === true;
  return { fresh, flat, ageMinutes };
}

/**
 * Attempt to refresh the broker reconciliation artifact synchronously by
 * invoking the read-only fill-check script. Never throws; on any failure the
 * caller falls back to the existing (possibly stale) artifact.
 */
function refreshReconciliationArtifact(env: NodeJS.ProcessEnv = process.env): void {
  if (env.VITEST || env.NODE_ENV === "test" || env.BILL_DISABLE_RECONCILIATION_REFRESH === "true") {
    return;
  }
  try {
    const pythonBin = env.BILL_PYTHON_BIN
      ?? join(process.cwd(), ".venv/bin/python");
    const scriptPath = env.BILL_TOPSTEP_FILL_CHECK_PATH
      ?? join(env.HOME ?? "", ".hermes/scripts/topstep_demo_fill_check.py");
    if (!existsSync(pythonBin) || !existsSync(scriptPath)) {
      return;
    }
    execFileSync(pythonBin, [scriptPath], {
      timeout: 60000,
      // The fill-check script refuses to run (and writes a blocked placeholder
      // artifact) unless the env is in the read-only safety posture, so never
      // inherit the router's live/demo routing flags for this subprocess.
      env: {
        ...env,
        RH_TOPSTEP_READ_ONLY: "true",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false",
        RH_LIVE_EXECUTION_ENABLED: "false"
      },
      stdio: "ignore"
    });
  } catch {
    // Read-only refresh attempt failed; fall back to stale-artifact handling.
  }
}

/**
 * Restart-safety gate: before routing any demo order, require a fresh,
 * broker-confirmed-flat reconciliation artifact. If the artifact is missing
 * or stale, attempt a synchronous (read-only) refresh via the fill-check
 * script before failing closed.
 */
export function reconciliationFreshnessBlockers(env: NodeJS.ProcessEnv = process.env, now = new Date()): string[] {
  const path = reconciliationArtifactPath(env);
  const expectedAccountId = env.RH_TOPSTEP_RECONCILE_ACCOUNT_ID?.trim();
  let reconciliation = readJsonSafe(path);
  let status = reconciliationStatus(reconciliation, now);

  if (!status.fresh || !status.flat) {
    refreshReconciliationArtifact(env);
    reconciliation = readJsonSafe(path);
    status = reconciliationStatus(reconciliation, now);
  }

  if (!existsSync(path) || Object.keys(reconciliation ?? {}).length === 0) {
    return ["broker reconciliation artifact is missing"];
  }
  if (!status.fresh) {
    return [`broker reconciliation artifact is stale: age=${status.ageMinutes.toFixed(1)}min (max ${RECONCILIATION_MAX_AGE_MINUTES}min)`];
  }
  if (!status.flat) {
    return ["broker reconciliation artifact does not confirm broker_flat === true"];
  }
  if (expectedAccountId && String(reconciliation?.account_id ?? "") !== expectedAccountId) {
    return [`broker reconciliation account mismatch: expected=${expectedAccountId} actual=${reconciliation?.account_id ?? "missing"}`];
  }
  return [];
}

export function demoExecutionCanaryBlockers(args: {
  env?: NodeJS.ProcessEnv;
  stateDir?: string;
  dailyControlLines?: Set<string>;
} = {}): string[] {
  const env = args.env ?? process.env;
  if (!demoCanaryEnabled(env)) {
    return ["BILL_FUTURES_DEMO_CANARY_ENABLED is not true"];
  }

  const stateDir = args.stateDir ?? env.BILL_STATE_DIR ?? STATE_DIR;
  const controlLines = args.dailyControlLines ?? machineControlLines(readTextSafe(todayDailyPlanPath(env)));
  const realtimePreflight = readJsonSafe(join(stateDir, "realtime-data-preflight.latest.json"));
  const brokerParity = readJsonSafe(join(stateDir, "futures-broker-parity-plan.latest.json"));
  const currentParity = brokerParity?.current ?? {};
  const topstep = currentParity?.topstep ?? {};
  const maxOrdersPerRun = numericEnv(env.BILL_FUTURES_DEMO_MAX_ORDERS_PER_RUN, 1);
  const maxContracts = numericEnv(env.RH_MAX_CONTRACTS, 1);

  const blockers: string[] = [];
  if (!controlLines.has("BILL_DEMO_CANARY: APPROVED")) {
    blockers.push("daily plan lacks BILL_DEMO_CANARY: APPROVED");
  }
  if (!env.BILL_FUTURES_DEMO_APPROVAL_ID?.trim()) {
    blockers.push("BILL_FUTURES_DEMO_APPROVAL_ID is required for demo canary routing");
  }
  if (!env.RH_TOPSTEP_RECONCILE_ACCOUNT_ID?.trim()) {
    blockers.push("RH_TOPSTEP_RECONCILE_ACCOUNT_ID is required for account-bound demo canary reconciliation");
  }
  if (maxOrdersPerRun > 1) {
    blockers.push("demo canary max orders per run must be <= 1");
  }
  if (maxContracts > 1) {
    blockers.push("demo canary RH_MAX_CONTRACTS must be <= 1");
  }
  if (realtimePreflight?.readyForExecutionData !== true) {
    blockers.push(`demo canary requires realtime-data-preflight readyForExecutionData=true, got ${realtimePreflight?.decision ?? "missing"}`);
  }
  if ((realtimePreflight?.blockers ?? []).length > 0) {
    blockers.push("demo canary realtime-data-preflight has blockers");
  }
  if (currentParity?.topstepBrokerLocalBarParityPassed !== true) {
    blockers.push("demo canary requires Topstep broker/local bar parity proof");
  }
  if (currentParity?.topstepRealtimeReadyForExecutionDataProof !== true) {
    blockers.push("demo canary requires Topstep realtime proof");
  }
  if (topstep?.brokerFlat !== true || Number(topstep?.openPositions ?? 0) !== 0) {
    blockers.push("demo canary requires broker flat proof from Topstep parity state");
  }
  return blockers;
}

export function demoExecutionRouteApprovalBlockers(env: NodeJS.ProcessEnv = process.env, now = new Date()): string[] {
  const stateDir = env.BILL_STATE_DIR ?? STATE_DIR;
  const dailyPlanText = readTextSafe(todayDailyPlanPath(env, now));
  const monitor = readJsonSafe(join(stateDir, "topstep-100k-monitor.latest.json"));
  const liveReadinessGate = readJsonSafe(join(stateDir, "live-readiness-gate.latest.json"));
  const blockers: string[] = [];
  let controlLines = new Set<string>();

  if (!dailyPlanText) {
    blockers.push("daily plan missing or unreadable");
  } else {
    controlLines = machineControlLines(dailyPlanText);
    if (dailyPlanText.includes("No new Bill/Hermes orders approved")) {
      blockers.push("daily plan explicitly says no new Bill/Hermes orders approved");
    }
    if (!controlLines.has("BILL_ROUTE_APPROVAL: APPROVED")) {
      blockers.push("daily plan lacks BILL_ROUTE_APPROVAL: APPROVED");
    }
    if (!controlLines.has("BROKER_RECONCILIATION: GREEN")) {
      blockers.push("daily plan lacks BROKER_RECONCILIATION: GREEN");
    }
  }

  if (monitor?.status !== "OK") {
    blockers.push(`Topstep monitor is not OK: ${monitor?.status ?? "missing"}`);
  }
  if ((monitor?.hard_blockers ?? []).length > 0) {
    blockers.push("Topstep monitor has hard blockers");
  }
  if ((monitor?.warnings ?? []).length > 0) {
    blockers.push("Topstep monitor warnings require reconciliation");
  }
  const canaryBlockers = demoCanaryEnabled(env)
    ? demoExecutionCanaryBlockers({ env, stateDir, dailyControlLines: controlLines })
    : [];
  const canaryRouteAllowed = demoCanaryEnabled(env) && canaryBlockers.length === 0;
  if (liveReadinessGate?.readyForDemoExpansion !== true && !canaryRouteAllowed) {
    blockers.push("live-readiness gate does not allow demo expansion");
  }
  if ((liveReadinessGate?.blockers ?? []).length > 0 && !canaryRouteAllowed) {
    blockers.push("live-readiness gate has blockers despite demo flag");
  }
  blockers.push(...canaryBlockers);

  return blockers;
}

export async function executeFuturesDemoLanes(
  options: ExecuteFuturesDemoLanesOptions
): Promise<FuturesDemoExecutionReport> {
  const maxOrdersPerRun = Math.max(1, options.maxOrdersPerRun);
  const blockers = [
    ...runtimeRiskPolicyBlockers(),
    ...reconciliationFreshnessBlockers(),
    ...(options.preflightBlockers ?? []),
    ...(options.enabled ? [] : ["BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true."]),
    ...(options.config.live.enabled ? [] : ["RH_LIVE_EXECUTION_ENABLED is not true."]),
    ...(options.config.live.demoOnly ? [] : ["RH_TOPSTEP_DEMO_ONLY must remain true for routed demo execution."]),
    ...(options.config.live.readOnly ? ["RH_TOPSTEP_READ_ONLY is still true."] : []),
    ...(isDemoAccountLockSatisfied(options.config.live) ? [] : ["Topstep demo account lock is incomplete or mismatched."]),
    ...(options.killSwitchActive ? ["Manual kill switch is active."] : []),
    ...(options.sampleSnapshot.laneCount > 0 ? [] : ["No demo account lanes are configured."])
  ];
  const strategyCatalog = buildStrategyCatalog();
  const adapterFactory = options.adapterFactory ?? buildAdapter;
  const routeApprovalBlockers = demoExecutionRouteApprovalBlockers();
  const routingBlockers = [...blockers, ...routeApprovalBlockers];
  const results: DemoExecutionLaneResult[] = [];
  let submittedCount = 0;

  const sampleDay = options.sampleSnapshot.lanes
    .map((lane) => buildLatestContext({
      bars: options.bars,
      symbol: lane.focusSymbol,
      config: options.config,
      newsGate: options.newsGate,
      dailyTradeCount: 0
    })?.bar.ts)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
  const tradeDay = sampleDay ? chicagoDateKey(sampleDay) : chicagoDateKey(new Date().toISOString());
  let riskState = buildDailyRiskState(options.trades, tradeDay);

  for (const lane of options.sampleSnapshot.lanes) {
    const base = {
      accountId: lane.accountId,
      label: lane.label,
      slot: lane.slot,
      primaryStrategy: lane.primaryStrategy,
      focusSymbol: lane.focusSymbol
    };

    if (!lane.primaryStrategy) {
      results.push({
        ...base,
        status: "skipped",
        reason: "lane has no assigned primary strategy",
        signal: null
      });
      continue;
    }

    const strategy = strategyCatalog[lane.primaryStrategy];
    if (!strategy) {
      results.push({
        ...base,
        status: "skipped",
        reason: `unknown strategy ${lane.primaryStrategy}`,
        signal: null
      });
      continue;
    }

    const context = buildLatestContext({
      bars: options.bars,
      symbol: lane.focusSymbol,
      config: options.config,
      newsGate: options.newsGate,
      dailyTradeCount: riskState.tradeCount
    });

    if (!context) {
      results.push({
        ...base,
        status: "skipped",
        reason: `no bar data is available for ${lane.focusSymbol}`,
        signal: null
      });
      continue;
    }

    // Hard session gate: skip strategy if current session is not in its preferred sessions
    const bars = context.history.length > 0
      ? [...context.history, context.bar]
      : [context.bar];
    const regime = classifyRegime(bars);
    const preferredSessions = STRATEGY_SESSION_PREFERENCE[lane.primaryStrategy];
    if (preferredSessions && preferredSessions.length > 0 && !preferredSessions.includes(regime.session)) {
      results.push({
        ...base,
        status: "skipped",
        reason: `session gate: ${regime.session} not in preferred [${preferredSessions.join(',')}] for ${lane.primaryStrategy}`,
        signal: null
      });
      continue;
    }

    let signal = strategy.generateSignal(context);
    
    // Demo exploration fallback: if primary strategy doesn't fire, 
    // generate a minimal signal from the latest bar for runtime learning
    if (!signal && options.config.live.demoOnly && process.env.BILL_FUTURES_DEMO_EXPLORATION_ENABLED === "true") {
      const bar = context.bar;
      const atr = (bar.high - bar.low) || (bar.close * 0.005);
      const direction = bar.close > bar.open ? "long" as const : "short" as const;
      const fallbackSignal: StrategySignal = {
        symbol: lane.focusSymbol,
        strategyId: `${lane.primaryStrategy}-demo-fallback`,
        side: direction,
        entry: bar.close,
        stop: direction === "long" ? bar.close - atr * 1.0 : bar.close + atr * 1.0,
        target: direction === "long" ? bar.close + atr * 2.5 : bar.close - atr * 2.5,
        rr: 2.5,
        confidence: 0.3,
        contracts: 1,
        maxHoldMinutes: 15,
        meta: { source: "demo-fallback", primaryStrategy: lane.primaryStrategy }
      };
      // Validate the fallback
      const fallbackValid = (direction === "long" && fallbackSignal.stop < fallbackSignal.entry && fallbackSignal.target > fallbackSignal.entry)
        || (direction === "short" && fallbackSignal.stop > fallbackSignal.entry && fallbackSignal.target < fallbackSignal.entry);
      if (fallbackValid) {
        signal = fallbackSignal;
      }
    }

    if (!signal) {
      results.push({
        ...base,
        status: "skipped",
        reason: `${lane.primaryStrategy} did not produce a routable signal on ${lane.focusSymbol}`,
        signal: null
      });
      continue;
    }

    const summarizedSignal = summarizeSignal({
      timestamp: context.bar.ts,
      signal
    });
    // ── NQ Challenge Daily Lock Gate ──────────────────────────
    // Enforces profit lock, loss lock, max trades, consecutive loss lock,
    // and news blackout windows before the signal reaches guardrails.
    const challengeState = options.nqChallengeState === undefined
      ? loadNQChallengeState()
      : options.nqChallengeState;
    if (challengeState && signal.symbol === "NQ") {
      const dailyLock = new DailyLock(challengeState.dailyLock);
      const lockDecision = dailyLock.canTrade(challengeState.phase);
      if (!lockDecision.allowed) {
        results.push({
          ...base,
          status: "skipped",
          reason: `NQ daily lock: ${lockDecision.reason}`,
          signal: summarizedSignal
        });
        continue;
      }
    }

    if (isDemoFallbackSignal(signal)) {
      results.push({
        ...base,
        status: "skipped",
        reason: "synthetic demo fallback signal is shadow-only and cannot be routed",
        signal: summarizedSignal
      });
      continue;
    }

    const decision = evaluateSignalGuardrails({
      signal,
      timestamp: context.bar.ts,
      guardrails: options.config.guardrails,
      riskState,
      news: context.news,
      cotDealerZ52: undefined // COT data not yet plumbed into live context; fail-open per spec
    });

    if (!decision.allowed) {
      results.push({
        ...base,
        status: "skipped",
        reason: decision.reasons.join("; "),
        signal: summarizedSignal
      });
      continue;
    }

    const routeDisabledByMode = !options.enabled || !options.config.live.enabled || options.config.live.readOnly;
    if (routeDisabledByMode && routingBlockers.length > 0) {
      results.push({
        ...base,
        status: "skipped",
        reason: `shadow signal captured; routing blocked by: ${routingBlockers.join(" ")}`,
        signal: summarizedSignal
      });
      continue;
    }

    const classificationBlocker = executionClassificationBlocker(signal.strategyId);
    if (classificationBlocker) {
      results.push({
        ...base,
        status: "skipped",
        reason: classificationBlocker,
        signal: summarizedSignal
      });
      continue;
    }

    if (routingBlockers.length > 0) {
      results.push({
        ...base,
        status: "skipped",
        reason: `shadow signal captured; routing blocked by: ${routingBlockers.join(" ")}`,
        signal: summarizedSignal
      });
      continue;
    }

    if (demoCanaryEnabled() && (signal.contracts > 1 || !["NQ", "MNQ"].includes(signal.symbol))) {
      results.push({
        ...base,
        status: "skipped",
        reason: "demo canary only routes <=1 contract on NQ/MNQ",
        signal: summarizedSignal
      });
      continue;
    }

    if (submittedCount >= maxOrdersPerRun) {
      results.push({
        ...base,
        status: "skipped",
        reason: `shadow signal captured; max orders per run (${maxOrdersPerRun}) already reached`,
        signal: summarizedSignal
      });
      continue;
    }

    if (signal.symbol === "NQ" && challengeState) {
      try {
        const dailyLockUpdater = new DailyLock(challengeState.dailyLock);
        dailyLockUpdater.reserveSubmittedTrade(signal.strategyId, challengeState.phase);
        challengeState.dailyLock = dailyLockUpdater.getState();
        saveNQChallengeStateStrict(challengeState);
      } catch (error) {
        results.push({
          ...base,
          status: "skipped",
          reason: `NQ daily lock state could not be reserved before submit: ${error instanceof Error ? error.message : String(error)}`,
          signal: summarizedSignal
        });
        continue;
      }
    }

    const adapter = adapterFactory({
      ...options.config.live,
      accountId: lane.accountId
    });
    let receipt: ExecutionReceipt;
    try {
      receipt = await adapter.submit(signal);
    } catch (error) {
      results.push({
        ...base,
        status: "skipped",
        reason: error instanceof Error ? error.message : String(error),
        signal: summarizedSignal
      });
      continue;
    }
    submittedCount += 1;
    riskState = {
      ...riskState,
      tradeCount: riskState.tradeCount + 1
    };

    results.push({
      ...base,
      status: "submitted",
      reason: receipt.message,
      signal: summarizedSignal,
      receipt
    });
  }

  return {
    enabled: options.enabled,
    mode: routingBlockers.length === 0 ? "demo-route" : "shadow-only",
    blockers: routingBlockers,
    submittedCount,
    skippedCount: results.filter((lane) => lane.status === "skipped").length,
    maxOrdersPerRun,
    telemetry: summarizeTelemetry({ blockers: routingBlockers, lanes: results }),
    lanes: results
  };
}
