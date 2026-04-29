import type { MarketCategory, SummaryReport } from "../domain.js";
import { getMarketCategory } from "../utils/markets.js";
import type { SymbolRegimeAssessment } from "./regime.js";

export interface StrategyCandidate {
  symbol: string;
  strategyId: string;
  marketFamily: MarketCategory;
  regime: SymbolRegimeAssessment["label"];
  directionalBias: SymbolRegimeAssessment["directionalBias"];
  expectedValueScore: number;
  regimeConfidence: number;
  strategyAverageR: number;
  symbolAverageR: number;
  strategyTrades: number;
  resilienceScore: number;
  convexityScore: number;
  familyActive: boolean;
  rationale: string[];
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function parseStrategyMetric(args: {
  summary: SummaryReport;
  symbol: string;
  strategyId: string;
}): {
  averageR: number;
  trades: number;
  winRate: number;
  profitFactor: number;
  payoffRatio: number;
  avgWinR: number;
  cvar95TradeR: number;
  riskOfRuinProb: number;
  maxConsecutiveLosses: number;
  sharpePerTrade: number;
  sortinoPerTrade: number;
} {
  const leafMatch = Object.entries(args.summary.byLeaf ?? {}).find(([key]) =>
    (key === `${args.symbol}:${args.strategyId}`)
    || (key.startsWith(`${args.symbol}:`) && key.endsWith(`:${args.strategyId}`))
  );
  if (leafMatch) {
    const [, value] = leafMatch;
    return {
      averageR: value.averageR,
      trades: value.trades,
      winRate: value.winRate,
      profitFactor: value.profitFactor,
      payoffRatio: value.payoffRatio,
      avgWinR: value.avgWinR,
      cvar95TradeR: value.cvar95TradeR,
      riskOfRuinProb: value.riskOfRuinProb,
      maxConsecutiveLosses: value.maxConsecutiveLosses,
      sharpePerTrade: value.sharpePerTrade,
      sortinoPerTrade: value.sortinoPerTrade
    };
  }

  const match = Object.entries(args.summary.byStrategy).find(([key]) => key.endsWith(`:${args.strategyId}`) || key === args.strategyId);
  if (!match) {
    return {
      averageR: 0,
      trades: 0,
      winRate: 0,
      profitFactor: 0,
      payoffRatio: 0,
      avgWinR: 0,
      cvar95TradeR: 0,
      riskOfRuinProb: 1,
      maxConsecutiveLosses: 0,
      sharpePerTrade: 0,
      sortinoPerTrade: 0
    };
  }

  const [, value] = match;
  return {
    averageR: value.averageR,
    trades: value.trades,
    winRate: value.winRate,
    profitFactor: value.profitFactor,
    payoffRatio: value.payoffRatio,
    avgWinR: value.avgWinR,
    cvar95TradeR: value.cvar95TradeR,
    riskOfRuinProb: value.riskOfRuinProb,
    maxConsecutiveLosses: value.maxConsecutiveLosses,
    sharpePerTrade: value.sharpePerTrade,
    sortinoPerTrade: value.sortinoPerTrade
  };
}

function strategyRegimeFit(args: {
  strategyId: string;
  regime: SymbolRegimeAssessment;
}): { score: number; note: string } {
  const { strategyId, regime } = args;
  const preferredIndex = regime.preferredStrategies.indexOf(strategyId);
  if (preferredIndex === 0) {
    return { score: 0.45, note: `${strategyId} is the primary fit for the detected ${regime.label} regime.` };
  }
  if (preferredIndex === 1) {
    return { score: 0.22, note: `${strategyId} is a secondary fit for the detected ${regime.label} regime.` };
  }

  if (regime.label === "range-chop" && strategyId === "session-momentum") {
    return { score: -0.35, note: "Momentum is penalized in a range-chop regime." };
  }

  if (regime.label.startsWith("trend") && strategyId === "opening-range-reversal") {
    return { score: -0.25, note: "Opening reversal is penalized on a clear trend regime." };
  }

  return { score: -0.15, note: `${strategyId} is not a preferred fit for the detected ${regime.label} regime.` };
}

function scoreResilience(args: {
  trades: number;
  profitFactor: number;
  sharpePerTrade: number;
  sortinoPerTrade: number;
  cvar95TradeR: number;
  riskOfRuinProb: number;
  maxConsecutiveLosses: number;
}): number {
  const support = clamp01(args.trades / 12);
  const profitFactor = clamp01((args.profitFactor - 1) / 1.5);
  const sharpe = clamp01((args.sharpePerTrade + 0.05) / 0.45);
  const sortino = clamp01((args.sortinoPerTrade + 0.05) / 0.55);
  const tailPenalty = clamp01((Math.abs(Math.min(0, args.cvar95TradeR)) - 1) / 0.75);
  const ruinPenalty = clamp01(args.riskOfRuinProb);
  const streakPenalty = clamp01((args.maxConsecutiveLosses - 1) / 4);

  return clamp01(
    (support * 0.25) +
    (profitFactor * 0.25) +
    (sharpe * 0.16) +
    (sortino * 0.14) +
    ((1 - ruinPenalty) * 0.2) -
    (tailPenalty * 0.12) -
    (streakPenalty * 0.08)
  );
}

function scoreConvexity(args: {
  avgWinR: number;
  payoffRatio: number;
  averageR: number;
}): number {
  const avgWin = clamp01((args.avgWinR - 2.2) / 1.8);
  const payoff = clamp01((args.payoffRatio - 1.1) / 1.7);
  const expectancy = clamp01(args.averageR / 0.6);
  return clamp01((avgWin * 0.45) + (payoff * 0.4) + (expectancy * 0.15));
}

function marketConditionAdjustment(args: {
  strategyId: string;
  regime: SymbolRegimeAssessment;
}): { score: number; note: string | null } {
  const { strategyId, regime } = args;
  const atr = Math.max(regime.features.atr, 0.0001);
  const trendEfficiency = Math.abs(regime.features.netMove) / Math.max(regime.features.sessionRange, 0.0001);
  const trendStrength = Math.abs(regime.features.netMove) / atr;
  const shockRatio = regime.features.sessionRange / atr;

  if (regime.label.startsWith("trend") && strategyId === "session-momentum") {
    const orderlyBonus = clamp01((trendEfficiency - 0.55) / 0.35) * 0.16;
    const strengthBonus = clamp01((trendStrength - 1.2) / 2.5) * 0.14;
    const shockPenalty = clamp01((shockRatio - 9) / 5) * 0.12;
    const score = orderlyBonus + strengthBonus - shockPenalty;
    return {
      score,
      note: score === 0
        ? null
        : `Managed-futures trend bonus ${score.toFixed(2)} from trend efficiency ${trendEfficiency.toFixed(2)} and shock ratio ${shockRatio.toFixed(2)}.`
    };
  }

  if (regime.label.startsWith("trend") && strategyId === "opening-range-reversal") {
    const penalty = clamp01((trendEfficiency - 0.5) / 0.3) * 0.16;
    return {
      score: -penalty,
      note: penalty === 0 ? null : `Trend persistence penalty ${penalty.toFixed(2)} makes reversal less attractive in a sustained directional regime.`
    };
  }

  if (regime.label === "range-chop" && strategyId === "liquidity-reversion") {
    const bonus = clamp01((1.1 - trendEfficiency) / 0.8) * 0.08;
    const shockPenalty = clamp01((shockRatio - 10) / 5) * 0.1;
    const score = bonus - shockPenalty;
    return {
      score,
      note: score === 0
        ? null
        : `Volatility-targeting adjustment ${score.toFixed(2)} from chop efficiency ${trendEfficiency.toFixed(2)} and shock ratio ${shockRatio.toFixed(2)}.`
    };
  }

  return { score: 0, note: null };
}

export function buildExpectedValueSurface(args: {
  summary: SummaryReport;
  enabledStrategies: string[];
  allowedSymbols: string[];
  activeFamilies: MarketCategory[];
  regimeAssessments: SymbolRegimeAssessment[];
}): StrategyCandidate[] {
  const { summary, enabledStrategies, allowedSymbols, activeFamilies, regimeAssessments } = args;
  const symbolSet = new Set(allowedSymbols);

  return regimeAssessments
    .filter((regime) => symbolSet.has(regime.symbol))
    .flatMap((regime) => {
      const symbolMetrics = summary.bySymbol[regime.symbol] ?? {
        trades: 0,
        grossTotalR: 0,
        netTotalR: 0,
        averageR: 0,
        winRate: 0
      };
      const marketFamily = getMarketCategory(regime.symbol);
      const familyActive = activeFamilies.includes(marketFamily);

      return enabledStrategies.map((strategyId) => {
        const strategyMetrics = parseStrategyMetric({
          summary,
          symbol: regime.symbol,
          strategyId
        });
        const fit = strategyRegimeFit({
          strategyId,
          regime
        });
        const marketAdjustment = marketConditionAdjustment({
          strategyId,
          regime
        });
        const activityBonus = Math.min(0.2, (strategyMetrics.trades / 12) * 0.2);
        const symbolActivityBonus = Math.min(0.15, (symbolMetrics.trades / 8) * 0.15);
        const familyBonus = familyActive ? 0.12 : -0.18;
        const resilienceScore = scoreResilience(strategyMetrics);
        const convexityScore = scoreConvexity(strategyMetrics);
        const riskPenalty = clamp01(strategyMetrics.riskOfRuinProb) * 0.55;
        const sparsePenalty = strategyMetrics.trades === 0
          ? 0.35
          : strategyMetrics.trades < 3
            ? 0.12
            : 0;
        const fragilityPenalty = strategyMetrics.averageR < 0 && resilienceScore < 0.35
          ? 0.18
          : 0;
        const evScore =
          (strategyMetrics.averageR * 0.3) +
          (symbolMetrics.averageR * 0.22) +
          familyBonus +
          activityBonus +
          symbolActivityBonus +
          (fit.score * Math.max(0.35, regime.confidence)) +
          marketAdjustment.score +
          (resilienceScore * 0.32) +
          (convexityScore * 0.28) -
          riskPenalty -
          sparsePenalty -
          fragilityPenalty;

        const rationale = [
          fit.note,
          `Strategy test average R: ${strategyMetrics.averageR.toFixed(4)} across ${strategyMetrics.trades} trades.`,
          `Symbol test average R: ${symbolMetrics.averageR.toFixed(4)} across ${symbolMetrics.trades} trades.`,
          `Resilience ${resilienceScore.toFixed(2)} with risk-of-ruin ${strategyMetrics.riskOfRuinProb.toFixed(2)} and CVaR95 ${strategyMetrics.cvar95TradeR.toFixed(2)}R.`,
          `Convexity ${convexityScore.toFixed(2)} from payoff ${strategyMetrics.payoffRatio.toFixed(2)} and avg win ${strategyMetrics.avgWinR.toFixed(2)}R.`,
          ...(marketAdjustment.note ? [marketAdjustment.note] : []),
          familyActive
            ? `${marketFamily} is active in the current family budget.`
            : `${marketFamily} is not active in the current family budget, so this candidate is discounted.`
        ];

        return {
          symbol: regime.symbol,
          strategyId,
          marketFamily,
          regime: regime.label,
          directionalBias: regime.directionalBias,
          expectedValueScore: Number(evScore.toFixed(4)),
          regimeConfidence: regime.confidence,
          strategyAverageR: Number(strategyMetrics.averageR.toFixed(4)),
          symbolAverageR: Number(symbolMetrics.averageR.toFixed(4)),
          strategyTrades: strategyMetrics.trades,
          resilienceScore: Number(resilienceScore.toFixed(4)),
          convexityScore: Number(convexityScore.toFixed(4)),
          familyActive,
          rationale
        } satisfies StrategyCandidate;
      });
    })
    .sort((left, right) =>
      right.expectedValueScore - left.expectedValueScore
      || right.resilienceScore - left.resilienceScore
      || right.convexityScore - left.convexityScore
    );
}
