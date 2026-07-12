import type {
  ActiveTrade,
  BacktestResult,
  Bar,
  ExitReason,
  LabConfig,
  MacroContextSnapshot,
  RejectedSignalRecord,
  RiskState,
  Strategy,
  TradeRecord
} from "../domain.js";
import { readFile } from "node:fs/promises";
import type { NewsGate } from "../news/base.js";
import { applyTradeToRiskState, createInitialRiskState, evaluateSignalGuardrails } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { chicagoDateKey, elapsedMinutes, isAfterCtTime, minutesFromCtTime } from "../utils/time.js";
import { pointsToTicks, ticksToDollars } from "../utils/markets.js";

const INTERNAL_META = {
  initialStop: "__rhInitialStop",
  pendingStop: "__rhPendingStop",
  runnerActive: "__rhRunnerActive"
} as const;

function macroMeta(macroContext?: MacroContextSnapshot): Record<string, string | number | boolean> {
  if (!macroContext) {
    return {};
  }

  return {
    macroSource: macroContext.source,
    macroRiskRegime: macroContext.riskRegime,
    ...(macroContext.tailScore !== null ? { macroTailScore: macroContext.tailScore } : {}),
    macroVixTermStructure: macroContext.vixTermStructure,
    macroCreditRiskProxy: macroContext.creditRiskProxy,
    macroEquityTrendProxy: macroContext.equityTrendProxy
  };
}

function entryResearchMeta(args: {
  bar: Bar;
  history: Bar[];
  sessionHistory: Bar[];
  config: LabConfig;
}): Record<string, string | number> {
  const sourceHistory = args.sessionHistory.length >= 8 ? args.sessionHistory : args.history;
  const recent = sourceHistory.slice(-20);
  const avgVolume = recent.length === 0
    ? 0
    : recent.reduce((sum, bar) => sum + bar.volume, 0) / recent.length;
  const atr = averageTrueRange(sourceHistory, Math.min(14, Math.max(4, sourceHistory.length)));
  const sessionWindow = getMarketSessionWindow(args.bar.symbol, args.config.guardrails.sessionStartCt);
  const sessionMinute = minutesFromCtTime(args.bar.ts, sessionWindow.startCt);
  const sessionBucket = sessionMinute < 0
    ? "pre-session"
    : sessionMinute < 30
      ? "first-30m"
      : sessionMinute < 90
        ? "30-90m"
        : sessionMinute < 180
          ? "90-180m"
          : "late-session";

  return {
    entrySessionMinute: sessionMinute,
    entrySessionBucket: sessionBucket,
    entryVolumeRatio20: avgVolume > 0 ? Number((args.bar.volume / avgVolume).toFixed(4)) : 0,
    entryAtrPct: atr > 0 && args.bar.close !== 0 ? Number(((atr / args.bar.close) * 100).toFixed(4)) : 0,
    entryRangeAtr: atr > 0 ? Number(((args.bar.high - args.bar.low) / atr).toFixed(4)) : 0
  };
}

async function loadHmmState(): Promise<Record<string, { regime: string; confidence: number }>> {
  try {
    const raw = await readFile(".rumbling-hedge/state/hmm-regime.json", "utf8");
    const data = JSON.parse(raw);
    const out: Record<string, { regime: string; confidence: number }> = {};
    for (const [symbol, result] of Object.entries(data.results || {})) {
      const states = (result as any).states || {};
      let bestState: any = null;
      let bestCount = 0;
      let total = 0;
      for (const [, state] of Object.entries(states)) {
        const s = state as any;
        total += s.count || 0;
        if ((s.count || 0) > bestCount) {
          bestCount = s.count;
          bestState = s;
        }
      }
      if (bestState) {
        out[symbol] = {
          regime: bestState.label || "range-chop",
          confidence: total > 0 ? bestCount / total : 0.5
        };
      }
    }
    return out;
  } catch {
    return {};
  }
}

async function loadCotScores(): Promise<Record<string, number>> {
  try {
    const raw = await readFile(".rumbling-hedge/state/cot-status.smoke.out", "utf8");
    const out: Record<string, number> = {};
    for (const line of raw.split("\n")) {
      const match = line.match(/^\s*(\w+)\s+.*z52=([-\d.]+)/);
      if (match) out[match[1]!] = Number.parseFloat(match[2]!);
    }
    return out;
  } catch {
    return {};
  }
}

async function loadKronosForecasts(bars: Bar[]): Promise<Record<string, { direction: number; confidence: number }>> {
  try {
    const symbols = [...new Set(bars.map((bar) => bar.symbol))];
    const out: Record<string, { direction: number; confidence: number }> = {};
    for (const symbol of symbols) {
      const symbolBars = bars.filter((bar) => bar.symbol === symbol).slice(-128);
      if (symbolBars.length < 8) continue;
      const history = symbolBars.map((bar) => ({
        ts: bar.ts,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume
      }));
      const lastBar = symbolBars.at(-1)!;
      const futureTs = [new Date(Date.parse(lastBar.ts) + 3_600_000).toISOString()];
      const resp = await fetch("http://127.0.0.1:8787/forecast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, history, future_timestamps: futureTs }),
        signal: AbortSignal.timeout(10_000)
      });
      if (!resp.ok) continue;
      const data = await resp.json() as { predicted?: Array<{ close: number }> };
      if (data.predicted && data.predicted.length > 0) {
        const lastClose = lastBar.close;
        const predClose = data.predicted[0]!.close;
        const change = (predClose - lastClose) / lastClose;
        out[symbol] = {
          direction: Math.tanh(change * 100),
          confidence: Math.min(0.8, 0.4 + Math.abs(change) * 50)
        };
      }
    }
    return out;
  } catch {
    return {};
  }
}

async function loadTimesfmForecasts(): Promise<Record<string, { direction: number; confidence: number }>> {
  try {
    const raw = await readFile(".rumbling-hedge/research/timesfm/forecast-v1.json", "utf8");
    const data = JSON.parse(raw);
    if (data.status !== "ok") return {};
    const out: Record<string, { direction: number; confidence: number }> = {};
    const series = Array.isArray(data.series) ? data.series : [];
    for (const s of series) {
      const symbol = s.symbol;
      const points = Array.isArray(s.point) ? s.point : [];
      if (!symbol || points.length < 2) continue;
      const lastActual = s.lastClose || points[0];
      const predClose = points[points.length - 1];
      const change = (predClose - lastActual) / Math.max(lastActual, 0.0001);
      out[symbol] = {
        direction: Math.tanh(change * 50),
        confidence: Math.min(0.8, 0.4 + Math.abs(change) * 25)
      };
    }
    return out;
  } catch {
    return {};
  }
}

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
  macroContext?: MacroContextSnapshot;
}): Promise<BacktestResult> {
  const { bars, strategy, config, newsGate, macroContext } = args;
  const historyBySymbol = new Map<string, Bar[]>();
  const sessionHistoryBySymbolDay = new Map<string, Bar[]>();
  const riskByDay = new Map<string, RiskState>();
  const trades: TradeRecord[] = [];
  const rejectedSignalRecords: RejectedSignalRecord[] = [];
  const rejectedReasonCounts = new Map<string, number>();
  let activeTrade: ActiveTrade | null = null;
  let nextTradeId = 1;
  let rejectedSignals = 0;
  const hmmState = await loadHmmState();
  const cotScores = await loadCotScores();
  const kronosForecasts = await loadKronosForecasts(bars);
  const timesfmForecasts = await loadTimesfmForecasts();
  const mergedForecasts: Record<string, { direction: number; confidence: number }> = {
    ...timesfmForecasts,
    ...kronosForecasts
  };

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
      const forecast = mergedForecasts[bar.symbol];
      const macro = {
        hmmRegime: hmmState[bar.symbol]?.regime,
        hmmConfidence: hmmState[bar.symbol]?.confidence,
        cotDealerZ52: cotScores[bar.symbol],
        kronosDirection: forecast?.direction,
        kronosConfidence: forecast?.confidence,
        vixRegime: macroContext?.vixTermStructure !== "unknown"
          ? macroContext?.vixTermStructure
          : hmmState[bar.symbol]?.regime === "high-vol"
            ? "backwardation"
            : "contango",
        capitulationScore: macroContext?.tailScore != null
          ? Math.min(5, Math.max(0, Math.round(macroContext.tailScore / 20)))
          : hmmState[bar.symbol]?.regime === "high-vol"
            ? 1
            : 0
      };
      const signal = strategy.generateSignal({
        symbol: bar.symbol,
        bar,
        history,
        sessionHistory,
        config,
        news,
        macroContext,
        macro,
        dailyTradeCount: currentRiskState.tradeCount
      });

      if (signal) {
        const decision = evaluateSignalGuardrails({
          signal,
          timestamp: bar.ts,
          guardrails: config.guardrails,
          riskState: currentRiskState,
          news,
          cotDealerZ52: cotScores[bar.symbol]
        });

        if (decision.allowed) {
          activeTrade = {
            ...signal,
            id: `trade_${String(nextTradeId).padStart(4, "0")}`,
            entryTs: bar.ts,
            meta: {
              ...(signal.meta ?? {}),
              ...macroMeta(macroContext),
              ...entryResearchMeta({ bar, history, sessionHistory, config }),
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
            newsBlackoutActive: news?.blackout?.active === true,
            ...(macroContext ? {
              macroRiskRegime: macroContext.riskRegime,
              macroTailScore: macroContext.tailScore
            } : {})
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
    rejectedReasonCounts: Object.fromEntries(rejectedReasonCounts.entries()),
    ...(macroContext ? { macroContext } : {})
  };
}
