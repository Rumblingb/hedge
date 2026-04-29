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

  it("adds committee context for a valid but non-paperable top candidate", () => {
    const review = buildPredictionCycleReview({
      ts: "2026-04-15T00:00:00.000Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 100, kalshi: 100, manifold: 20 },
      counts: { reject: 0, watch: 1, "paper-trade": 0 },
      recentCycles: [
        {
          review: {
            topCandidate: {
              candidateId: "polymarket:1919425__manifold:ghI9lZO0CP",
              verdict: "watch",
              grossEdgePct: 1.1,
              netEdgePct: -3.4,
              edgeShortfallPct: 3.4
            }
          }
        },
        {
          review: {
            topCandidate: {
              candidateId: "polymarket:1919425__manifold:ghI9lZO0CP",
              verdict: "watch",
              grossEdgePct: 2.1,
              netEdgePct: -2.4,
              edgeShortfallPct: 2.4
            }
          }
        }
      ],
      rows: [
        {
          ts: "2026-04-15T00:00:00.000Z",
          candidateId: "polymarket:1919425__manifold:ghI9lZO0CP",
          venueA: "polymarket",
          venueB: "manifold",
          marketType: "binary",
          normalizedEventKey: "by deal iran peace permanent us",
          normalizedQuestionKey: "by deal iran may peace permanent us",
          normalizedOutcomeKey: "yes",
          eventTitleA: "US x Iran permanent peace deal by...?",
          eventTitleB: "US x Iran permanent peace deal by May 31? [Polymarket]",
          outcomeA: "Yes",
          outcomeB: "Yes",
          expiryA: "2026-05-31T00:00:00Z",
          expiryB: "2026-05-31T23:59:00.000Z",
          settlementCompatible: true,
          matchScore: 0.83,
          entityOverlap: 0.63,
          questionOverlap: 0.88,
          grossEdgePct: 0.5,
          netEdgePct: -4,
          feeDragPct: 4.5,
          displayedSizeA: 128940.3387,
          displayedSizeB: 3689.8991,
          sizeVerdict: "ok",
          verdict: "watch",
          reasons: ["negative-net-edge", "subscale-edge"],
          sizing: {
            action: "buy-cheaper-venue",
            venue: "manifold",
            entryPrice: 0.53,
            referenceVenue: "polymarket",
            referencePrice: 0.535,
            consensusPrice: 0.5325,
            bankroll: 100,
            bankrollCurrency: "GBP",
            impliedEdgePct: 0.25,
            confidenceAdjustedEdgePct: 0.1038,
            kellyFraction: 0.0022,
            cappedStakePct: 0,
            recommendedStake: 0,
            maxLoss: 0,
            expectedValue: 0,
            rewardRiskRatio: 0
          }
        }
      ]
    });

    expect(review.topCandidate?.committee?.finalStance).toBe("watch");
    expect(review.topCandidate?.edgeShortfallPct).toBe(4);
    expect(review.topCandidate?.history?.observations).toBe(3);
    expect(review.topCandidate?.history?.bestGrossEdgePct).toBe(2.1);
    expect(review.topCandidate?.history?.trend).toBe("worsening");
    expect(review.topCandidate?.committee?.votes.some((vote) => vote.analyst === "contract-analyst" && vote.stance === "approve")).toBe(true);
    expect(review.topCandidate?.committee?.votes.some((vote) => vote.analyst === "edge-analyst" && vote.stance === "reject")).toBe(true);
    expect(review.recommendation).toMatch(/needs roughly 4% more gross dislocation/i);
    expect(review.recommendation).toMatch(/resurfaced 3 times recently/i);
    expect(review.recommendation).toMatch(/shortfall trend is worsening/i);
    expect(review.readyForPaper).toBe(false);
  });

  it("uses the lead paper-trade candidate for paper readiness instead of the first row", () => {
    const review = buildPredictionCycleReview({
      ts: "2026-04-15T00:00:00.000Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 100, kalshi: 100, manifold: 20 },
      counts: { reject: 0, watch: 1, "paper-trade": 1 },
      rows: [
        {
          ts: "2026-04-15T00:00:00.000Z",
          candidateId: "watch-candidate",
          venueA: "polymarket",
          venueB: "manifold",
          marketType: "binary",
          normalizedEventKey: "watch-event",
          normalizedQuestionKey: "watch-question",
          normalizedOutcomeKey: "yes",
          eventTitleA: "Watch candidate",
          eventTitleB: "Watch candidate",
          outcomeA: "Yes",
          outcomeB: "Yes",
          expiryA: "2026-05-31T00:00:00Z",
          expiryB: "2026-05-31T23:59:00.000Z",
          settlementCompatible: true,
          matchScore: 0.83,
          entityOverlap: 0.63,
          questionOverlap: 0.88,
          grossEdgePct: 0.5,
          netEdgePct: -4,
          feeDragPct: 4.5,
          displayedSizeA: 128940.3387,
          displayedSizeB: 3689.8991,
          sizeVerdict: "ok",
          verdict: "watch",
          reasons: ["negative-net-edge", "subscale-edge"],
          sizing: {
            action: "buy-cheaper-venue",
            venue: "manifold",
            entryPrice: 0.53,
            referenceVenue: "polymarket",
            referencePrice: 0.535,
            consensusPrice: 0.5325,
            bankroll: 100,
            bankrollCurrency: "GBP",
            impliedEdgePct: 0.25,
            confidenceAdjustedEdgePct: 0.1038,
            kellyFraction: 0.0022,
            cappedStakePct: 0,
            recommendedStake: 0,
            maxLoss: 0,
            expectedValue: 0,
            rewardRiskRatio: 0
          }
        },
        {
          ts: "2026-04-15T00:00:00.000Z",
          candidateId: "paper-candidate",
          venueA: "polymarket",
          venueB: "kalshi",
          marketType: "binary",
          normalizedEventKey: "paper-event",
          normalizedQuestionKey: "paper-question",
          normalizedOutcomeKey: "yes",
          eventTitleA: "Paper candidate",
          eventTitleB: "Paper candidate",
          outcomeA: "Yes",
          outcomeB: "Yes",
          expiryA: "2026-05-31T00:00:00Z",
          expiryB: "2026-05-31T00:00:00Z",
          settlementCompatible: true,
          matchScore: 0.96,
          entityOverlap: 0.95,
          questionOverlap: 0.94,
          grossEdgePct: 8.2,
          netEdgePct: 5.8,
          feeDragPct: 1.4,
          displayedSizeA: 4000,
          displayedSizeB: 5000,
          sizeVerdict: "ok",
          verdict: "paper-trade",
          reasons: ["cross-venue-edge"],
          sizing: {
            action: "buy-cheaper-venue",
            venue: "polymarket",
            entryPrice: 0.31,
            referenceVenue: "kalshi",
            referencePrice: 0.37,
            consensusPrice: 0.34,
            bankroll: 100,
            bankrollCurrency: "GBP",
            impliedEdgePct: 5.4,
            confidenceAdjustedEdgePct: 4,
            kellyFraction: 0.04,
            cappedStakePct: 0.01,
            recommendedStake: 10,
            maxLoss: 5,
            expectedValue: 0.5,
            rewardRiskRatio: 1.8
          }
        }
      ]
    });

    expect(review.topCandidate?.candidateId).toBe("paper-candidate");
    expect(review.readyForPaper).toBe(true);
  });

  it("keeps committee and recommendation aligned when the lead candidate has an expiry mismatch", () => {
    const review = buildPredictionCycleReview({
      ts: "2026-04-15T00:00:00.000Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 100, kalshi: 100, manifold: 20 },
      counts: { reject: 0, watch: 1, "paper-trade": 0 },
      rows: [
        {
          ts: "2026-04-15T00:00:00.000Z",
          candidateId: "expiry-mismatch-candidate",
          venueA: "polymarket",
          venueB: "manifold",
          marketType: "binary",
          normalizedEventKey: "ceasefire-event",
          normalizedQuestionKey: "ceasefire-question",
          normalizedOutcomeKey: "yes",
          eventTitleA: "Ceasefire by June 30",
          eventTitleB: "Ceasefire in April",
          outcomeA: "Yes",
          outcomeB: "Yes",
          expiryA: "2026-06-30T00:00:00Z",
          expiryB: "2026-04-30T23:59:00.000Z",
          settlementCompatible: true,
          matchScore: 0.72,
          entityOverlap: 0.7,
          questionOverlap: 0.77,
          grossEdgePct: 82.92,
          netEdgePct: 78.42,
          feeDragPct: 4.5,
          displayedSizeA: 500,
          displayedSizeB: 500,
          sizeVerdict: "ok",
          verdict: "watch",
          reasons: ["expiry-mismatch"],
          sizing: {
            action: "buy-cheaper-venue",
            venue: "polymarket",
            entryPrice: 0.18,
            referenceVenue: "manifold",
            referencePrice: 0.82,
            consensusPrice: 0.5,
            bankroll: 100,
            bankrollCurrency: "GBP",
            impliedEdgePct: 78.42,
            confidenceAdjustedEdgePct: 39.21,
            kellyFraction: 0.2,
            cappedStakePct: 0.01,
            recommendedStake: 1,
            maxLoss: 1,
            expectedValue: 14.9,
            rewardRiskRatio: 1.5
          }
        }
      ]
    });

    expect(review.topCandidate?.committee?.finalStance).toBe("watch");
    expect(review.recommendation).toMatch(/different expiry windows/i);
    expect(review.readyForPaper).toBe(false);
  });

  it("prioritizes economic shortfall messaging when the contract is real but edge is still negative", () => {
    const review = buildPredictionCycleReview({
      ts: "2026-04-24T16:01:48.236Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 493, kalshi: 62, manifold: 2 },
      counts: { reject: 0, watch: 1, "paper-trade": 0 },
      rows: [
        {
          ts: "2026-04-24T16:01:48.236Z",
          candidateId: "polymarket:1919421__manifold:ZUyOquuQEg",
          venueA: "polymarket",
          venueB: "manifold",
          marketType: "binary",
          normalizedEventKey: "by deal iran peace permanent us",
          normalizedQuestionKey: "30 april by deal iran peace permanent us",
          normalizedOutcomeKey: "yes",
          eventTitleA: "US x Iran permanent peace deal by...?",
          eventTitleB: "US x Iran permanent peace deal by April 30? [Polymarket]",
          outcomeA: "Yes",
          outcomeB: "Yes",
          expiryA: "2026-05-31T00:00:00Z",
          expiryB: "2026-04-30T23:59:00.000Z",
          sameHorizon: true,
          settlementCompatible: true,
          matchScore: 0.84,
          entityOverlap: 0.63,
          questionOverlap: 0.94,
          grossEdgePct: 0.28,
          netEdgePct: -4.22,
          feeDragPct: 4.5,
          displayedSizeA: 494976.841,
          displayedSizeB: 10387.140096234392,
          sizeVerdict: "ok",
          verdict: "watch",
          reasons: ["negative-net-edge", "cost-drag-exceeds-edge", "subscale-edge"],
          sizing: {
            action: "buy-cheaper-venue",
            venue: "polymarket",
            entryPrice: 0.095,
            referenceVenue: "manifold",
            referencePrice: 0.0978,
            consensusPrice: 0.0964,
            bankroll: 100,
            bankrollCurrency: "GBP",
            impliedEdgePct: 0.14,
            confidenceAdjustedEdgePct: 0.0588,
            kellyFraction: 0.0007,
            cappedStakePct: 0,
            recommendedStake: 0,
            maxLoss: 0,
            expectedValue: 0,
            rewardRiskRatio: 0
          }
        }
      ]
    });

    expect(review.recommendation).toMatch(/too weak after costs/i);
    expect(review.recommendation).toMatch(/needs roughly 4.22% more gross dislocation/i);
  });

  it("does not approve a paper candidate when liquidity is still unknown", () => {
    const review = buildPredictionCycleReview({
      ts: "2026-04-24T16:30:00.000Z",
      policy: DEFAULT_PREDICTION_SOURCE_POLICY,
      venueCounts: { polymarket: 493, kalshi: 62, manifold: 2 },
      counts: { reject: 0, watch: 0, "paper-trade": 1 },
      rows: [
        {
          ts: "2026-04-24T16:30:00.000Z",
          candidateId: "unknown-liquidity-paper",
          venueA: "polymarket",
          venueB: "kalshi",
          marketType: "binary",
          normalizedEventKey: "paper-event",
          normalizedQuestionKey: "paper-question",
          normalizedOutcomeKey: "yes",
          eventTitleA: "Paper candidate",
          eventTitleB: "Paper candidate",
          outcomeA: "Yes",
          outcomeB: "Yes",
          expiryA: "2026-05-31T00:00:00Z",
          expiryB: "2026-05-31T00:00:00Z",
          sameHorizon: true,
          settlementCompatible: true,
          matchScore: 0.96,
          entityOverlap: 0.95,
          questionOverlap: 0.94,
          grossEdgePct: 8.2,
          netEdgePct: 5.8,
          feeDragPct: 1.4,
          sizeVerdict: "ok",
          verdict: "paper-trade",
          reasons: ["cross-venue-edge"],
          sizing: {
            action: "buy-cheaper-venue",
            venue: "polymarket",
            entryPrice: 0.31,
            referenceVenue: "kalshi",
            referencePrice: 0.37,
            consensusPrice: 0.34,
            bankroll: 100,
            bankrollCurrency: "GBP",
            impliedEdgePct: 5.4,
            confidenceAdjustedEdgePct: 4,
            kellyFraction: 0.04,
            cappedStakePct: 0.01,
            recommendedStake: 10,
            maxLoss: 5,
            expectedValue: 0.5,
            rewardRiskRatio: 1.8
          }
        }
      ]
    });

    expect(review.topCandidate?.committee?.votes.some((vote) => vote.analyst === "liquidity-analyst" && vote.stance === "watch")).toBe(true);
    expect(review.topCandidate?.committee?.finalStance).toBe("watch");
    expect(review.readyForPaper).toBe(false);
  });
});
