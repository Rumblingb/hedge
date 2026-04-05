import { afterEach, describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";

function clearEnv(): void {
  delete process.env.RH_ACCOUNT_PHASE;
  delete process.env.RH_MAX_CONTRACTS;
  delete process.env.RH_MAX_TRADES_PER_DAY;
  delete process.env.RH_MAX_DAILY_LOSS_R;
}

afterEach(() => {
  clearEnv();
});

describe("phase-aware guardrail config", () => {
  it("uses challenge defaults when phase is unset", () => {
    const config = getConfig();

    expect(config.accountPhase).toBe("challenge");
    expect(config.guardrails.maxContracts).toBe(2);
    expect(config.guardrails.maxTradesPerDay).toBe(3);
    expect(config.guardrails.maxDailyLossR).toBe(2);
  });

  it("uses tighter funded defaults", () => {
    process.env.RH_ACCOUNT_PHASE = "funded";
    const config = getConfig();

    expect(config.accountPhase).toBe("funded");
    expect(config.guardrails.maxContracts).toBe(1);
    expect(config.guardrails.maxTradesPerDay).toBe(2);
    expect(config.guardrails.maxDailyLossR).toBe(1.25);
    expect(config.guardrails.maxConsecutiveLosses).toBe(1);
    expect(config.guardrails.minRr).toBe(2.8);
  });

  it("still allows explicit env overrides", () => {
    process.env.RH_ACCOUNT_PHASE = "funded";
    process.env.RH_MAX_CONTRACTS = "2";

    const config = getConfig();
    expect(config.guardrails.maxContracts).toBe(2);
  });
});
