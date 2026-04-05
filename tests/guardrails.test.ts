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

  it("rejects a trade whose max hold crosses the flat cutoff", () => {
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
        maxHoldMinutes: 15
      },
      timestamp: "2026-04-01T20:58:00.000Z",
      guardrails: config.guardrails,
      riskState: createInitialRiskState()
    });

    expect(decision.allowed).toBe(false);
    expect(decision.reasons).toContain("max hold crosses flat cutoff");
  });

  it("rejects a trade whose max hold crosses the blocked maintenance window", () => {
    const config = getConfig();
    const decision = evaluateSignalGuardrails({
      signal: {
        symbol: "6E",
        strategyId: "test",
        side: "long",
        entry: 100,
        stop: 99,
        target: 103,
        rr: 3,
        confidence: 0.8,
        contracts: 1,
        maxHoldMinutes: 20
      },
      timestamp: "2026-04-01T21:10:00.000Z",
      guardrails: {
        ...config.guardrails,
        sessionStartCt: "15:00",
        lastEntryCt: "16:30"
      },
      riskState: createInitialRiskState()
    });

    expect(decision.allowed).toBe(false);
    expect(decision.reasons).toContain("max hold crosses blocked window (topstep maintenance window)");
  });

  it("rejects an entry inside the blocked maintenance window", () => {
    const config = getConfig();
    const decision = evaluateSignalGuardrails({
      signal: {
        symbol: "6E",
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
      timestamp: "2026-04-01T21:25:00.000Z",
      guardrails: {
        ...config.guardrails,
        sessionStartCt: "15:00",
        lastEntryCt: "16:30"
      },
      riskState: createInitialRiskState()
    });

    expect(decision.allowed).toBe(false);
    expect(decision.reasons).toContain("entry inside blocked window (topstep maintenance window)");
  });
});
