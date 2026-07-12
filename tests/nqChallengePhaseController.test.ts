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

  it("sizes challenge-demo to the combine-clearing optimum (6 MNQ, DD-safe locks)", () => {
    // From combine_clear_probability.py: 6 MNQ minimizes expected days-to-pass-with-
    // restarts under a 12% trailing-DD bust cap. Micros (not NQ) for granular DD control.
    const controller = new NQChallengePhaseController("challenge-demo");
    const profile = controller.getRiskProfile();
    const guardrails = controller.buildGuardrailOverrides();

    expect(profile.maxNqContracts).toBe(0);
    expect(profile.maxMnqContracts).toBe(6);
    expect(guardrails.maxContracts).toBe(6);
    // daily loss lock must sit below the worst 2-consec-loss and inside the $2k trailing DD
    expect(profile.dailyLossLock).toBeLessThan(2000);
    expect(profile.dailyLossLock).toBe(800);
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
