import type { SummaryReport, TradeRecord } from "../domain.js";

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
    bySymbol: symbolSummary
  };
}
