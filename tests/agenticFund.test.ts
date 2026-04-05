import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { buildAgenticFundReport } from "../src/engine/agenticFund.js";
import type { WalkforwardResearchResult } from "../src/engine/walkforward.js";
import type { PromotionGateResult } from "../src/engine/promotionGate.js";

function buildGate(ready: boolean): PromotionGateResult {
  return {
    ready,
    checks: [
      {
        name: "testTradeCount",
        passed: false,
        observed: 5,
        threshold: 8,
        direction: "min",
        reason: "Out-of-sample sample size is too small."
      },
      {
        name: "maxDrawdownR",
        passed: false,
        observed: 6,
        threshold: 4,
        direction: "max",
        reason: "Drawdown exceeds acceptable bound."
      }
    ],
    reasons: ["Out-of-sample sample size is too small.", "Drawdown exceeds acceptable bound."]
  };
}

function buildResearchResult(ready = false): WalkforwardResearchResult {
  const gate = buildGate(ready);
  return {
    profiles: [],
    winner: {
      profileId: "trend-only",
      description: "test",
      trainSummary: {
        totalTrades: 10,
        wins: 5,
        losses: 5,
        winRate: 0.5,
        totalR: -2,
        averageR: -0.2,
        grossTotalR: -1,
        grossAverageR: -0.1,
        netTotalR: -2,
        netAverageR: -0.2,
        frictionR: 1,
        profitFactor: 0.8,
        maxDrawdownR: 4,
        byStrategy: {},
        bySymbol: {},
        byMarketFamily: {
          index: { trades: 10, grossTotalR: -1, netTotalR: -2, averageR: -0.2, winRate: 0.5 },
          fx: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          energy: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          metal: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          bond: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          ag: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          crypto: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 }
        },
        suggestedFocus: [],
        tradeQuality: {
          expectancyR: -0.2,
          payoffRatio: 0.8,
          avgWinR: 0.9,
          avgLossR: -1,
          winRate: 0.5,
          lossRate: 0.5,
          maxConsecutiveWins: 2,
          maxConsecutiveLosses: 3,
          sharpePerTrade: -0.1,
          sortinoPerTrade: -0.1,
          ulcerIndexR: 2,
          cvar95TradeR: -1.2,
          riskOfRuinProb: 0.5
        }
      },
      testSummary: {
        totalTrades: 5,
        wins: 2,
        losses: 3,
        winRate: 0.4,
        totalR: -1,
        averageR: -0.2,
        grossTotalR: -0.8,
        grossAverageR: -0.16,
        netTotalR: -1,
        netAverageR: -0.2,
        frictionR: 0.2,
        profitFactor: 0.7,
        maxDrawdownR: 6,
        byStrategy: {},
        bySymbol: {},
        byMarketFamily: {
          index: { trades: 5, grossTotalR: -0.8, netTotalR: -1, averageR: -0.2, winRate: 0.4 },
          fx: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          energy: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          metal: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          bond: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          ag: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
          crypto: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 }
        },
        suggestedFocus: [],
        tradeQuality: {
          expectancyR: -0.2,
          payoffRatio: 0.8,
          avgWinR: 0.8,
          avgLossR: -1,
          winRate: 0.4,
          lossRate: 0.6,
          maxConsecutiveWins: 1,
          maxConsecutiveLosses: 3,
          sharpePerTrade: -0.2,
          sortinoPerTrade: -0.3,
          ulcerIndexR: 3,
          cvar95TradeR: -1.2,
          riskOfRuinProb: 0.6
        }
      },
      score: -2,
      scoreStability: 0.2,
      windowCount: 3,
      familyBudget: {
        activeFamilies: [],
        targetWeights: { index: 0, fx: 0, energy: 0, metal: 0, bond: 0, ag: 0, crypto: 0 },
        rankedFamilies: []
      }
    },
    recommendedFamilyBudget: {
      activeFamilies: [],
      targetWeights: { index: 0, fx: 0, energy: 0, metal: 0, bond: 0, ag: 0, crypto: 0 },
      rankedFamilies: []
    },
    promotionGate: gate,
    deployableWinner: null,
    deployableFamilyBudget: null,
    deployablePromotionGate: null
  };
}

describe("buildAgenticFundReport", () => {
  it("returns red status with actionable fixes on failed checks", () => {
    const config = getConfig();
    const report = buildAgenticFundReport({
      research: buildResearchResult(false),
      config
    });

    expect(report.status).toBe("yellow");
    expect(report.survivabilityScore).toBeLessThan(75);
    expect(report.issues.length).toBeGreaterThan(0);
    expect(report.learningActions.some((action) => action.id === "risk-tighten-core")).toBe(true);
  });

  it("returns deployable flags when winner is promotable", () => {
    const config = getConfig();
    const research = buildResearchResult(true);
    research.promotionGate = {
      ready: true,
      checks: [],
      reasons: []
    };
    research.deployableWinner = research.winner;
    research.deployableFamilyBudget = research.winner?.familyBudget ?? null;
    research.deployablePromotionGate = {
      ready: true,
      checks: [],
      reasons: []
    };

    const report = buildAgenticFundReport({ research, config });

    expect(report.deployableNow).toBe(true);
    expect(report.deployableProfileId).toBe("trend-only");
  });
});
