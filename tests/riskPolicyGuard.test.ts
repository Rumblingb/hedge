import { describe, expect, it } from "vitest";
import { evaluateRiskPolicyGuard } from "../src/engine/riskPolicyGuard.js";

describe("risk policy guard", () => {
  it("passes the starter envelope when live execution is not armed", () => {
    const report = evaluateRiskPolicyGuard({
      env: {
        RH_LIVE_EXECUTION_ENABLED: "false",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "true",
        RH_TOPSTEP_READ_ONLY: "true",
        BILL_PREDICTION_EXECUTION_MODE: "paper",
        RH_MAX_CONTRACTS: "1",
        RH_MAX_TRADES_PER_DAY: "1",
        RH_MAX_DAILY_LOSS_R: "1",
        RH_MAX_CONSECUTIVE_LOSSES: "1"
      },
      now: () => "2026-05-06T12:00:00.000Z"
    });

    expect(report.status).toBe("pass");
    expect(report.blockers).toEqual([]);
  });

  it("blocks live arming and risk widening without approval", () => {
    const report = evaluateRiskPolicyGuard({
      env: {
        RH_LIVE_EXECUTION_ENABLED: "true",
        BILL_PREDICTION_EXECUTION_MODE: "live",
        RH_MAX_CONTRACTS: "2",
        RH_MAX_TRADES_PER_DAY: "4",
        RH_MAX_DAILY_LOSS_R: "2",
        RH_MAX_CONSECUTIVE_LOSSES: "2"
      },
      now: () => "2026-05-06T12:00:00.000Z"
    });

    expect(report.status).toBe("blocked");
    expect(report.blockers).toContain("risk-policy:futuresLiveApproval");
    expect(report.blockers).toContain("risk-policy:predictionLiveApproval");
    expect(report.blockers).toContain("risk-policy:starterMaxContracts");
  });

  it("allows explicitly approved Topstep demo-only exploration without live approval", () => {
    const report = evaluateRiskPolicyGuard({
      env: {
        RH_LIVE_EXECUTION_ENABLED: "true",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "true",
        BILL_FUTURES_DEMO_APPROVAL_ID: "demo-2026-05-06",
        RH_TOPSTEP_DEMO_ONLY: "true",
        RH_TOPSTEP_READ_ONLY: "false",
        BILL_PREDICTION_EXECUTION_MODE: "paper",
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
        RH_MAX_CONTRACTS: "1",
        RH_MAX_TRADES_PER_DAY: "4",
        RH_MAX_DAILY_LOSS_R: "2",
        RH_MAX_CONSECUTIVE_LOSSES: "2"
      },
      now: () => "2026-05-06T12:00:00.000Z"
    });

    expect(report.status).toBe("pass");
    expect(report.blockers).toEqual([]);
  });
});
