import type {
  FamilyBudgetEntry,
  FamilyBudgetRecommendation,
  MarketCategory,
  SummaryReport,
  TradeQualityMetrics,
  TradeRecord
} from "../domain.js";
import { getMarketCategory } from "../utils/markets.js";

const MARKET_FAMILIES: MarketCategory[] = ["index", "fx", "energy", "metal", "bond", "ag", "crypto"];

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function mean(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }

  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function sampleStd(values: number[]): number {
  if (values.length < 2) {
    return 0;
  }

  const avg = mean(values);
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / (values.length - 1);
  return Math.sqrt(Math.max(0, variance));
}

function downsideStd(values: number[]): number {
  const downside = values.filter((value) => value < 0);
  if (downside.length < 2) {
    return 0;
  }

  return sampleStd(downside);
}

function calculateStreaks(values: number[]): { maxWins: number; maxLosses: number } {
  let maxWins = 0;
  let maxLosses = 0;
  let currentWins = 0;
  let currentLosses = 0;

  for (const value of values) {
    if (value > 0) {
      currentWins += 1;
      currentLosses = 0;
      maxWins = Math.max(maxWins, currentWins);
      continue;
    }

    if (value < 0) {
      currentLosses += 1;
      currentWins = 0;
      maxLosses = Math.max(maxLosses, currentLosses);
      continue;
    }

    currentWins = 0;
    currentLosses = 0;
  }

  return { maxWins, maxLosses };
}

function calculateUlcerIndex(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }

  let equity = 0;
  let peak = 0;
  let drawdownSquareSum = 0;

  for (const value of values) {
    equity += value;
    peak = Math.max(peak, equity);
    const drawdown = peak - equity;
    drawdownSquareSum += drawdown ** 2;
  }

  return Math.sqrt(drawdownSquareSum / values.length);
}

function calculateCvar95(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }

  const sorted = [...values].sort((left, right) => left - right);
  const tailCount = Math.max(1, Math.ceil(sorted.length * 0.05));
  const tail = sorted.slice(0, tailCount);
  return mean(tail);
}

function createDeterministicRng(seed: number): () => number {
  let state = seed >>> 0;

  return () => {
    state = ((1664525 * state) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function estimateRiskOfRuin(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }

  const simulations = 500;
  const horizonTrades = Math.max(50, values.length * 3);
  const ruinThresholdR = -6;
  const rng = createDeterministicRng(9042026);
  let ruined = 0;

  for (let simulation = 0; simulation < simulations; simulation += 1) {
    let equity = 0;

    for (let index = 0; index < horizonTrades; index += 1) {
      const sampleIndex = Math.floor(rng() * values.length);
      const tradeR = values[sampleIndex] ?? 0;
      equity += tradeR;
      if (equity <= ruinThresholdR) {
        ruined += 1;
        break;
      }
    }
  }

  return ruined / simulations;
}

function buildTradeQualityMetrics(trades: TradeRecord[]): TradeQualityMetrics {
  const values = trades.map((trade) => trade.netRMultiple);
  const wins = values.filter((value) => value > 0);
  const losses = values.filter((value) => value < 0);
  const avg = mean(values);
  const avgWin = mean(wins);
  const avgLoss = mean(losses);
  const std = sampleStd(values);
  const downside = downsideStd(values);
  const streaks = calculateStreaks(values);
  const cvar95 = calculateCvar95(values);

  return {
    expectancyR: Number(avg.toFixed(4)),
    payoffRatio: avgLoss === 0 ? 0 : Number((Math.abs(avgWin / avgLoss)).toFixed(4)),
    avgWinR: Number(avgWin.toFixed(4)),
    avgLossR: Number(avgLoss.toFixed(4)),
    winRate: values.length === 0 ? 0 : Number((wins.length / values.length).toFixed(4)),
    lossRate: values.length === 0 ? 0 : Number((losses.length / values.length).toFixed(4)),
    maxConsecutiveWins: streaks.maxWins,
    maxConsecutiveLosses: streaks.maxLosses,
    sharpePerTrade: std === 0 ? 0 : Number((avg / std).toFixed(4)),
    sortinoPerTrade: downside === 0 ? 0 : Number((avg / downside).toFixed(4)),
    ulcerIndexR: Number(calculateUlcerIndex(values).toFixed(4)),
    cvar95TradeR: Number(cvar95.toFixed(4)),
    riskOfRuinProb: Number(estimateRiskOfRuin(values).toFixed(4))
  };
}

export function summarizeTrades(trades: TradeRecord[]): SummaryReport {
  let wins = 0;
  let losses = 0;
  let positive = 0;
  let negative = 0;
  let netCumulativeR = 0;
  let peakNetR = 0;
  let maxDrawdownR = 0;
  const byStrategy = new Map<string, TradeRecord[]>();
  const bySymbol = new Map<string, TradeRecord[]>();
  const byMarketFamily = new Map<MarketCategory, TradeRecord[]>();

  for (const trade of trades) {
    if (trade.netRMultiple > 0) {
      wins += 1;
      positive += trade.netRMultiple;
    } else if (trade.netRMultiple < 0) {
      losses += 1;
      negative += trade.netRMultiple;
    }

    netCumulativeR += trade.netRMultiple;
    peakNetR = Math.max(peakNetR, netCumulativeR);
    maxDrawdownR = Math.max(maxDrawdownR, peakNetR - netCumulativeR);

    const current = byStrategy.get(trade.strategyId) ?? [];
    current.push(trade);
    byStrategy.set(trade.strategyId, current);

    const symbolTrades = bySymbol.get(trade.symbol) ?? [];
    symbolTrades.push(trade);
    bySymbol.set(trade.symbol, symbolTrades);

    const marketFamily = getMarketCategory(trade.symbol);
    const familyTrades = byMarketFamily.get(marketFamily) ?? [];
    familyTrades.push(trade);
    byMarketFamily.set(marketFamily, familyTrades);
  }

  const netTotalR = trades.reduce((sum, trade) => sum + trade.netRMultiple, 0);
  const grossTotalR = trades.reduce((sum, trade) => sum + trade.grossRMultiple, 0);
  const frictionR = grossTotalR - netTotalR;
  const strategySummary = Object.fromEntries(
    Array.from(byStrategy.entries()).map(([strategyId, strategyTrades]) => {
      const total = strategyTrades.reduce((sum, trade) => sum + trade.netRMultiple, 0);
      const strategyWins = strategyTrades.filter((trade) => trade.netRMultiple > 0).length;
      return [
        strategyId,
        {
          trades: strategyTrades.length,
          totalR: Number(total.toFixed(2)),
          winRate: strategyTrades.length === 0 ? 0 : Number((strategyWins / strategyTrades.length).toFixed(4))
        }
      ];
    })
  );
  const symbolSummary = Object.fromEntries(
    Array.from(bySymbol.entries()).map(([symbol, symbolTrades]) => {
      const gross = symbolTrades.reduce((sum, trade) => sum + trade.grossRMultiple, 0);
      const net = symbolTrades.reduce((sum, trade) => sum + trade.netRMultiple, 0);
      const symbolWins = symbolTrades.filter((trade) => trade.netRMultiple > 0).length;
      return [
        symbol,
        {
          trades: symbolTrades.length,
          grossTotalR: Number(gross.toFixed(2)),
          netTotalR: Number(net.toFixed(2)),
          averageR: symbolTrades.length === 0 ? 0 : Number((net / symbolTrades.length).toFixed(4)),
          winRate: symbolTrades.length === 0 ? 0 : Number((symbolWins / symbolTrades.length).toFixed(4))
        }
      ];
    })
  );
  const familySummary = Object.fromEntries(
    MARKET_FAMILIES.map((marketFamily) => {
      const familyTrades = byMarketFamily.get(marketFamily) ?? [];
      const gross = familyTrades.reduce((sum, trade) => sum + trade.grossRMultiple, 0);
      const net = familyTrades.reduce((sum, trade) => sum + trade.netRMultiple, 0);
      const familyWins = familyTrades.filter((trade) => trade.netRMultiple > 0).length;
      return [
        marketFamily,
        {
          trades: familyTrades.length,
          grossTotalR: Number(gross.toFixed(2)),
          netTotalR: Number(net.toFixed(2)),
          averageR: familyTrades.length === 0 ? 0 : Number((net / familyTrades.length).toFixed(4)),
          winRate: familyTrades.length === 0 ? 0 : Number((familyWins / familyTrades.length).toFixed(4))
        }
      ];
    })
  ) as Record<MarketCategory, { trades: number; grossTotalR: number; netTotalR: number; averageR: number; winRate: number }>;

  const positiveFamilyTotal = MARKET_FAMILIES.reduce(
    (sum, marketFamily) => sum + Math.max(0, familySummary[marketFamily].netTotalR),
    0
  );
  const suggestedFocus = MARKET_FAMILIES
    .map((marketFamily) => {
      const summary = familySummary[marketFamily];
      const score = summary.trades === 0 ? 0 : summary.netTotalR / summary.trades;
      const positiveShare = positiveFamilyTotal > 0 ? Math.max(0, summary.netTotalR) / positiveFamilyTotal : 0;
      return {
        marketFamily,
        weight: Number(positiveShare.toFixed(4)),
        note: summary.netTotalR > 0
          ? `Positive net contribution from ${marketFamily} suggests more research capacity here.`
          : `Weak or negative ${marketFamily} contribution suggests deprioritizing this family until conditions improve.`,
        score
      };
    })
    .sort((left, right) => right.score - left.score)
    .map(({ score: _score, ...rest }) => rest);

  const tradeQuality = buildTradeQualityMetrics(trades);

  return {
    totalTrades: trades.length,
    wins,
    losses,
    winRate: trades.length === 0 ? 0 : wins / trades.length,
    totalR: netTotalR,
    averageR: trades.length === 0 ? 0 : netTotalR / trades.length,
    grossTotalR,
    grossAverageR: trades.length === 0 ? 0 : grossTotalR / trades.length,
    netTotalR,
    netAverageR: trades.length === 0 ? 0 : netTotalR / trades.length,
    frictionR,
    profitFactor: negative === 0 ? positive : positive / Math.abs(negative),
    maxDrawdownR,
    byStrategy: strategySummary,
    bySymbol: symbolSummary,
    byMarketFamily: familySummary,
    suggestedFocus,
    tradeQuality
  };
}

export function buildFamilyBudgetRecommendation(args: {
  trainSummary: SummaryReport;
  testSummary: SummaryReport;
  maxActiveFamilies?: number;
}): FamilyBudgetRecommendation {
  const { trainSummary, testSummary, maxActiveFamilies = 3 } = args;

  const rankedFamilies = MARKET_FAMILIES
    .map((marketFamily): FamilyBudgetEntry & { score: number } => {
      const train = trainSummary.byMarketFamily[marketFamily];
      const test = testSummary.byMarketFamily[marketFamily];
      const trainAvg = train.trades === 0 ? 0 : train.netTotalR / train.trades;
      const testAvg = test.trades === 0 ? 0 : test.netTotalR / test.trades;
      const combinedNetR = (train.netTotalR * 0.4) + (test.netTotalR * 0.6);
      const combinedAvg = (trainAvg * 0.4) + (testAvg * 0.6);
      const support = clamp01((train.trades + test.trades) / 8);
      const consistency = clamp01(1 - (Math.abs(trainAvg - testAvg) / (Math.abs(trainAvg) + Math.abs(testAvg) + 1)));
      const splitAlignment = train.netTotalR > 0 && test.netTotalR > 0
        ? 1.15
        : (train.netTotalR >= 0 || test.netTotalR >= 0 ? 0.9 : 0.4);
      const baseScore = Math.max(0, combinedAvg) * (0.4 + (0.6 * consistency)) * (0.5 + (0.5 * support)) * splitAlignment;
      const recoverySignal = (test.netTotalR > 0 && testAvg > 0 && test.trades >= 6)
        ? (testAvg * 0.35 * (0.5 + (0.5 * support)) * (0.5 + (0.5 * consistency)))
        : 0;
      const score = baseScore + recoverySignal;
      const confidence = clamp01((0.5 * consistency) + (0.5 * support));
      const note = score > 0
        ? (baseScore > 0
          ? `Positive and reasonably stable across train/test; keep ${marketFamily} active.`
          : `Test split is improving for ${marketFamily}; keep active at reduced confidence while monitoring stability.`)
        : `Weak or inconsistent ${marketFamily} contribution across train/test; keep it on watch only.`;

      return {
        marketFamily,
        trainNetR: Number(train.netTotalR.toFixed(2)),
        testNetR: Number(test.netTotalR.toFixed(2)),
        combinedNetR: Number(combinedNetR.toFixed(2)),
        weight: 0,
        confidence: Number(confidence.toFixed(4)),
        active: false,
        note,
        score
      };
    })
    .sort((left, right) => right.score - left.score);

  const totalScore = rankedFamilies.reduce((sum, entry) => sum + entry.score, 0);
  const preliminaryWeightedFamilies = rankedFamilies.map((entry) => {
    const weight = totalScore > 0 ? entry.score / totalScore : 0;
    return {
      ...entry,
      weight: Number(weight.toFixed(4)),
      active: weight > 0
    };
  });

  const activeFamilies = preliminaryWeightedFamilies
    .filter((entry) => entry.active)
    .slice(0, maxActiveFamilies)
    .map((entry) => entry.marketFamily);

  const activeWeightTotal = preliminaryWeightedFamilies
    .filter((entry) => activeFamilies.includes(entry.marketFamily))
    .reduce((sum, entry) => sum + entry.weight, 0);

  const weightedFamilies = preliminaryWeightedFamilies.map((entry) => {
    if (!activeFamilies.includes(entry.marketFamily) || activeWeightTotal <= 0) {
      return {
        ...entry,
        weight: 0,
        active: false
      };
    }

    return {
      ...entry,
      weight: Number((entry.weight / activeWeightTotal).toFixed(4)),
      active: true
    };
  });

  const targetWeights = Object.fromEntries(
    MARKET_FAMILIES.map((marketFamily) => {
      const entry = weightedFamilies.find((candidate) => candidate.marketFamily === marketFamily);
      return [marketFamily, entry ? entry.weight : 0];
    })
  ) as Record<MarketCategory, number>;

  return {
    activeFamilies,
    targetWeights,
    rankedFamilies: weightedFamilies.map(({ score: _score, ...entry }) => entry)
  };
}
