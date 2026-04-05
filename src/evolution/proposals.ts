import type { EvolutionProposal, LabConfig, TradeRecord } from "../domain.js";

function round(value: number): number {
  return Number(value.toFixed(2));
}

export function proposeEvolution(trades: TradeRecord[], config: LabConfig): EvolutionProposal[] {
  const proposals: EvolutionProposal[] = [];
  const recent = trades.slice(-30);

  if (recent.length === 0) {
    return proposals;
  }

  const losingTrades = recent.filter((trade) => trade.rMultiple < 0);
  const lossRate = losingTrades.length / recent.length;
  const avgR = recent.reduce((sum, trade) => sum + trade.rMultiple, 0) / recent.length;

  if (lossRate > 0.55 && config.guardrails.maxTradesPerDay > 1) {
    proposals.push({
      id: "tighten-max-trades",
      summary: "Reduce max trades per day by one",
      rationale: `Recent loss rate is ${round(lossRate * 100)}% across the last ${recent.length} trades.`,
      patch: {
        guardrails: {
          maxTradesPerDay: config.guardrails.maxTradesPerDay - 1
        }
      },
      impact: "tighten"
    });
  }

  if (avgR < 0 && config.guardrails.maxHoldMinutes > 10) {
    proposals.push({
      id: "tighten-hold-time",
      summary: "Reduce max hold time by 5 minutes",
      rationale: `Recent average R is ${round(avgR)}, suggesting exits are staying exposed too long.`,
      patch: {
        guardrails: {
          maxHoldMinutes: Math.max(10, config.guardrails.maxHoldMinutes - 5)
        }
      },
      impact: "tighten"
    });
  }

  if (avgR < 0.15) {
    proposals.push({
      id: "raise-news-threshold",
      summary: "Raise the high-impact news confidence threshold",
      rationale: `Recent average R is ${round(avgR)}. Tightening the news gate can reduce weak entries.`,
      patch: {
        guardrails: {
          newsProbabilityThreshold: Math.min(0.9, round(config.guardrails.newsProbabilityThreshold + 0.05))
        }
      },
      impact: "tighten"
    });
  }

  const byLeafStrategy = new Map<string, TradeRecord[]>();
  for (const trade of recent) {
    const leaf = trade.strategyId.split(":").pop() ?? trade.strategyId;
    const current = byLeafStrategy.get(leaf) ?? [];
    current.push(trade);
    byLeafStrategy.set(leaf, current);
  }

  for (const [strategyId, strategyTrades] of byLeafStrategy.entries()) {
    if (strategyTrades.length < 5) {
      continue;
    }

    const strategyWinRate = strategyTrades.filter((trade) => trade.rMultiple > 0).length / strategyTrades.length;
    const strategyTotalR = strategyTrades.reduce((sum, trade) => sum + trade.rMultiple, 0);

    if (strategyWinRate < 0.35 && strategyTotalR < 0 && config.enabledStrategies.includes(strategyId)) {
      proposals.push({
        id: `disable-${strategyId}`,
        summary: `Disable weak strategy ${strategyId}`,
        rationale: `${strategyId} posted ${round(strategyWinRate * 100)}% win rate and ${round(strategyTotalR)}R over ${strategyTrades.length} recent trades.`,
        patch: {
          enabledStrategies: config.enabledStrategies.filter((enabled) => enabled !== strategyId)
        },
        impact: "disable"
      });
    }
  }

  return proposals;
}
