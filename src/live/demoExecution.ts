import type { Bar, LabConfig, TradeRecord, StrategySignal } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { applyTradeToRiskState, createInitialRiskState, evaluateSignalGuardrails } from "../risk/guardrails.js";
import { chicagoDateKey } from "../utils/time.js";
import { isDemoAccountLockSatisfied } from "./demoAccounts.js";
import type { DemoStrategySampleSnapshot } from "./demoSampling.js";
import { buildStrategyCatalog } from "../strategies/wctcEnsemble.js";
import type { ExecutionReceipt, ExecutionAdapter } from "../adapters/topstep/topstepAdapter.js";
import { ProjectXLiveAdapter } from "../adapters/projectx/projectxAdapter.js";

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

export interface FuturesDemoExecutionReport {
  enabled: boolean;
  mode: "demo-route" | "shadow-only";
  blockers: string[];
  submittedCount: number;
  skippedCount: number;
  maxOrdersPerRun: number;
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

export async function executeFuturesDemoLanes(
  options: ExecuteFuturesDemoLanesOptions
): Promise<FuturesDemoExecutionReport> {
  const maxOrdersPerRun = Math.max(1, options.maxOrdersPerRun);
  const blockers = [
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

    if (blockers.length > 0) {
      results.push({
        ...base,
        status: "skipped",
        reason: blockers.join(" "),
        signal: null
      });
      continue;
    }

    if (submittedCount >= maxOrdersPerRun) {
      results.push({
        ...base,
        status: "skipped",
        reason: `max orders per run (${maxOrdersPerRun}) already reached`,
        signal: null
      });
      continue;
    }

    if (riskState.tradeCount >= options.config.guardrails.maxTradesPerDay) {
      results.push({
        ...base,
        status: "skipped",
        reason: `daily trade cap ${options.config.guardrails.maxTradesPerDay} already reached`,
        signal: null
      });
      continue;
    }

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

    const signal = strategy.generateSignal(context);
    if (!signal) {
      results.push({
        ...base,
        status: "skipped",
        reason: `${lane.primaryStrategy} did not produce a routable signal on ${lane.focusSymbol}`,
        signal: null
      });
      continue;
    }

    const decision = evaluateSignalGuardrails({
      signal,
      timestamp: context.bar.ts,
      guardrails: options.config.guardrails,
      riskState,
      news: context.news
    });

    if (!decision.allowed) {
      results.push({
        ...base,
        status: "skipped",
        reason: decision.reasons.join("; "),
        signal: summarizeSignal({
          timestamp: context.bar.ts,
          signal
        })
      });
      continue;
    }

    const adapter = adapterFactory({
      ...options.config.live,
      accountId: lane.accountId
    });
    const receipt = await adapter.submit(signal);
    submittedCount += 1;
    riskState = {
      ...riskState,
      tradeCount: riskState.tradeCount + 1
    };

    results.push({
      ...base,
      status: "submitted",
      reason: receipt.message,
      signal: summarizeSignal({
        timestamp: context.bar.ts,
        signal
      }),
      receipt
    });
  }

  return {
    enabled: options.enabled,
    mode: blockers.length === 0 ? "demo-route" : "shadow-only",
    blockers,
    submittedCount,
    skippedCount: results.filter((lane) => lane.status === "skipped").length,
    maxOrdersPerRun,
    lanes: results
  };
}
