import type { MarketCategory, SummaryReport, TradeRecord } from "../domain.js";
import { getMarketCategory } from "../utils/markets.js";

const MARKET_FAMILIES: MarketCategory[] = ["index", "fx", "energy", "metal", "bond", "ag", "crypto"];

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
    suggestedFocus
  };
}
