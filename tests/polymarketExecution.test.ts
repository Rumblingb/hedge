import { describe, expect, it } from "vitest";
import { toExecutionSignal } from "../src/prediction/polymarketExecution.js";

describe("polymarketExecution", () => {
  it("uses executable ask and explicit token id when present", () => {
    const exec = toExecutionSignal({
      side: "DOWN",
      tokenId: "explicit-token",
      tokenDown: "down-token",
      prob: 0.82,
      edge: 0.08,
      marketPrice: 0.70,
      executablePrice: 0.74,
      deltaBps: -0.12,
      kellyFraction: 0.05,
      recommendedBet: 5,
      secondsRemaining: 90,
    });

    expect(exec).not.toBeNull();
    expect(exec?.tokenId).toBe("explicit-token");
    expect(exec?.signal.marketPrice).toBe(0.74);
  });

  it("falls back to best ask before legacy market price", () => {
    const exec = toExecutionSignal({
      side: "UP",
      tokenUp: "up-token",
      prob: 0.84,
      edge: 0.07,
      marketPrice: 0.72,
      bestAsk: 0.76,
      deltaBps: 0.13,
      kellyFraction: 0.05,
      recommendedBet: 5,
      secondsRemaining: 80,
    });

    expect(exec?.tokenId).toBe("up-token");
    expect(exec?.signal.marketPrice).toBe(0.76);
  });

  it("rejects invalid executable prices", () => {
    expect(toExecutionSignal({
      side: "UP",
      tokenUp: "up-token",
      marketPrice: 1,
    })).toBeNull();
  });
});
