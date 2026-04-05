import { describe, expect, it } from "vitest";
import { buildTopstepBracketOrderSpec } from "../src/adapters/topstep/topstepAdapter.js";
import type { StrategySignal } from "../src/domain.js";

describe("buildTopstepBracketOrderSpec", () => {
  it("builds a valid bracket spec for an allowed signal", () => {
    const signal: StrategySignal = {
      symbol: "NQ",
      strategyId: "wctc-ensemble:session-momentum",
      side: "long",
      entry: 18250,
      stop: 18240,
      target: 18280,
      rr: 3,
      confidence: 0.8,
      contracts: 1,
      maxHoldMinutes: 20
    };

    const order = buildTopstepBracketOrderSpec({
      signal,
      accountId: "acct-demo"
    });

    expect(order.side).toBe("buy");
    expect(order.quantity).toBe(1);
    expect(order.rr).toBe(3);
    expect(order.strategyTag).toContain("session-momentum");
  });

  it("rejects specs that violate hard RR bounds", () => {
    const signal: StrategySignal = {
      symbol: "NQ",
      strategyId: "wctc-ensemble:session-momentum",
      side: "short",
      entry: 18250,
      stop: 18260,
      target: 18245,
      rr: 1.2,
      confidence: 0.8,
      contracts: 1,
      maxHoldMinutes: 20
    };

    expect(() => buildTopstepBracketOrderSpec({
      signal,
      accountId: "acct-demo"
    })).toThrow(/minimum RR/);
  });
});
