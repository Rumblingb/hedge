import { afterEach, describe, expect, it } from "vitest";
import { getConfig, redactConfigForDiagnostics } from "../src/config.js";

function clearEnv(): void {
  delete process.env.RH_ACCOUNT_PHASE;
  delete process.env.RH_MAX_CONTRACTS;
  delete process.env.RH_MAX_TRADES_PER_DAY;
  delete process.env.RH_MAX_DAILY_LOSS_R;
  delete process.env.RH_ENABLED_STRATEGIES;
  delete process.env.RH_TOPSTEP_USERNAME;
  delete process.env.RH_TOPSTEP_ACCOUNT_ID;
  delete process.env.RH_TOPSTEP_ALLOWED_ACCOUNT_ID;
  delete process.env.RH_TOPSTEP_ALLOWED_ACCOUNT_IDS;
  delete process.env.RH_TOPSTEP_ALLOWED_ACCOUNT_LABEL;
  delete process.env.RH_TOPSTEP_ALLOWED_ACCOUNT_LABELS;
  delete process.env.RH_TOPSTEP_API_KEY;
  delete process.env.RH_TOPSTEP_DEMO_ONLY;
  delete process.env.RH_TOPSTEP_READ_ONLY;
  delete process.env.RH_TOPSTEP_BASE_URL;
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
    expect(config.enabledStrategies).toEqual([
      "opening-range-reversal",
      "session-momentum",
      "liquidity-reversion",
      "ict-displacement"
    ]);
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

  it("defaults live integration to demo-only read-only posture and reads account locks", () => {
    process.env.RH_TOPSTEP_USERNAME = "demo-user";
    process.env.RH_TOPSTEP_ACCOUNT_ID = "acct-demo";
    process.env.RH_TOPSTEP_ALLOWED_ACCOUNT_ID = "acct-demo";
    process.env.RH_TOPSTEP_ALLOWED_ACCOUNT_LABEL = "Demo Test";

    const config = getConfig();

    expect(config.live.username).toBe("demo-user");
    expect(config.live.accountId).toBe("acct-demo");
    expect(config.live.allowedAccountId).toBe("acct-demo");
    expect(config.live.allowedAccountLabel).toBe("Demo Test");
    expect(config.live.demoOnly).toBe(true);
    expect(config.live.readOnly).toBe(true);
  });

  it("parses multiple demo accounts and enabled strategies from env", () => {
    process.env.RH_ENABLED_STRATEGIES = "opening-range-reversal,session-momentum,liquidity-reversion,ict-displacement";
    process.env.RH_TOPSTEP_ALLOWED_ACCOUNT_IDS = "acct-1,acct-2,acct-3,acct-4";
    process.env.RH_TOPSTEP_ALLOWED_ACCOUNT_LABELS = "ORB,Momentum,Reversion,ICT";

    const config = getConfig();

    expect(config.enabledStrategies).toEqual([
      "opening-range-reversal",
      "session-momentum",
      "liquidity-reversion",
      "ict-displacement"
    ]);
    expect(config.live.allowedAccountIds).toEqual(["acct-1", "acct-2", "acct-3", "acct-4"]);
    expect(config.live.allowedAccountLabels).toEqual(["ORB", "Momentum", "Reversion", "ICT"]);
    expect(config.live.accountId).toBeUndefined();
  });

  it("redacts API secrets in diagnostic config output", () => {
    process.env.RH_TOPSTEP_API_KEY = "super-secret-topstep";
    const config = getConfig();

    const redacted = redactConfigForDiagnostics(config);
    expect(redacted.live.apiKey).not.toBe("super-secret-topstep");
    expect(redacted.live.apiKey).toMatch(/^sup\*\*\*tep$/);
  });

  it("normalizes UI base URLs to the ProjectX API gateway", () => {
    process.env.RH_TOPSTEP_BASE_URL = "https://topstepx.com/trade";
    const config = getConfig();

    expect(config.live.baseUrl).toBe("https://api.thefuturesdesk.projectx.com");
  });
});
