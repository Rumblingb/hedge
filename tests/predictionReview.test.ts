import { describe, expect, it } from "vitest";
import { buildPredictionCycleReview } from "../src/prediction/review.js";
import { DEFAULT_PREDICTION_SOURCE_POLICY } from "../src/prediction/policy.js";

describe("prediction review", () => {
  it("blocks paper promotion when required sources or candidates are missing", () => {
    const review = buildPredictionCycleReview({
      ts: "2026-04-15T00:00:00.000Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 100, manifold: 20 },
      counts: { reject: 0, watch: 0, "paper-trade": 0 },
      rows: []
    });

    expect(review.readyForPaper).toBe(false);
    expect(review.blockers).toContain("required-source-missing:kalshi");
    expect(review.blockers).toContain("no-paper-candidates");
  });
});
