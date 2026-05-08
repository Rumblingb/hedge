import { describe, expect, it } from "vitest";
import { buildPropFirmPayoutPlan, scorePropFirmCandidate, TOPSTEP_50K_PARAMETERS } from "../src/engine/propFirmPayout.js";
import type { StrategyCandidate } from "../src/engine/expectedValueSurface.js";

function candidate(overrides: Partial<StrategyCandidate> = {}): StrategyCandidate {
  return {
    symbol: "NQ",
    strategyId: "ict-displacement",
    marketFamily: "index",
    regime: "trend-up",
    directionalBias: "long",
    expectedValueScore: 0.55,
    regimeConfidence: 0.72,
    strategyAverageR: 0.22,
    symbolAverageR: 0.12,
    strategyTrades: 24,
    resilienceScore: 0.68,
    convexityScore: 0.55,
    familyActive: true,
    rationale: [],
    ...overrides
  };
}

describe("prop firm payout plan", () => {
  it("scores resilient ICT/FVG-style candidates as payout builders", async () => {
    const score = scorePropFirmCandidate(candidate({ strategyId: "ict-displacement" }));

    expect(score.laneRole).toBe("payout-builder");
    expect(score.maxContracts).toBe(1);
    expect(score.maxDailyTargetDollars).toBeLessThan(TOPSTEP_50K_PARAMETERS.combineBestDayRecommendation);
    expect(score.maxDailyLossDollars).toBeLessThan(TOPSTEP_50K_PARAMETERS.dailyLossLimit);

    const plan = await buildPropFirmPayoutPlan({
      candidates: [candidate({ strategyId: "ict-displacement" }), candidate({ strategyAverageR: -0.1, strategyTrades: 30 })],
      now: () => "2026-05-08T00:00:00.000Z"
    });

    expect(plan.posture).toBe("ready-to-demo");
    expect(plan.topCandidates[0].strategyId).toBe("ict-displacement");
    expect(plan.operatingRules.join(" ")).toContain("$150+");
  });

  it("rejects thin or negative candidates for payout work", () => {
    const score = scorePropFirmCandidate(candidate({
      strategyAverageR: -0.05,
      strategyTrades: 3,
      resilienceScore: 0.2
    }));

    expect(score.laneRole).toBe("reject");
    expect(score.blockers).toContain("non-positive-strategy-expectancy");
    expect(score.blockers).toContain("thin-trade-sample");
  });
});
