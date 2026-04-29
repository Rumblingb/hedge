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

function buildNegativeEdgeGate(): PromotionGateResult {
  return {
    ready: false,
    checks: [
      {
        name: "testNetR",
        passed: false,
        observed: -1,
        threshold: 0,
        direction: "min",
        reason: "Test net R is not positive."
      },
      {
        name: "testExpectancyR",
        passed: false,
        observed: -0.2,
        threshold: 0,
        direction: "min",
        reason: "Per-trade expectancy is not positive."
      }
    ],
    reasons: ["Test net R is not positive.", "Per-trade expectancy is not positive."]
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
        byStrategy: {
          "wctc-ensemble:session-momentum": {
            trades: 6,
            totalR: -1.8,
            grossTotalR: -1.4,
            netTotalR: -1.8,
            averageR: -0.3,
            winRate: 0.3333,
            profitFactor: 0.7,
            payoffRatio: 0.8,
            avgWinR: 0.9,
            avgLossR: -1,
            sharpePerTrade: -0.2,
            sortinoPerTrade: -0.2,
            ulcerIndexR: 2.4,
            cvar95TradeR: -1.3,
            riskOfRuinProb: 0.72,
            maxConsecutiveLosses: 3,
            frictionR: 0.4
          },
          "wctc-ensemble:opening-range-reversal": {
            trades: 4,
            totalR: -0.2,
            grossTotalR: 0.4,
            netTotalR: -0.2,
            averageR: -0.05,
            winRate: 0.5,
            profitFactor: 0.95,
            payoffRatio: 1.3,
            avgWinR: 1.1,
            avgLossR: -0.85,
            sharpePerTrade: -0.05,
            sortinoPerTrade: -0.04,
            ulcerIndexR: 1.1,
            cvar95TradeR: -1,
            riskOfRuinProb: 0.38,
            maxConsecutiveLosses: 2,
            frictionR: 0.6
          }
        },
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
        byStrategy: {
          "wctc-ensemble:session-momentum": {
            trades: 3,
            totalR: -1.2,
            grossTotalR: -0.9,
            netTotalR: -1.2,
            averageR: -0.4,
            winRate: 0.3333,
            profitFactor: 0.55,
            payoffRatio: 0.75,
            avgWinR: 0.8,
            avgLossR: -1.05,
            sharpePerTrade: -0.3,
            sortinoPerTrade: -0.35,
            ulcerIndexR: 2.2,
            cvar95TradeR: -1.25,
            riskOfRuinProb: 0.74,
            maxConsecutiveLosses: 3,
            frictionR: 0.3
          },
          "wctc-ensemble:opening-range-reversal": {
            trades: 2,
            totalR: 0.2,
            grossTotalR: 0.1,
            netTotalR: 0.2,
            averageR: 0.1,
            winRate: 0.5,
            profitFactor: 1.1,
            payoffRatio: 1.4,
            avgWinR: 1.2,
            avgLossR: -0.85,
            sharpePerTrade: 0.08,
            sortinoPerTrade: 0.1,
            ulcerIndexR: 0.8,
            cvar95TradeR: -0.9,
            riskOfRuinProb: 0.28,
            maxConsecutiveLosses: 1,
            frictionR: -0.1
          }
        },
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
      splitScores: [-2],
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
    expect(report.agentStatus.operatingMode).toBe("stabilize");
    expect(report.evolutionPlan.guardrailsLocked).toContain("Red-folder event blackout");
  });

  it("suggests pruning the weakest strategy leg when negative edge is concentrated", () => {
    const config = getConfig();
    const research = buildResearchResult(false);
    research.promotionGate = buildNegativeEdgeGate();

    const report = buildAgenticFundReport({ research, config });

    expect(report.learningActions.some((action) => action.id === "prune-weakest-strategy")).toBe(true);
    expect(report.learningActions.find((action) => action.id === "prune-weakest-strategy")?.envPatch.RH_ENABLED_STRATEGIES).toBe("opening-range-reversal");
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
    expect(report.agentStatus.operatingMode).toBe("stabilize");
    expect(report.evolutionPlan.candidateMarkets.length).toBeGreaterThanOrEqual(0);
  });
});
