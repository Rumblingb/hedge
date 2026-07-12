import { describe, expect, it } from "vitest";
import { DailyLock } from "../src/risk/dailyLock.js";

describe("DailyLock", () => {
  it("uses the funded payout-defense loss lock when recording funded trades", () => {
    const lock = new DailyLock();

    lock.recordTrade(-250, false, "payout-defense-test", "funded-payout-defense");

    const state = lock.getState();
    expect(state.lossLocked).toBe(true);
    expect(state.lockReason).toContain("loss");
  });

  it("does not apply the challenge-demo loss lock to funded trades", () => {
    const lock = new DailyLock();

    lock.recordTrade(-181, false, "payout-defense-test", "funded-payout-defense");

    expect(lock.getState().lossLocked).toBe(true);
  });
});
