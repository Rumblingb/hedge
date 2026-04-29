import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runAgenticImprovementLoop, runAgenticImprovementLoopWithEvaluator } from "../src/engine/agenticLoop.js";
import { NoopNewsGate } from "../src/news/base.js";
import { collectResearchUniverse } from "../src/research/profiles.js";

function buildResearchWithStrategyMix(enabledStrategies: string[]): any {
  const includesWeakLeg = enabledStrategies.includes("ict-displacement");
  const negativeNet = includesWeakLeg ? -1.4 : 1.1;
  const expectancy = includesWeakLeg ? -0.2 : 0.35;

  return {
    profiles: [
      {
        profileId: "strategy-mix",
        description: "Synthetic strategy-mix profile.",
        score: 1,
        scoreStability: 0.8,
        windowCount: 1,
        splitScores: [1],
        familyBudget: {
          mode: "active",
          activeFamilies: ["index"],
          rankedFamilies: [],
          targetWeights: {},
          reasons: []
        },
        trainSummary: {
          totalTrades: 10,
          wins: 5,
          losses: 5,
          winRate: 0.5,
          totalR: 0.2,
          averageR: 0.02,
          maxDrawdownR: 0.8,
          grossToNetRetention: 0.9,
          bySymbol: {},
          byStrategy: {},
          byMarketFamily: {},
          grossTotalR: 0.5,
          netTotalR: 0.2,
          frictionR: 0.3,
          profitFactor: 1.05,
          tradeQuality: {
            expectancyR: 0.02,
            payoffRatio: 1.3,
            avgWinR: 1.1,
            avgLossR: -0.8,
            winRate: 0.5,
            lossRate: 0.5,
            maxConsecutiveWins: 2,
            maxConsecutiveLosses: 2,
            sharpePerTrade: 0.3,
            sortinoPerTrade: 0.35,
            ulcerIndexR: 0.2,
            cvar95TradeR: -0.7,
            riskOfRuinProb: 0.06
          }
        },
        testSummary: {
          totalTrades: 6,
          wins: 2,
          losses: 4,
          winRate: 0.3333,
          totalR: negativeNet,
          averageR: Number((negativeNet / 6).toFixed(4)),
          maxDrawdownR: 1.2,
          grossToNetRetention: 0.82,
          bySymbol: {},
          byStrategy: {
            "profile:opening-range-reversal": {
              trades: 3,
              totalR: 0.9,
              averageR: 0.3,
              riskOfRuinProb: 0.08
            },
            "profile:ict-displacement": {
              trades: includesWeakLeg ? 3 : 0,
              totalR: includesWeakLeg ? -2.3 : 0,
              averageR: includesWeakLeg ? -0.7667 : 0,
              riskOfRuinProb: includesWeakLeg ? 0.42 : 0
            }
          },
          byMarketFamily: {},
          grossTotalR: includesWeakLeg ? -0.8 : 1.4,
          netTotalR: negativeNet,
          frictionR: 0.6,
          profitFactor: includesWeakLeg ? 0.8 : 1.2,
          tradeQuality: {
            expectancyR: expectancy,
            payoffRatio: 1.1,
            avgWinR: 1,
            avgLossR: -0.9,
            winRate: 0.3333,
            lossRate: 0.6667,
            maxConsecutiveWins: 1,
            maxConsecutiveLosses: 3,
            sharpePerTrade: includesWeakLeg ? -0.2 : 0.45,
            sortinoPerTrade: includesWeakLeg ? -0.15 : 0.5,
            ulcerIndexR: 0.5,
            cvar95TradeR: -1.1,
            riskOfRuinProb: includesWeakLeg ? 0.21 : 0.08
          }
        }
      }
    ],
    winner: null as any,
    recommendedFamilyBudget: {
      mode: "active",
      activeFamilies: ["index"],
      rankedFamilies: [],
      targetWeights: {},
      reasons: []
    },
    promotionGate: {
      ready: false,
      checks: [
        { name: "testNetR", passed: !includesWeakLeg, expected: "> 0", actual: negativeNet },
        { name: "testExpectancyR", passed: !includesWeakLeg, expected: "> 0", actual: expectancy }
      ],
      reasons: includesWeakLeg ? ["negative expectancy"] : []
    },
    deployableWinner: null,
    deployableFamilyBudget: null,
    deployablePromotionGate: null
  };
}

describe("runAgenticImprovementLoop", () => {
  it("returns baseline and tuned reports with an applied patch object", async () => {
    const config = getConfig();
    const bars = generateSyntheticBars({
      symbols: collectResearchUniverse(config),
      days: 5,
      seed: 41
    });

    const result = await runAgenticImprovementLoop({
      baseConfig: config,
      bars,
      newsGate: new NoopNewsGate()
    });

    expect(result).toHaveProperty("baseline.report.survivabilityScore");
    expect(result).toHaveProperty("tuned.report.survivabilityScore");
    expect(result).toHaveProperty("appliedPatch");
    expect(result).toHaveProperty("delta.survivabilityScore");
    expect(result.tuned.config.guardrails.maxContracts).toBeLessThanOrEqual(config.guardrails.maxContracts);
    expect(result.tuned.config.guardrails.maxTradesPerDay).toBeLessThanOrEqual(config.guardrails.maxTradesPerDay);
    expect(result.tuned.config.guardrails.maxDailyLossR).toBeLessThanOrEqual(config.guardrails.maxDailyLossR);
  }, 50000);

  it("reuses the baseline research when no patch changes are available", async () => {
    const config = getConfig();
    let evaluations = 0;

    const result = await runAgenticImprovementLoopWithEvaluator({
      baseConfig: config,
      evaluateResearch: async () => {
        evaluations += 1;
        return {
          profiles: [
            {
              profileId: "noop-profile",
              description: "No-op profile.",
              score: 1,
              scoreStability: 1,
              windowCount: 1,
              splitScores: [1],
              familyBudget: {
                mode: "paused",
                activeFamilies: [],
                rankedFamilies: [],
                targetWeights: {},
                reasons: []
              },
              trainSummary: {
                totalTrades: 0,
                wins: 0,
                losses: 0,
                winRate: 0,
                totalR: 0,
                averageR: 0,
                maxDrawdownR: 0,
                grossToNetRetention: 1,
                bySymbol: {},
                byStrategy: {},
                byMarketFamily: {},
                grossTotalR: 0,
                netTotalR: 0,
                frictionR: 0,
                profitFactor: 0,
                tradeQuality: {
                  expectancyR: 0,
                  payoffRatio: 0,
                  avgWinR: 0,
                  avgLossR: 0,
                  winRate: 0,
                  lossRate: 0,
                  maxConsecutiveWins: 0,
                  maxConsecutiveLosses: 0,
                  sharpePerTrade: 0,
                  sortinoPerTrade: 0,
                  ulcerIndexR: 0,
                  cvar95TradeR: 0,
                  riskOfRuinProb: 0
                }
              },
              testSummary: {
                totalTrades: 0,
                wins: 0,
                losses: 0,
                winRate: 0,
                totalR: 0,
                averageR: 0,
                maxDrawdownR: 0,
                grossToNetRetention: 1,
                bySymbol: {},
                byStrategy: {},
                byMarketFamily: {},
                grossTotalR: 0,
                netTotalR: 0,
                frictionR: 0,
                profitFactor: 0,
                tradeQuality: {
                  expectancyR: 0,
                  payoffRatio: 0,
                  avgWinR: 0,
                  avgLossR: 0,
                  winRate: 0,
                  lossRate: 0,
                  maxConsecutiveWins: 0,
                  maxConsecutiveLosses: 0,
                  sharpePerTrade: 0,
                  sortinoPerTrade: 0,
                  ulcerIndexR: 0,
                  cvar95TradeR: 0,
                  riskOfRuinProb: 0
                }
              }
            }
          ],
          winner: null,
          recommendedFamilyBudget: null,
          promotionGate: null,
          deployableWinner: null,
          deployableFamilyBudget: null,
          deployablePromotionGate: null
        } as any;
      }
    });

    expect(evaluations).toBe(1);
    expect(result.reusedBaseline).toBe(true);
    expect(result.delta.survivabilityScore).toBe(0);
  });

  it("applies strategy-pruning patches when the weakest leg is dragging net edge", async () => {
    const config = getConfig();
    let evaluations = 0;

    const result = await runAgenticImprovementLoopWithEvaluator({
      baseConfig: config,
      evaluateResearch: async (candidateConfig) => {
        evaluations += 1;
        const research = buildResearchWithStrategyMix(candidateConfig.enabledStrategies);
        research.winner = research.profiles[0];
        return research;
      }
    });

    expect(evaluations).toBe(2);
    expect(result.reusedBaseline).toBe(false);
    expect(result.appliedPatch.RH_ENABLED_STRATEGIES).toBe("opening-range-reversal");
    expect(result.tuned.config.enabledStrategies).toEqual(["opening-range-reversal"]);
    expect(result.tuned.report.profitableNow).toBe(true);
  });
});
