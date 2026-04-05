import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { createInitialRiskState, evaluateSignalGuardrails } from "../src/risk/guardrails.js";

describe("evaluateSignalGuardrails", () => {
  it("rejects a low RR trade", () => {
    const config = getConfig();
    const decision = evaluateSignalGuardrails({
      signal: {
        symbol: "NQ",
        strategyId: "test",
        side: "long",
        entry: 100,
        stop: 99,
        target: 101,
        rr: 1,
        confidence: 0.8,
        contracts: 1,
        maxHoldMinutes: 10
      },
      timestamp: "2026-04-01T14:00:00.000Z",
      guardrails: config.guardrails,
      riskState: createInitialRiskState()
    });

    expect(decision.allowed).toBe(false);
    expect(decision.reasons).toContain("rr below minimum");
  });

  it("rejects an entry after the session cutoff", () => {
    const config = getConfig();
    const decision = evaluateSignalGuardrails({
      signal: {
        symbol: "NQ",
        strategyId: "test",
        side: "long",
        entry: 100,
        stop: 99,
        target: 103,
        rr: 3,
        confidence: 0.8,
        contracts: 1,
        maxHoldMinutes: 10
      },
      timestamp: "2026-04-01T18:00:00.000Z",
      guardrails: config.guardrails,
      riskState: createInitialRiskState()
    });

    expect(decision.allowed).toBe(false);
    expect(decision.reasons).toContain("entry outside allowed CT session window");
  });
});
