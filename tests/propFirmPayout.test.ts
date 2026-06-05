import { describe, expect, it } from "vitest";
import { buildPropFirmPayoutPlan, hasCurrentTopstep50KPolicy, migratePropFirmPayoutPlanPolicy, scorePropFirmCandidate, TOPSTEP_50K_PARAMETERS } from "../src/engine/propFirmPayout.js";
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
    expect(plan.operatingRules.join(" ")).toContain("proposals only");
    expect(plan.challengePath.objective).toBe("pass-combine");
    expect(plan.challengePath.preferredFundedPath).toBe("xfa-standard");
    expect(plan.challengePath.dailyNetTargetRange[1]).toBeLessThan(TOPSTEP_50K_PARAMETERS.combineBestDayRecommendation);
    expect(TOPSTEP_50K_PARAMETERS.xfaConsistencyMaxLargestDayPct).toBe(0.4);
    expect(TOPSTEP_50K_PARAMETERS.xfaStandardMaxPayoutCap).toBe(2000);
    expect(TOPSTEP_50K_PARAMETERS.xfaConsistencyMaxPayoutCap).toBe(3000);
    expect(plan.riskModes.challenge.executionInstrument).toBe("MNQ");
    expect(plan.riskModes.challenge.activationStatus).toBe("proposal-only-until-risk-policy-clears");
    expect(plan.riskModes.challenge.activePolicyRule).toContain("risk-policy max contracts");
    expect(plan.riskModes.challenge.tradeMath.targetTicks).toBe(80);
    expect(plan.riskModes.challenge.tradeMath.grossWinPerTrade).toBe(320);
    expect(plan.riskModes.challenge.dailyProfitLock).toBeLessThan(TOPSTEP_50K_PARAMETERS.combineBestDayRecommendation);
    expect(plan.riskModes.funded.executionInstrument).toBe("MNQ");
    expect(plan.riskModes.funded.activationStatus).toBe("proposal-only-until-risk-policy-clears");
    expect(plan.riskModes.funded.tradeMath.grossWinPerTrade).toBeGreaterThan(150);
    expect(plan.riskModes.funded.dailyLossLock).toBeLessThan(plan.riskModes.challenge.dailyLossLock);
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

  it("migrates legacy candidate-backed plans without keeping stale payout rules", () => {
    const legacy = {
      command: "prop-firm-payout-plan",
      account: {
        xfaStandardMaxPayoutCap: 5000,
        xfaConsistencyMaxPayoutCap: 6000
      },
      challengePath: {
        preferredFundedPath: "xfa-consistency"
      },
      riskModes: {
        challenge: { executionInstrument: "NQ" },
        funded: { executionInstrument: "MNQ" }
      },
      candidateCount: 1,
      topCandidates: [scorePropFirmCandidate(candidate({ strategyId: "legacy-payout-builder" }))]
    };

    expect(hasCurrentTopstep50KPolicy(legacy)).toBe(false);
    const migrated = migratePropFirmPayoutPlanPolicy(legacy, () => "2026-06-02T00:00:00.000Z");

    expect(hasCurrentTopstep50KPolicy(migrated)).toBe(true);
    expect(migrated.candidateCount).toBe(1);
    expect(migrated.topCandidates[0].strategyId).toBe("legacy-payout-builder");
    expect(migrated.account.xfaStandardMaxPayoutCap).toBe(2000);
    expect(migrated.challengePath.preferredFundedPath).toBe("xfa-standard");
    expect(migrated.riskModes.challenge.executionInstrument).toBe("MNQ");
    expect(migrated.riskModes.challenge.activationStatus).toBe("proposal-only-until-risk-policy-clears");
  });

  it("treats plans without explicit proposal-only sizing status as stale", () => {
    const stale = migratePropFirmPayoutPlanPolicy({
      command: "prop-firm-payout-plan",
      account: TOPSTEP_50K_PARAMETERS,
      challengePath: { preferredFundedPath: "xfa-standard" },
      riskModes: {
        challenge: { executionInstrument: "MNQ" },
        funded: { executionInstrument: "MNQ" }
      },
      candidateCount: 1,
      topCandidates: [scorePropFirmCandidate(candidate({ strategyId: "legacy-payout-builder" }))]
    });

    expect(hasCurrentTopstep50KPolicy({
      ...stale,
      riskModes: {
        challenge: { executionInstrument: "MNQ" },
        funded: { executionInstrument: "MNQ" }
      }
    })).toBe(false);
  });
});
