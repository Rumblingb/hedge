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
  familyActive: boolean;
  rationale: string[];
}

function parseStrategyMetric(args: {
  summary: SummaryReport;
  strategyId: string;
}): { averageR: number; trades: number; winRate: number } {
  const match = Object.entries(args.summary.byStrategy).find(([key]) => key.endsWith(`:${args.strategyId}`) || key === args.strategyId);
  if (!match) {
    return { averageR: 0, trades: 0, winRate: 0 };
  }

  const [, value] = match;
  return {
    averageR: value.trades > 0 ? value.totalR / value.trades : 0,
    trades: value.trades,
    winRate: value.winRate
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
          strategyId
        });
        const fit = strategyRegimeFit({
          strategyId,
          regime
        });
        const activityBonus = Math.min(0.2, (strategyMetrics.trades / 12) * 0.2);
        const symbolActivityBonus = Math.min(0.15, (symbolMetrics.trades / 8) * 0.15);
        const familyBonus = familyActive ? 0.12 : -0.18;
        const evScore =
          (strategyMetrics.averageR * 0.45) +
          (symbolMetrics.averageR * 0.35) +
          familyBonus +
          activityBonus +
          symbolActivityBonus +
          (fit.score * Math.max(0.35, regime.confidence));

        const rationale = [
          fit.note,
          `Strategy test average R: ${strategyMetrics.averageR.toFixed(4)} across ${strategyMetrics.trades} trades.`,
          `Symbol test average R: ${symbolMetrics.averageR.toFixed(4)} across ${symbolMetrics.trades} trades.`,
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
          familyActive,
          rationale
        } satisfies StrategyCandidate;
      });
    })
    .sort((left, right) => right.expectedValueScore - left.expectedValueScore);
}
