import type {
  Bar,
  LabConfig,
  RiskTradeBucketSummary,
  RiskTradeSegmentInsight,
  RiskTradeModelReport,
  RiskTradeScenarioSummary,
  TradeRecord
} from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { runBacktest } from "./backtest.js";
import { summarizeTrades } from "./report.js";
import type { Strategy } from "../domain.js";

const BUCKET_DEFS: Array<{ bucket: string; min: number; max?: number }> = [
  { bucket: "2.5-3.0R", min: 2.5, max: 3.0 },
  { bucket: "3.0-4.0R", min: 3.0, max: 4.0 },
  { bucket: "4.0-6.0R", min: 4.0, max: 6.0 },
  { bucket: "6.0R+", min: 6.0 }
];

function createFrictionlessConfig(baseConfig: LabConfig): LabConfig {
  return {
    ...baseConfig,
    executionCosts: {
      ...baseConfig.executionCosts,
      roundTripFeeRPerContract: 0,
      slippageRPerSidePerContract: 0,
      stressMultiplier: 1,
      stressBufferRPerTrade: 0
    },
    executionEnv: {
      ...baseConfig.executionEnv,
      latencyMs: 0,
      latencyJitterMs: 0,
      slippageTicksPerSide: 0,
      dataQualityPenaltyR: 0
    }
  };
}

function createStressedConfig(baseConfig: LabConfig): LabConfig {
  return {
    ...baseConfig,
    executionCosts: {
      ...baseConfig.executionCosts,
      slippageRPerSidePerContract: baseConfig.executionCosts.slippageRPerSidePerContract * 1.75,
      stressMultiplier: baseConfig.executionCosts.stressMultiplier * 1.4,
      stressBufferRPerTrade: baseConfig.executionCosts.stressBufferRPerTrade + 0.05
    },
    executionEnv: {
      ...baseConfig.executionEnv,
      latencyMs: baseConfig.executionEnv.latencyMs * 2,
      latencyJitterMs: baseConfig.executionEnv.latencyJitterMs * 2,
      slippageTicksPerSide: Math.max(1, baseConfig.executionEnv.slippageTicksPerSide + 1),
      dataQualityPenaltyR: baseConfig.executionEnv.dataQualityPenaltyR * 2
    }
  };
}

function summarizeScenario(name: string, trades: TradeRecord[]): RiskTradeScenarioSummary {
  const summary = summarizeTrades(trades);

  return {
    name,
    trades: summary.totalTrades,
    grossTotalR: Number(summary.grossTotalR.toFixed(4)),
    netTotalR: Number(summary.netTotalR.toFixed(4)),
    averageR: Number(summary.averageR.toFixed(4)),
    winRate: Number(summary.winRate.toFixed(4)),
    maxDrawdownR: Number(summary.maxDrawdownR.toFixed(4)),
    cvar95TradeR: Number(summary.tradeQuality.cvar95TradeR.toFixed(4)),
    riskOfRuinProb: Number(summary.tradeQuality.riskOfRuinProb.toFixed(4))
  };
}

function buildBucketNote(args: {
  bucket: string;
  averageR: number;
  winRate: number;
  frictionlessNetR: number;
  stressedNetR: number;
  currentNetR: number;
}): string {
  const { bucket, averageR, winRate, frictionlessNetR, stressedNetR, currentNetR } = args;

  if (currentNetR <= 0) {
    return `${bucket} bucket is not profitable after current execution costs.`;
  }

  const frictionLoss = frictionlessNetR - currentNetR;

  if (stressedNetR > 0 && stressedNetR >= currentNetR * 0.7) {
    return `${bucket} bucket remains resilient under stress; this is the best candidate for narrow, controlled risk.`;
  }

  if (averageR > 0 && winRate >= 0.4) {
    if (frictionLoss > 0.25) {
      return `${bucket} bucket has edge, but latency/friction strips a meaningful share of it.`;
    }

    return `${bucket} bucket has acceptable expectancy and is worth keeping under guardrails.`;
  }

  return `${bucket} bucket is too fragile; keep it in research only.`;
}

function buildBucketMap(trades: TradeRecord[]): Map<string, RiskTradeBucketSummary> {
  const bucketMap = new Map<string, RiskTradeBucketSummary>();

  for (const def of BUCKET_DEFS) {
    const bucketTrades = trades.filter((trade) => trade.rr >= def.min && (def.max === undefined || trade.rr < def.max));
    const summary = summarizeTrades(bucketTrades);
    bucketMap.set(def.bucket, {
      bucket: def.bucket,
      trades: summary.totalTrades,
      winRate: Number(summary.winRate.toFixed(4)),
      grossTotalR: Number(summary.grossTotalR.toFixed(4)),
      netTotalR: Number(summary.netTotalR.toFixed(4)),
      averageR: Number(summary.averageR.toFixed(4)),
      maxDrawdownR: Number(summary.maxDrawdownR.toFixed(4)),
      cvar95TradeR: Number(summary.tradeQuality.cvar95TradeR.toFixed(4)),
      note: bucketTrades.length === 0 ? `No trades landed in the ${def.bucket} bucket.` : ""
    });
  }

  return bucketMap;
}

function buildBucketSummaries(args: {
  currentTrades: TradeRecord[];
  frictionlessTrades: TradeRecord[];
  stressedTrades: TradeRecord[];
}): RiskTradeBucketSummary[] {
  const currentBuckets = buildBucketMap(args.currentTrades);
  const frictionlessBuckets = buildBucketMap(args.frictionlessTrades);
  const stressedBuckets = buildBucketMap(args.stressedTrades);

  return BUCKET_DEFS.map((def) => {
    const current = currentBuckets.get(def.bucket) ?? {
      bucket: def.bucket,
      trades: 0,
      winRate: 0,
      grossTotalR: 0,
      netTotalR: 0,
      averageR: 0,
      maxDrawdownR: 0,
      cvar95TradeR: 0,
      note: `No trades landed in the ${def.bucket} bucket.`
    };
    const frictionless = frictionlessBuckets.get(def.bucket) ?? current;
    const stressed = stressedBuckets.get(def.bucket) ?? current;

    return {
      ...current,
      note: current.trades === 0
        ? current.note
        : buildBucketNote({
            bucket: def.bucket,
            averageR: current.averageR,
            winRate: current.winRate,
            frictionlessNetR: frictionless.netTotalR,
            stressedNetR: stressed.netTotalR,
            currentNetR: current.netTotalR
          })
    };
  });
}

function pickPreferredBucket(buckets: RiskTradeBucketSummary[]): RiskTradeBucketSummary | null {
  const eligible = buckets.filter((bucket) => bucket.trades > 0 && bucket.netTotalR > 0);
  if (eligible.length === 0) {
    return null;
  }

  return eligible.sort((left, right) => {
    const leftResilience = left.netTotalR - Math.abs(left.cvar95TradeR) - left.maxDrawdownR;
    const rightResilience = right.netTotalR - Math.abs(right.cvar95TradeR) - right.maxDrawdownR;
    return rightResilience - leftResilience;
  })[0] ?? null;
}

function buildSegmentInsight(args: {
  kind: "strategy" | "symbol";
  key: string;
  currentTrades: TradeRecord[];
  frictionlessTrades: TradeRecord[];
  stressedTrades: TradeRecord[];
}): RiskTradeSegmentInsight {
  const current = summarizeScenario("current", args.currentTrades);
  const frictionless = summarizeScenario("frictionless", args.frictionlessTrades);
  const stressed = summarizeScenario("stressed", args.stressedTrades);
  const rrBuckets = buildBucketSummaries({
    currentTrades: args.currentTrades,
    frictionlessTrades: args.frictionlessTrades,
    stressedTrades: args.stressedTrades
  });
  const preferredBucket = pickPreferredBucket(rrBuckets);

  return {
    kind: args.kind,
    key: args.key,
    current,
    frictionless,
    stressed,
    rrBuckets,
    recommendation: {
      preferredBucket: preferredBucket?.bucket ?? null,
      reason: preferredBucket
        ? preferredBucket.note
        : `No resilient RR bucket exists for ${args.kind} ${args.key}; keep this lane narrow.`,
      modelView: preferredBucket
        ? `For ${args.kind} ${args.key}, the best slightly risky but good risk-to-reward trades are the ones that preserve netR under stress and retain low drawdown.`
        : `For ${args.kind} ${args.key}, the trade set is too fragile to widen yet.`
    }
  };
}

function groupTradesByKey(trades: TradeRecord[], keySelector: (trade: TradeRecord) => string): Map<string, TradeRecord[]> {
  const grouped = new Map<string, TradeRecord[]>();

  for (const trade of trades) {
    const key = keySelector(trade);
    const current = grouped.get(key) ?? [];
    current.push(trade);
    grouped.set(key, current);
  }

  return grouped;
}

export async function runRiskTradeModel(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  strategy: Strategy;
  newsGate: NewsGate;
}): Promise<RiskTradeModelReport> {
  const currentRun = await runBacktest({
    bars: args.bars,
    strategy: args.strategy,
    config: args.baseConfig,
    newsGate: args.newsGate
  });

  const frictionlessRun = await runBacktest({
    bars: args.bars,
    strategy: args.strategy,
    config: createFrictionlessConfig(args.baseConfig),
    newsGate: args.newsGate
  });

  const stressedRun = await runBacktest({
    bars: args.bars,
    strategy: args.strategy,
    config: createStressedConfig(args.baseConfig),
    newsGate: args.newsGate
  });

  const current = summarizeScenario("current", currentRun.trades);
  const frictionless = summarizeScenario("frictionless", frictionlessRun.trades);
  const stressed = summarizeScenario("stressed", stressedRun.trades);
  const rrBuckets = buildBucketSummaries({
    currentTrades: currentRun.trades,
    frictionlessTrades: frictionlessRun.trades,
    stressedTrades: stressedRun.trades
  });
  const preferredBucket = pickPreferredBucket(rrBuckets);

  const strategyKeys = Array.from(new Set(currentRun.trades.map((trade) => trade.strategyId)));
  const symbolKeys = Array.from(new Set(currentRun.trades.map((trade) => trade.symbol)));
  const frictionlessByStrategy = groupTradesByKey(frictionlessRun.trades, (trade) => trade.strategyId);
  const stressedByStrategy = groupTradesByKey(stressedRun.trades, (trade) => trade.strategyId);
  const frictionlessBySymbol = groupTradesByKey(frictionlessRun.trades, (trade) => trade.symbol);
  const stressedBySymbol = groupTradesByKey(stressedRun.trades, (trade) => trade.symbol);

  const strategyInsights = strategyKeys.map((key) => buildSegmentInsight({
    kind: "strategy",
    key,
    currentTrades: currentRun.trades.filter((trade) => trade.strategyId === key),
    frictionlessTrades: frictionlessByStrategy.get(key) ?? [],
    stressedTrades: stressedByStrategy.get(key) ?? []
  }));

  const symbolInsights = symbolKeys.map((key) => buildSegmentInsight({
    kind: "symbol",
    key,
    currentTrades: currentRun.trades.filter((trade) => trade.symbol === key),
    frictionlessTrades: frictionlessBySymbol.get(key) ?? [],
    stressedTrades: stressedBySymbol.get(key) ?? []
  }));

  return {
    timestamp: new Date().toISOString(),
    current,
    frictionless,
    stressed,
    edgeDecay: {
      frictionlessMinusCurrentNetR: Number((frictionless.netTotalR - current.netTotalR).toFixed(4)),
      stressedMinusCurrentNetR: Number((stressed.netTotalR - current.netTotalR).toFixed(4)),
      grossEdgeRetention: current.grossTotalR === 0 ? 0 : Number((current.netTotalR / current.grossTotalR).toFixed(4))
    },
    rrBuckets,
    strategyInsights,
    symbolInsights,
    recommendation: {
      preferredBucket: preferredBucket?.bucket ?? null,
      reason: preferredBucket
        ? preferredBucket.note
        : "No RR bucket produced positive, resilient expectancy; keep the model narrow and raise selectivity."
      ,
      modelView: preferredBucket
        ? "Slightly risky but good risk-to-reward trades are only acceptable when they retain edge under stress and do not explode tail risk."
        : "The current trade set is not robust enough to widen risk; continue with narrow research only."
    }
  };
}