import { describe, expect, it } from "vitest";
import { authorizePredictionExecution } from "../src/prediction/execution/authorization.js";
import { DEFAULT_PREDICTION_SOURCE_POLICY } from "../src/prediction/policy.js";

describe("prediction execution authorization", () => {
  it("refuses paper execution when the review is not ready", () => {
    expect(authorizePredictionExecution({
      mode: "paper",
      review: {
        ts: "2026-04-23T00:00:00.000Z",
        policy: DEFAULT_PREDICTION_SOURCE_POLICY,
        venueCounts: { polymarket: 20, kalshi: 12 },
        counts: { reject: 0, watch: 2, "paper-trade": 1 },
        topCandidate: null,
        checks: [],
        blockers: ["committee-watch"],
        recommendation: "stay in research",
        readyForPaper: false
      },
      promotion: {
        track: "prediction-markets",
        currentStage: "research",
        recommendedStage: "research",
        updatedAt: "2026-04-23T00:00:00.000Z",
        blockers: ["committee-watch"],
        approvalsRequired: [],
        checks: [],
        notes: []
      }
    })).toEqual({
      ok: false,
      reason: "prediction review is not ready for paper execution"
    });
  });

  it("refuses paper execution when promotion has not advanced to paper", () => {
    expect(authorizePredictionExecution({
      mode: "paper",
      review: {
        ts: "2026-04-23T00:00:00.000Z",
        policy: DEFAULT_PREDICTION_SOURCE_POLICY,
        venueCounts: { polymarket: 20, kalshi: 12 },
        counts: { reject: 0, watch: 0, "paper-trade": 1 },
        topCandidate: null,
        checks: [],
        blockers: [],
        recommendation: "queue for paper",
        readyForPaper: true
      },
      promotion: {
        track: "prediction-markets",
        currentStage: "research",
        recommendedStage: "research",
        updatedAt: "2026-04-23T00:00:00.000Z",
        blockers: ["operator-review-pending"],
        approvalsRequired: [],
        checks: [],
        notes: []
      }
    })).toEqual({
      ok: false,
      reason: "promotion state recommends research instead of paper"
    });
  });

  it("allows paper execution only when review and promotion both agree", () => {
    expect(authorizePredictionExecution({
      mode: "paper",
      review: {
        ts: "2026-04-23T00:00:00.000Z",
        policy: DEFAULT_PREDICTION_SOURCE_POLICY,
        venueCounts: { polymarket: 20, kalshi: 12 },
        counts: { reject: 0, watch: 0, "paper-trade": 1 },
        topCandidate: null,
        checks: [],
        blockers: [],
        recommendation: "queue for paper",
        readyForPaper: true
      },
      promotion: {
        track: "prediction-markets",
        currentStage: "research",
        recommendedStage: "paper",
        updatedAt: "2026-04-23T00:00:00.000Z",
        blockers: [],
        approvalsRequired: [],
        checks: [],
        notes: []
      }
    })).toEqual({
      ok: true,
      reason: null
    });
  });

  it("refuses live execution unless promotion is explicitly live", () => {
    expect(authorizePredictionExecution({
      mode: "live",
      review: {
        ts: "2026-04-23T00:00:00.000Z",
        policy: DEFAULT_PREDICTION_SOURCE_POLICY,
        venueCounts: { polymarket: 20, kalshi: 12 },
        counts: { reject: 0, watch: 0, "paper-trade": 1 },
        topCandidate: null,
        checks: [],
        blockers: [],
        recommendation: "queue for live",
        readyForPaper: true
      },
      promotion: {
        track: "prediction-markets",
        currentStage: "paper",
        recommendedStage: "paper",
        updatedAt: "2026-04-23T00:00:00.000Z",
        blockers: [],
        approvalsRequired: [],
        checks: [],
        notes: []
      }
    })).toEqual({
      ok: false,
      reason: "promotion state is not explicitly at live (current=paper, recommended=paper)"
    });
  });

  it("allows live execution only when review is ready and promotion is explicitly live", () => {
    expect(authorizePredictionExecution({
      mode: "live",
      review: {
        ts: "2026-04-23T00:00:00.000Z",
        policy: DEFAULT_PREDICTION_SOURCE_POLICY,
        venueCounts: { polymarket: 20, kalshi: 12 },
        counts: { reject: 0, watch: 0, "paper-trade": 1 },
        topCandidate: null,
        checks: [],
        blockers: [],
        recommendation: "queue for live",
        readyForPaper: true
      },
      promotion: {
        track: "prediction-markets",
        currentStage: "live",
        recommendedStage: "live",
        updatedAt: "2026-04-23T00:00:00.000Z",
        blockers: [],
        approvalsRequired: [],
        checks: [],
        notes: []
      }
    })).toEqual({
      ok: true,
      reason: null
    });
  });
});
