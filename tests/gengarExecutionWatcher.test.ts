import { describe, expect, it } from "vitest";
import { evaluateGengarLiveExecutionGate } from "../src/prediction/gengarExecutionWatcher.js";

describe("evaluateGengarLiveExecutionGate", () => {
  it("does not treat default dry-run posture as live intent", () => {
    expect(evaluateGengarLiveExecutionGate({} as NodeJS.ProcessEnv)).toEqual({
      liveIntent: false,
      ok: false,
      failures: [
        "BILL_GENGAR_LIVE_EXECUTION_ENABLED must be exactly 'true'.",
        "BILL_PREDICTION_LIVE_EXECUTION_ENABLED must be exactly 'true'.",
        "BILL_PREDICTION_EXECUTION_MODE must be exactly 'live'.",
        "BILL_PREDICTION_LIVE_ACKNOWLEDGED must be exactly 'true' (founder dual-acknowledgement).",
        "BILL_PREDICTION_LIVE_MAX_STAKE must be a positive number.",
        "BILL_PREDICTION_BANKROLL_CURRENCY must be set (ISO 4217)."
      ]
    });
  });

  it("refuses live intent unless the full prediction live gate passes", () => {
    const gate = evaluateGengarLiveExecutionGate({
      BILL_GENGAR_LIVE_EXECUTION_ENABLED: "true",
      BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "true",
      BILL_PREDICTION_EXECUTION_MODE: "live",
      RH_MODE: "paper"
    } as NodeJS.ProcessEnv);

    expect(gate.liveIntent).toBe(true);
    expect(gate.ok).toBe(false);
    expect(gate.failures).toContain("BILL_PREDICTION_LIVE_ACKNOWLEDGED must be exactly 'true' (founder dual-acknowledgement).");
    expect(gate.failures).toContain("RH_MODE=paper is incompatible with live prediction execution — set RH_MODE=live explicitly.");
  });

  it("allows live only when Gengar and prediction live gates are both explicit", () => {
    expect(evaluateGengarLiveExecutionGate({
      BILL_GENGAR_LIVE_EXECUTION_ENABLED: "true",
      BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "true",
      BILL_PREDICTION_LIVE_ACKNOWLEDGED: "true",
      BILL_PREDICTION_LIVE_MAX_STAKE: "1",
      BILL_PREDICTION_BANKROLL_CURRENCY: "USD",
      BILL_PREDICTION_EXECUTION_MODE: "live",
      RH_MODE: "live"
    } as NodeJS.ProcessEnv)).toEqual({
      liveIntent: true,
      ok: true,
      failures: []
    });
  });
});
