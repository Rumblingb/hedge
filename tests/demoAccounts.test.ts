import { describe, expect, it } from "vitest";
import { buildDemoAccountStrategyLanes, isDemoAccountLockSatisfied, listAllowedDemoAccounts } from "../src/live/demoAccounts.js";

describe("demo account helpers", () => {
  it("treats an allowlist without a pinned account as a valid demo lock", () => {
    expect(isDemoAccountLockSatisfied({
      enabled: false,
      allowedAccountIds: ["acct-1", "acct-2", "acct-3", "acct-4"],
      demoOnly: true,
      readOnly: true
    })).toBe(true);
  });

  it("builds one primary strategy lane per demo account", () => {
    const lanes = buildDemoAccountStrategyLanes({
      config: {
        enabled: false,
        allowedAccountIds: ["acct-1", "acct-2", "acct-3", "acct-4"],
        allowedAccountLabels: ["ORB", "Momentum", "Reversion", "ICT"],
        demoOnly: true,
        readOnly: true
      },
      enabledStrategies: [
        "opening-range-reversal",
        "session-momentum",
        "liquidity-reversion",
        "ict-displacement"
      ]
    });

    expect(lanes).toHaveLength(4);
    expect(lanes.map((lane) => lane.primaryStrategy)).toEqual([
      "opening-range-reversal",
      "session-momentum",
      "liquidity-reversion",
      "ict-displacement"
    ]);
    expect(listAllowedDemoAccounts({
      enabled: false,
      allowedAccountIds: ["acct-1", "acct-2", "acct-3", "acct-4"],
      allowedAccountLabels: ["ORB", "Momentum", "Reversion", "ICT"],
      demoOnly: true,
      readOnly: true
    }).map((account) => account.label)).toEqual(["ORB", "Momentum", "Reversion", "ICT"]);
  });
});
