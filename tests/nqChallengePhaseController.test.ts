import { describe, expect, it } from "vitest";
import { NQChallengePhaseController } from "../src/risk/challengePhaseController.js";

describe("NQChallengePhaseController", () => {
  it("keeps 50K challenge-live MNQ sizing aligned with the payout plan", () => {
    const controller = new NQChallengePhaseController("challenge-live");
    const profile = controller.getRiskProfile();
    const guardrails = controller.buildGuardrailOverrides();

    expect(profile.maxNqContracts).toBe(0);
    expect(profile.maxMnqContracts).toBe(8);
    expect(guardrails.maxContracts).toBe(8);
    expect(profile.dailyLossLock).toBe(350);
    expect(profile.dailyProfitLock).toBe(900);
  });

  it("keeps funded payout-defense smaller than challenge-live", () => {
    const controller = new NQChallengePhaseController("funded-payout-defense");
    const profile = controller.getRiskProfile();
    const guardrails = controller.buildGuardrailOverrides();

    expect(profile.maxNqContracts).toBe(0);
    expect(profile.maxMnqContracts).toBe(5);
    expect(guardrails.maxContracts).toBe(5);
    expect(profile.dailyLossLock).toBe(180);
    expect(profile.dailyProfitLock).toBe(300);
  });
});
