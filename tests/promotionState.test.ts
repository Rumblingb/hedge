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

  it("demotes stale paper state when the latest review is not paper-ready", () => {
    const review = {
      ts: "2026-04-15T00:00:00.000Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 20, kalshi: 12 },
      counts: { reject: 4, watch: 0, "paper-trade": 0 },
      topCandidate: null,
      checks: [],
      blockers: ["no-paper-candidates"],
      recommendation: "stay in research",
      readyForPaper: false
    };

    const state = buildPromotionStateFromPredictionReview({
      review,
      prior: {
        track: "prediction-markets",
        currentStage: "paper",
        recommendedStage: "paper",
        updatedAt: "2026-04-14T00:00:00.000Z",
        blockers: [],
        approvalsRequired: ["operator-approval-for-demo", "operator-approval-for-live"],
        checks: [],
        notes: []
      }
    });

    expect(state.currentStage).toBe("research");
    expect(state.recommendedStage).toBe("research");
    expect(state.blockers).toEqual(["no-paper-candidates"]);
  });
});
