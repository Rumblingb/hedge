import { describe, expect, it } from "vitest";
import { buildExpectedValueSurface } from "../src/engine/expectedValueSurface.js";
import type { SummaryReport } from "../src/domain.js";

function buildSummary(): SummaryReport {
  return {
    totalTrades: 12,
    wins: 6,
    losses: 6,
    winRate: 0.5,
    totalR: 2.4,
    averageR: 0.2,
    grossTotalR: 3.2,
    grossAverageR: 0.2667,
    netTotalR: 2.4,
    netAverageR: 0.2,
    frictionR: 0.8,
    profitFactor: 1.3,
    maxDrawdownR: 2.2,
    byStrategy: {
      "wctc-ensemble:session-momentum": {
        trades: 8,
        totalR: 1.6,
        grossTotalR: 2.1,
        netTotalR: 1.6,
        averageR: 0.2,
        winRate: 0.5,
        profitFactor: 1.15,
        payoffRatio: 1.2,
        avgWinR: 1.8,
        avgLossR: -1,
        sharpePerTrade: 0.12,
        sortinoPerTrade: 0.15,
        ulcerIndexR: 1.4,
        cvar95TradeR: -1.15,
        riskOfRuinProb: 0.42,
        maxConsecutiveLosses: 3,
        frictionR: 0.5
      },
      "wctc-ensemble:ict-displacement": {
        trades: 4,
        totalR: 2.2,
        grossTotalR: 2.5,
        netTotalR: 2.2,
        averageR: 0.55,
        winRate: 0.5,
        profitFactor: 1.9,
        payoffRatio: 2.4,
        avgWinR: 3.4,
        avgLossR: -1.1,
        sharpePerTrade: 0.42,
        sortinoPerTrade: 0.51,
        ulcerIndexR: 0.9,
        cvar95TradeR: -0.95,
        riskOfRuinProb: 0.14,
        maxConsecutiveLosses: 1,
        frictionR: 0.3
      }
    },
    byLeaf: {
      "NQ:wctc-ensemble:session-momentum": {
        trades: 5,
        totalR: 0.9,
        grossTotalR: 1.2,
        netTotalR: 0.9,
        averageR: 0.18,
        winRate: 0.4,
        profitFactor: 1.1,
        payoffRatio: 1.2,
        avgWinR: 1.7,
        avgLossR: -0.95,
        sharpePerTrade: 0.08,
        sortinoPerTrade: 0.1,
        ulcerIndexR: 1.5,
        cvar95TradeR: -1.2,
        riskOfRuinProb: 0.45,
        maxConsecutiveLosses: 3,
        frictionR: 0.3
      },
      "NQ:wctc-ensemble:ict-displacement": {
        trades: 3,
        totalR: 1.8,
        grossTotalR: 2,
        netTotalR: 1.8,
        averageR: 0.6,
        winRate: 0.6667,
        profitFactor: 2.1,
        payoffRatio: 2.5,
        avgWinR: 3.3,
        avgLossR: -1.1,
        sharpePerTrade: 0.45,
        sortinoPerTrade: 0.54,
        ulcerIndexR: 0.8,
        cvar95TradeR: -0.9,
        riskOfRuinProb: 0.12,
        maxConsecutiveLosses: 1,
        frictionR: 0.2
      }
    },
    bySymbol: {
      NQ: { trades: 8, grossTotalR: 2.7, netTotalR: 2.1, averageR: 0.2625, winRate: 0.5 },
      ES: { trades: 4, grossTotalR: 0.5, netTotalR: 0.3, averageR: 0.075, winRate: 0.5 }
    },
    byMarketFamily: {
      index: { trades: 12, grossTotalR: 3.2, netTotalR: 2.4, averageR: 0.2, winRate: 0.5 },
      fx: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      energy: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      metal: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      bond: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      ag: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      crypto: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 }
    },
    suggestedFocus: [],
    tradeQuality: {
      expectancyR: 0.2,
      payoffRatio: 1.4,
      avgWinR: 2.2,
      avgLossR: -1,
      winRate: 0.5,
      lossRate: 0.5,
      maxConsecutiveWins: 2,
      maxConsecutiveLosses: 2,
      sharpePerTrade: 0.2,
      sortinoPerTrade: 0.24,
      ulcerIndexR: 1.3,
      cvar95TradeR: -1,
      riskOfRuinProb: 0.25
    }
  };
}

describe("buildExpectedValueSurface", () => {
  it("prefers resilient convex strategies over shallow average-R candidates", () => {
    const surface = buildExpectedValueSurface({
      summary: buildSummary(),
      enabledStrategies: ["session-momentum", "ict-displacement"],
      allowedSymbols: ["NQ"],
      activeFamilies: ["index"],
      regimeAssessments: [
        {
          symbol: "NQ",
          marketFamily: "index",
          label: "trend-up",
          confidence: 0.72,
          directionalBias: "long",
          preferredStrategies: ["session-momentum", "ict-displacement"],
          note: "trend",
          features: {
            sessionBars: 200,
            sessionRange: 120,
            atr: 10,
            netMove: 80,
            closeLocation: 0.82,
            openingRangeWidth: 18
          }
        }
      ]
    });

    expect(surface[0]?.strategyId).toBe("ict-displacement");
    expect(surface[0]?.convexityScore).toBeGreaterThan(surface[1]?.convexityScore ?? 0);
    expect(surface[0]?.resilienceScore).toBeGreaterThan(surface[1]?.resilienceScore ?? 0);
  });

  it("uses symbol-specific leaf evidence before global strategy aggregates", () => {
    const summary = buildSummary();
    summary.byLeaf = {
      ...summary.byLeaf,
      "NQ:wctc-ensemble:session-momentum": {
        trades: 6,
        totalR: 2.7,
        grossTotalR: 3,
        netTotalR: 2.7,
        averageR: 0.45,
        winRate: 0.6667,
        profitFactor: 2,
        payoffRatio: 2.2,
        avgWinR: 2.8,
        avgLossR: -0.9,
        sharpePerTrade: 0.38,
        sortinoPerTrade: 0.44,
        ulcerIndexR: 0.9,
        cvar95TradeR: -0.85,
        riskOfRuinProb: 0.16,
        maxConsecutiveLosses: 1,
        frictionR: 0.3
      },
      "NQ:wctc-ensemble:ict-displacement": {
        trades: 4,
        totalR: -0.8,
        grossTotalR: -0.5,
        netTotalR: -0.8,
        averageR: -0.2,
        winRate: 0.25,
        profitFactor: 0.7,
        payoffRatio: 0.9,
        avgWinR: 1.1,
        avgLossR: -1.2,
        sharpePerTrade: -0.15,
        sortinoPerTrade: -0.18,
        ulcerIndexR: 1.8,
        cvar95TradeR: -1.35,
        riskOfRuinProb: 0.62,
        maxConsecutiveLosses: 3,
        frictionR: 0.3
      }
    };

    const surface = buildExpectedValueSurface({
      summary,
      enabledStrategies: ["session-momentum", "ict-displacement"],
      allowedSymbols: ["NQ"],
      activeFamilies: ["index"],
      regimeAssessments: [
        {
          symbol: "NQ",
          marketFamily: "index",
          label: "trend-up",
          confidence: 0.72,
          directionalBias: "long",
          preferredStrategies: ["session-momentum", "ict-displacement"],
          note: "trend",
          features: {
            sessionBars: 200,
            sessionRange: 120,
            atr: 10,
            netMove: 80,
            closeLocation: 0.82,
            openingRangeWidth: 18
          }
        }
      ]
    });

    expect(surface[0]?.strategyId).toBe("session-momentum");
    expect(surface[0]?.strategyAverageR).toBe(0.45);
  });

  it("adds a managed-futures style bonus to orderly trend momentum and penalizes reversal", () => {
    const surface = buildExpectedValueSurface({
      summary: buildSummary(),
      enabledStrategies: ["session-momentum", "opening-range-reversal"],
      allowedSymbols: ["NQ"],
      activeFamilies: ["index"],
      regimeAssessments: [
        {
          symbol: "NQ",
          marketFamily: "index",
          label: "trend-up",
          confidence: 0.78,
          directionalBias: "long",
          preferredStrategies: ["session-momentum", "ict-displacement"],
          note: "orderly trend",
          features: {
            sessionBars: 220,
            sessionRange: 30,
            atr: 8,
            netMove: 24,
            closeLocation: 0.88,
            openingRangeWidth: 10
          }
        }
      ]
    });

    expect(surface[0]?.strategyId).toBe("session-momentum");
    expect(surface[0]?.rationale.some((line) => line.includes("Managed-futures trend bonus"))).toBe(true);
    expect(surface[1]?.rationale.some((line) => line.includes("Trend persistence penalty"))).toBe(true);
  });
});
