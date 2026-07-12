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

  it("rejects when trailing max drawdown lock is active", () => {
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
      timestamp: "2026-04-01T14:00:00.000Z",
      guardrails: {
        ...config.guardrails,
        trailingMaxDrawdownR: 2
      },
      riskState: {
        tradeCount: 0,
        realizedR: -2.2,
        peakRealizedR: 0.5,
        consecutiveLosses: 0
      }
    });

    expect(decision.allowed).toBe(false);
    expect(decision.reasons).toContain("trailing max drawdown lock active");
  });

  it("rejects trades during a red-folder blackout window", () => {
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
      timestamp: "2026-04-01T13:55:00.000Z",
      guardrails: config.guardrails,
      riskState: createInitialRiskState(),
      news: {
        provider: "mock-news-gate",
        direction: "flat",
        probability: 0.5,
        impact: "high",
        reason: "red-folder event",
        blackout: {
          active: true,
          eventTs: "2026-04-01T14:00:00.000Z",
          minutesBefore: 15,
          minutesAfter: 30,
          label: "nonfarm payrolls"
        }
      }
    });

    expect(decision.allowed).toBe(false);
    expect(decision.reasons).toContain("red-folder news blackout window (nonfarm payrolls 2026-04-01T14:00:00.000Z)");
  });

  it("allows the 50K MNQ challenge cap while keeping NQ capped tighter", () => {
    const config = getConfig();
    const baseSignal = {
      strategyId: "50k-sizing-policy",
      side: "long" as const,
      entry: 100,
      stop: 99,
      target: 103,
      rr: 3,
      confidence: 0.8,
      maxHoldMinutes: 10
    };
    const guardrails = {
      ...config.guardrails,
      allowedSymbols: ["NQ", "MNQ"],
      maxContracts: 8
    };

    const mnqDecision = evaluateSignalGuardrails({
      signal: {
        ...baseSignal,
        symbol: "MNQ",
        contracts: 8
      },
      timestamp: "2026-04-01T14:00:00.000Z",
      guardrails,
      riskState: createInitialRiskState()
    });
    const nqDecision = evaluateSignalGuardrails({
      signal: {
        ...baseSignal,
        symbol: "NQ",
        contracts: 2
      },
      timestamp: "2026-04-01T14:00:00.000Z",
      guardrails,
      riskState: createInitialRiskState()
    });

    expect(mnqDecision.allowed).toBe(true);
    expect(nqDecision.allowed).toBe(false);
    expect(nqDecision.reasons).toContain("contracts exceed hard limit (2 > 1 for NQ)");
  });
});
