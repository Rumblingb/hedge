import { describe, expect, it } from "vitest";
import { buildNoEdgeLedger, mergeNoEdgeLedgers } from "../src/research/noEdgeLedger.js";
import type { PromotionGateResult } from "../src/engine/promotionGate.js";
import type { WalkforwardProfileResult } from "../src/engine/walkforward.js";

function profile(overrides: Partial<WalkforwardProfileResult> = {}): WalkforwardProfileResult {
  return {
    profileId: "session-momentum-index-core",
    description: "Session momentum profile.",
    trainSummary: {} as WalkforwardProfileResult["trainSummary"],
    testSummary: {
      totalTrades: 12,
      netTotalR: -1.5,
      maxDrawdownR: 2.1,
      tradeQuality: {
        expectancyR: -0.12
      }
    } as WalkforwardProfileResult["testSummary"],
    score: -1,
    scoreStability: 0.42,
    windowCount: 3,
    splitScores: [-1, -0.4, -0.8],
    familyBudget: {} as WalkforwardProfileResult["familyBudget"],
    ...overrides
  };
}

function gate(ready: boolean, failed: string[]): PromotionGateResult {
  return {
    ready,
    reasons: failed.map((name) => `${name} failed`),
    checks: failed.map((name) => ({
      name,
      passed: false,
      observed: 0,
      threshold: 1,
      direction: "min",
      reason: `${name} failed`
    }))
  };
}

describe("no-edge ledger", () => {
  it("records negative OOS profiles as no-edge memory for agents", () => {
    const artifact = buildNoEdgeLedger({
      generatedAt: "2026-05-06T00:00:00.000Z",
      runId: "strategy-factory-test",
      profiles: [profile()],
      gatesByProfileId: new Map([["session-momentum-index-core", gate(false, ["testNetR", "testExpectancyR"])]]),
      strategiesByProfileId: new Map([["session-momentum-index-core", ["session-momentum"]]])
    });

    expect(artifact.noEdgeCount).toBe(1);
    expect(artifact.blockedStrategies).toEqual(["session-momentum"]);
    expect(artifact.entries[0]?.nextAction).toContain("Do not re-promote");
    expect(artifact.learningSummary.join(" ")).toContain("negative evidence");
  });

  it("keeps thin samples in needs-more-data instead of calling them edge", () => {
    const artifact = buildNoEdgeLedger({
      generatedAt: "2026-05-06T00:00:00.000Z",
      runId: "strategy-factory-test",
      profiles: [
        profile({
          profileId: "ict-killzone-core",
          testSummary: {
            totalTrades: 2,
            netTotalR: 0.8,
            maxDrawdownR: 0.2,
            tradeQuality: {
              expectancyR: 0.4
            }
          } as WalkforwardProfileResult["testSummary"]
        })
      ],
      gatesByProfileId: new Map([["ict-killzone-core", gate(false, ["testTradeCount"])]]),
      strategiesByProfileId: new Map([["ict-killzone-core", ["ict-displacement"]]])
    });

    expect(artifact.needsMoreDataCount).toBe(1);
    expect(artifact.noEdgeCount).toBe(0);
    expect(artifact.blockedStrategies).toEqual([]);
  });

  it("merges sliced runs without forgetting older no-edge profiles", () => {
    const previous = buildNoEdgeLedger({
      generatedAt: "2026-05-01T00:00:00.000Z",
      runId: "previous",
      profiles: [
        profile({
          profileId: "old-core",
          testSummary: {
            totalTrades: 14,
            netTotalR: -3,
            maxDrawdownR: 3,
            tradeQuality: {
              expectancyR: -0.2
            }
          } as WalkforwardProfileResult["testSummary"]
        })
      ],
      gatesByProfileId: new Map([["old-core", gate(false, ["oldFailure"])]]),
      strategiesByProfileId: new Map([["old-core", ["session-momentum"]]])
    });
    const current = buildNoEdgeLedger({
      generatedAt: "2026-05-02T00:00:00.000Z",
      runId: "current",
      profiles: [
        profile({
          profileId: "new-slice",
          testSummary: {
            totalTrades: 14,
            netTotalR: -2,
            maxDrawdownR: 2,
            tradeQuality: {
              expectancyR: -0.1
            }
          } as WalkforwardProfileResult["testSummary"]
        })
      ],
      gatesByProfileId: new Map([["new-slice", gate(false, ["newFailure"])]]),
      strategiesByProfileId: new Map([["new-slice", ["vwap-reversion"]]])
    });

    const merged = mergeNoEdgeLedgers({ previous, current });

    expect(merged.count).toBe(2);
    expect(merged.noEdgeCount).toBe(2);
    expect(merged.blockedStrategies.sort()).toEqual(["session-momentum", "vwap-reversion"]);
  });
});
