import { describe, expect, it } from "vitest";
import { buildPromotionStateFromPredictionReview } from "../src/promotion/state.js";
import { DEFAULT_PREDICTION_SOURCE_POLICY } from "../src/prediction/policy.js";

describe("promotion state", () => {
  it("recommends paper only when prediction review is ready", () => {
    const review = {
      ts: "2026-04-15T00:00:00.000Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 20, kalshi: 12 },
      counts: { reject: 0, watch: 2, "paper-trade": 1 },
      topCandidate: null,
      checks: [],
      blockers: [],
      recommendation: "queue for paper",
      readyForPaper: true
    };

    const state = buildPromotionStateFromPredictionReview({ review });
    expect(state.currentStage).toBe("research");
    expect(state.recommendedStage).toBe("paper");
    expect(state.blockers).toHaveLength(0);
  });
});
