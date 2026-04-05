import type {
  ActiveTrade,
  BacktestResult,
  Bar,
  ExitReason,
  LabConfig,
  RiskState,
  Strategy,
  TradeRecord
} from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { applyTradeToRiskState, createInitialRiskState, evaluateSignalGuardrails } from "../risk/guardrails.js";
import { chicagoDateKey, elapsedMinutes, isAfterCtTime } from "../utils/time.js";

function calculateExecutionCostR(args: {
  contracts: number;
  config: LabConfig;
  exitReason: ExitReason;
}): number {
  const { contracts, config, exitReason } = args;
  const perContractRoundTripR =
    config.executionCosts.roundTripFeeRPerContract +
    (config.executionCosts.slippageRPerSidePerContract * 2);
  const stressApplied = exitReason === "timeout" || exitReason === "flat-cutoff";
  const stressedRoundTripR = perContractRoundTripR * (stressApplied ? config.executionCosts.stressMultiplier : 1);

  return (stressedRoundTripR * contracts) + config.executionCosts.stressBufferRPerTrade;
}

function closeTrade(args: {
  trade: ActiveTrade;
  exitPrice: number;
  exitTs: string;
  exitReason: ExitReason;
  config: LabConfig;
}): TradeRecord {
  const { trade, exitPrice, exitTs, exitReason, config } = args;
  const risk = trade.side === "long" ? trade.entry - trade.stop : trade.stop - trade.entry;
  const pnlPoints = trade.side === "long" ? exitPrice - trade.entry : trade.entry - exitPrice;
  const grossRMultiple = risk <= 0 ? 0 : pnlPoints / risk;
  const executionCostR = calculateExecutionCostR({
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

  const forceFlat = isAfterCtTime(bar.ts, config.guardrails.flatByCt);
  const timedOut = elapsedMinutes(trade.entryTs, bar.ts) >= trade.maxHoldMinutes;

  if (trade.side === "long") {
    const stopHit = bar.low <= trade.stop;
    const targetHit = bar.high >= trade.target;
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
    const targetHit = bar.low <= trade.target;
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
            entryTs: bar.ts
          };
          nextTradeId += 1;
        } else {
          rejectedSignals += 1;
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
    rejectedSignals
  };
}
