import { describe, expect, it } from "vitest";
import { evaluateResearchPromotion } from "../src/engine/promotionGate.js";
import type { FamilyBudgetRecommendation, SummaryReport } from "../src/domain.js";
import type { WalkforwardProfileResult } from "../src/engine/walkforward.js";

function buildSummary(overrides?: Partial<SummaryReport>): SummaryReport {
  return {
    totalTrades: 10,
    wins: 6,
    losses: 4,
    winRate: 0.6,
    totalR: 3,
    averageR: 0.3,
    grossTotalR: 3.5,
    grossAverageR: 0.35,
    netTotalR: 3,
    netAverageR: 0.3,
    frictionR: 0.5,
    profitFactor: 1.8,
    maxDrawdownR: 2,
    byStrategy: {},
    bySymbol: {},
    byMarketFamily: {
      index: { trades: 10, grossTotalR: 3.5, netTotalR: 3, averageR: 0.3, winRate: 0.6 },
      fx: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      energy: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      metal: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      bond: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      ag: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 },
      crypto: { trades: 0, grossTotalR: 0, netTotalR: 0, averageR: 0, winRate: 0 }
    },
    suggestedFocus: [],
    tradeQuality: {
      expectancyR: 0.3,
      payoffRatio: 1.2,
      avgWinR: 1,
      avgLossR: -0.8,
      winRate: 0.6,
      lossRate: 0.4,
      maxConsecutiveWins: 3,
      maxConsecutiveLosses: 2,
      sharpePerTrade: 0.4,
      sortinoPerTrade: 0.5,
      ulcerIndexR: 1.2,
      cvar95TradeR: -1,
      riskOfRuinProb: 0.2
    },
    ...overrides
  };
}

function buildFamilyBudget(active = true): FamilyBudgetRecommendation {
  return {
    activeFamilies: active ? ["index"] : [],
    targetWeights: {
      index: active ? 1 : 0,
      fx: 0,
      energy: 0,
      metal: 0,
      bond: 0,
      ag: 0,
      crypto: 0
    },
    rankedFamilies: []
  };
}

function buildWinner(overrides?: Partial<WalkforwardProfileResult>): WalkforwardProfileResult {
  const trainSummary = buildSummary();
  const testSummary = buildSummary();

  return {
    profileId: "balanced-wctc",
    description: "test",
    trainSummary,
    testSummary,
    score: 1.2,
    scoreStability: 0.8,
    windowCount: 3,
    familyBudget: buildFamilyBudget(true),
    ...overrides
  };
}

describe("evaluateResearchPromotion", () => {
  it("passes when metrics satisfy founder thresholds", () => {
    const result = evaluateResearchPromotion({
      winner: buildWinner(),
      recommendedFamilyBudget: buildFamilyBudget(true),
      phase: "challenge"
    });

    expect(result.ready).toBe(true);
    expect(result.reasons).toHaveLength(0);
  });

  it("fails when no active families and tail-risk is too high", () => {
    const riskySummary = buildSummary({
      tradeQuality: {
        ...buildSummary().tradeQuality,
        riskOfRuinProb: 0.7,
        cvar95TradeR: -2
      },
      netTotalR: -0.4,
      maxDrawdownR: 5
    });

    const result = evaluateResearchPromotion({
      winner: buildWinner({
        testSummary: riskySummary,
        scoreStability: 0.2
      }),
      recommendedFamilyBudget: buildFamilyBudget(false),
      phase: "challenge"
    });

    expect(result.ready).toBe(false);
    expect(result.reasons.length).toBeGreaterThan(1);
  });

  it("fails when out-of-sample trade count is too low", () => {
    const thinSummary = buildSummary({
      totalTrades: 3
    });

    const result = evaluateResearchPromotion({
      winner: buildWinner({
        testSummary: thinSummary
      }),
      recommendedFamilyBudget: buildFamilyBudget(true),
      phase: "challenge"
    });

    expect(result.ready).toBe(false);
    expect(result.reasons).toContain("Out-of-sample sample size is too small.");
  });

  it("applies stricter funded thresholds", () => {
    const borderline = buildSummary({
      maxDrawdownR: 3.5,
      tradeQuality: {
        ...buildSummary().tradeQuality,
        cvar95TradeR: -1.1,
        riskOfRuinProb: 0.3
      }
    });

    const challengeResult = evaluateResearchPromotion({
      winner: buildWinner({
        testSummary: borderline,
        scoreStability: 0.6
      }),
      recommendedFamilyBudget: buildFamilyBudget(true),
      phase: "challenge"
    });

    const fundedResult = evaluateResearchPromotion({
      winner: buildWinner({
        testSummary: borderline,
        scoreStability: 0.6
      }),
      recommendedFamilyBudget: buildFamilyBudget(true),
      phase: "funded"
    });

    expect(challengeResult.ready).toBe(true);
    expect(fundedResult.ready).toBe(false);
  });
});
