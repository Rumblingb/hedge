import type { SummaryReport, TradeRecord } from "../domain.js";

export function summarizeTrades(trades: TradeRecord[]): SummaryReport {
  let wins = 0;
  let losses = 0;
  let positive = 0;
  let negative = 0;
  let cumulativeR = 0;
  let peakR = 0;
  let maxDrawdownR = 0;
  const byStrategy = new Map<string, TradeRecord[]>();

  for (const trade of trades) {
    if (trade.rMultiple > 0) {
      wins += 1;
      positive += trade.rMultiple;
    } else if (trade.rMultiple < 0) {
      losses += 1;
      negative += trade.rMultiple;
    }

    cumulativeR += trade.rMultiple;
    peakR = Math.max(peakR, cumulativeR);
    maxDrawdownR = Math.max(maxDrawdownR, peakR - cumulativeR);

    const current = byStrategy.get(trade.strategyId) ?? [];
    current.push(trade);
    byStrategy.set(trade.strategyId, current);
  }

  const totalR = trades.reduce((sum, trade) => sum + trade.rMultiple, 0);
  const strategySummary = Object.fromEntries(
    Array.from(byStrategy.entries()).map(([strategyId, strategyTrades]) => {
      const total = strategyTrades.reduce((sum, trade) => sum + trade.rMultiple, 0);
      const strategyWins = strategyTrades.filter((trade) => trade.rMultiple > 0).length;
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

  return {
    totalTrades: trades.length,
    wins,
    losses,
    winRate: trades.length === 0 ? 0 : wins / trades.length,
    totalR,
    averageR: trades.length === 0 ? 0 : totalR / trades.length,
    profitFactor: negative === 0 ? positive : positive / Math.abs(negative),
    maxDrawdownR,
    byStrategy: strategySummary
  };
}
