import type {
  ActiveTrade,
  BacktestResult,
  Bar,
  ExitReason,
  LabConfig,
  RejectedSignalRecord,
  RiskState,
  Strategy,
  TradeRecord
} from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { applyTradeToRiskState, createInitialRiskState, evaluateSignalGuardrails } from "../risk/guardrails.js";
import { chicagoDateKey, elapsedMinutes, isAfterCtTime } from "../utils/time.js";
import { pointsToTicks, ticksToDollars } from "../utils/markets.js";

const INTERNAL_META = {
  initialStop: "__rhInitialStop",
  pendingStop: "__rhPendingStop",
  runnerActive: "__rhRunnerActive"
} as const;

function getMetaNumber(trade: ActiveTrade, key: string): number | undefined {
  const value = trade.meta?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function setMetaNumber(trade: ActiveTrade, key: string, value: number | undefined): void {
  if (value === undefined || !Number.isFinite(value)) {
    return;
  }
  trade.meta = {
    ...(trade.meta ?? {}),
    [key]: value
  };
}

function getMetaBoolean(trade: ActiveTrade, key: string): boolean {
  return trade.meta?.[key] === true;
}

function setMetaBoolean(trade: ActiveTrade, key: string, value: boolean): void {
  trade.meta = {
    ...(trade.meta ?? {}),
    [key]: value
  };
}

function getInitialStop(trade: ActiveTrade): number {
  return getMetaNumber(trade, INTERNAL_META.initialStop) ?? trade.stop;
}

function computeInitialRisk(trade: ActiveTrade): number {
  const initialStop = getInitialStop(trade);
  const risk = trade.side === "long" ? trade.entry - initialStop : initialStop - trade.entry;
  return Math.max(0.000001, risk);
}

function applyPendingStopUpdate(trade: ActiveTrade): void {
  const pendingStop = getMetaNumber(trade, INTERNAL_META.pendingStop);
  if (pendingStop === undefined) {
    return;
  }

  if (trade.side === "long") {
    trade.stop = Math.max(trade.stop, pendingStop);
  } else {
    trade.stop = Math.min(trade.stop, pendingStop);
  }

  trade.meta = {
    ...(trade.meta ?? {})
  };
  delete trade.meta[INTERNAL_META.pendingStop];
}

function armNextBarStopManagement(args: {
  trade: ActiveTrade;
  bar: Bar;
  config: LabConfig;
}): void {
  const { trade, bar, config } = args;
  if (!config.stopManagement.enabled) {
    return;
  }

  const risk = computeInitialRisk(trade);
  const breakEvenTriggerR = Math.max(0, config.stopManagement.breakEvenTriggerR);
  const breakEvenOffsetR = config.stopManagement.breakEvenOffsetR;
  const runnerTriggerR = Math.max(0, config.stopManagement.runnerTriggerR);
  const trailingDistanceR = Math.max(0, config.stopManagement.runnerTrailingDistanceR);
  let pendingStop: number | undefined;

  if (trade.side === "long") {
    const favorableR = (bar.high - trade.entry) / risk;

    if (favorableR >= breakEvenTriggerR) {
      const breakEvenStop = trade.entry + (breakEvenOffsetR * risk);
      pendingStop = Math.max(trade.stop, breakEvenStop);
    }

    if (config.stopManagement.runnerEnabled && favorableR >= runnerTriggerR) {
      setMetaBoolean(trade, INTERNAL_META.runnerActive, true);
      const trailingStop = bar.high - (trailingDistanceR * risk);
      pendingStop = Math.max(pendingStop ?? trade.stop, trailingStop);
    }
  } else {
    const favorableR = (trade.entry - bar.low) / risk;

    if (favorableR >= breakEvenTriggerR) {
      const breakEvenStop = trade.entry - (breakEvenOffsetR * risk);
      pendingStop = Math.min(trade.stop, breakEvenStop);
    }

    if (config.stopManagement.runnerEnabled && favorableR >= runnerTriggerR) {
      setMetaBoolean(trade, INTERNAL_META.runnerActive, true);
      const trailingStop = bar.low + (trailingDistanceR * risk);
      pendingStop = Math.min(pendingStop ?? trade.stop, trailingStop);
    }
  }

  if (pendingStop !== undefined) {
    setMetaNumber(trade, INTERNAL_META.pendingStop, pendingStop);
  }
}

function calculateExecutionCostR(args: {
  symbol: string;
  entry: number;
  initialStop: number;
  contracts: number;
  config: LabConfig;
  exitReason: ExitReason;
}): number {
  const { symbol, entry, initialStop, contracts, config, exitReason } = args;
  const perContractRoundTripR =
    config.executionCosts.roundTripFeeRPerContract +
    (config.executionCosts.slippageRPerSidePerContract * 2);
  const stressApplied = exitReason === "timeout" || exitReason === "flat-cutoff";
  const stressedRoundTripR = perContractRoundTripR * (stressApplied ? config.executionCosts.stressMultiplier : 1);
  const stopDistancePoints = Math.max(0.000001, Math.abs(entry - initialStop));
  const stopDistanceTicks = Math.max(1, pointsToTicks(symbol, stopDistancePoints));
  const slippageTicksRoundTrip = Math.max(0, config.executionEnv.slippageTicksPerSide * 2);
  const spreadTicksRoundTrip = Math.max(0, config.executionEnv.maxSpreadTicks);

  const modeledSlippageR = config.executionEnv.slippageModel === "dollars"
    ? ticksToDollars(symbol, slippageTicksRoundTrip + spreadTicksRoundTrip, contracts) / Math.max(1, config.executionEnv.riskPerContractDollars * contracts)
    : (slippageTicksRoundTrip + spreadTicksRoundTrip) / stopDistanceTicks;

  const latencyPenaltyR =
    Math.max(0, config.executionEnv.latencyMs + (0.5 * config.executionEnv.latencyJitterMs))
    * 0.00004;
  const dataQualityPenaltyR = Math.max(0, config.executionEnv.dataQualityPenaltyR);

  return (stressedRoundTripR * contracts)
    + config.executionCosts.stressBufferRPerTrade
    + modeledSlippageR
    + latencyPenaltyR
    + dataQualityPenaltyR;
}

function closeTrade(args: {
  trade: ActiveTrade;
  exitPrice: number;
  exitTs: string;
  exitReason: ExitReason;
  config: LabConfig;
}): TradeRecord {
  const { trade, exitPrice, exitTs, exitReason, config } = args;
  const initialStop = getInitialStop(trade);
  const risk = trade.side === "long" ? trade.entry - initialStop : initialStop - trade.entry;
  const pnlPoints = trade.side === "long" ? exitPrice - trade.entry : trade.entry - exitPrice;
  const grossRMultiple = risk <= 0 ? 0 : pnlPoints / risk;
  const executionCostR = calculateExecutionCostR({
    symbol: trade.symbol,
    entry: trade.entry,
    initialStop,
    contracts: trade.contracts,
    config,
    exitReason
  });
  const netRMultiple = grossRMultiple - executionCostR;

  return {
    ...trade,
    exitTs,
    exitPrice,
    exitReason,
    pnlPoints,
    grossRMultiple,
    netRMultiple,
    executionCostR,
    rMultiple: netRMultiple,
    status: "closed"
  };
}

function evaluateExit(trade: ActiveTrade, bar: Bar, config: LabConfig): TradeRecord | null {
  if (trade.symbol !== bar.symbol) {
    return null;
  }

  applyPendingStopUpdate(trade);

  const forceFlat = isAfterCtTime(bar.ts, config.guardrails.flatByCt);
  const timedOut = elapsedMinutes(trade.entryTs, bar.ts) >= trade.maxHoldMinutes;
  const runnerActive = getMetaBoolean(trade, INTERNAL_META.runnerActive);

  if (trade.side === "long") {
    const stopHit = bar.low <= trade.stop;
    const targetHit = !runnerActive && (bar.high >= trade.target);
    if (stopHit && targetHit) {
      return closeTrade({ trade, exitPrice: trade.stop, exitTs: bar.ts, exitReason: "stop", config });
    }
    if (stopHit) {
      return closeTrade({ trade, exitPrice: trade.stop, exitTs: bar.ts, exitReason: "stop", config });
    }
    if (targetHit) {
      return closeTrade({ trade, exitPrice: trade.target, exitTs: bar.ts, exitReason: "target", config });
    }
  }

  if (trade.side === "short") {
    const stopHit = bar.high >= trade.stop;
    const targetHit = !runnerActive && (bar.low <= trade.target);
    if (stopHit && targetHit) {
      return closeTrade({ trade, exitPrice: trade.stop, exitTs: bar.ts, exitReason: "stop", config });
    }
    if (stopHit) {
      return closeTrade({ trade, exitPrice: trade.stop, exitTs: bar.ts, exitReason: "stop", config });
    }
    if (targetHit) {
      return closeTrade({ trade, exitPrice: trade.target, exitTs: bar.ts, exitReason: "target", config });
    }
  }

  if (forceFlat) {
    return closeTrade({ trade, exitPrice: bar.close, exitTs: bar.ts, exitReason: "flat-cutoff", config });
  }

  if (timedOut) {
    return closeTrade({ trade, exitPrice: bar.close, exitTs: bar.ts, exitReason: "timeout", config });
  }

  armNextBarStopManagement({ trade, bar, config });

  return null;
}

export async function runBacktest(args: {
  bars: Bar[];
  strategy: Strategy;
  config: LabConfig;
  newsGate: NewsGate;
}): Promise<BacktestResult> {
  const { bars, strategy, config, newsGate } = args;
  const historyBySymbol = new Map<string, Bar[]>();
  const sessionHistoryBySymbolDay = new Map<string, Bar[]>();
  const riskByDay = new Map<string, RiskState>();
  const trades: TradeRecord[] = [];
  const rejectedSignalRecords: RejectedSignalRecord[] = [];
  const rejectedReasonCounts = new Map<string, number>();
  let activeTrade: ActiveTrade | null = null;
  let nextTradeId = 1;
  let rejectedSignals = 0;

  for (const bar of bars) {
    const dayKey = chicagoDateKey(bar.ts);
    const currentRiskState = riskByDay.get(dayKey) ?? createInitialRiskState();
    const history = historyBySymbol.get(bar.symbol) ?? [];
    const sessionKey = `${dayKey}:${bar.symbol}`;
    const sessionHistory = sessionHistoryBySymbolDay.get(sessionKey) ?? [];

    if (activeTrade) {
      const exited = evaluateExit(activeTrade, bar, config);
      if (exited) {
        trades.push(exited);
        riskByDay.set(dayKey, applyTradeToRiskState(currentRiskState, exited.netRMultiple));
        activeTrade = null;
      }
    }

    if (!activeTrade) {
      const news = newsGate.score({ symbol: bar.symbol, ts: bar.ts, bar });
      const signal = strategy.generateSignal({
        symbol: bar.symbol,
        bar,
        history,
        sessionHistory,
        config,
        news,
        dailyTradeCount: currentRiskState.tradeCount
      });

      if (signal) {
        const decision = evaluateSignalGuardrails({
          signal,
          timestamp: bar.ts,
          guardrails: config.guardrails,
          riskState: currentRiskState,
          news
        });

        if (decision.allowed) {
          activeTrade = {
            ...signal,
            id: `trade_${String(nextTradeId).padStart(4, "0")}`,
            entryTs: bar.ts,
            meta: {
              ...(signal.meta ?? {}),
              [INTERNAL_META.initialStop]: signal.stop,
              [INTERNAL_META.runnerActive]: false
            }
          };
          nextTradeId += 1;
        } else {
          rejectedSignals += 1;
          rejectedSignalRecords.push({
            ts: bar.ts,
            symbol: signal.symbol,
            strategyId: signal.strategyId,
            reasons: decision.reasons,
            newsImpact: news?.impact,
            newsBlackoutActive: news?.blackout?.active === true
          });

          for (const reason of decision.reasons) {
            rejectedReasonCounts.set(reason, (rejectedReasonCounts.get(reason) ?? 0) + 1);
          }
        }
      }
    }

    history.push(bar);
    sessionHistory.push(bar);
    historyBySymbol.set(bar.symbol, history);
    sessionHistoryBySymbolDay.set(sessionKey, sessionHistory);
  }

  return {
    trades,
    rejectedSignals,
    rejectedSignalRecords,
    rejectedReasonCounts: Object.fromEntries(rejectedReasonCounts.entries())
  };
}
