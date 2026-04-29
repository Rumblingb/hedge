import { describe, expect, it } from "vitest";
import { DEFAULT_PREDICTION_SCAN_POLICY, classifyPredictionCandidate } from "../src/prediction/scanPolicy.js";

describe("prediction scan policy", () => {
  it("downgrades expiry mismatches to watch instead of paper-trade", () => {
    const result = classifyPredictionCandidate({
      candidate: {
        matchScore: 0.96,
        grossEdgePct: 8.2,
        netEdgePct: 5.8,
        feeDragPct: 1.4,
        displayedSizeA: 2000,
        displayedSizeB: 1800,
        expiryA: "2026-06-01T00:00:00Z",
        expiryB: "2026-08-01T00:00:00Z",
        settlementCompatible: true,
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
          rewardRiskRatio: 1.8,
        },
      },
      policy: DEFAULT_PREDICTION_SCAN_POLICY,
    });

    expect(result.reasons).toContain("expiry-mismatch");
    expect(result.verdict).toBe("watch");
  });

  it("treats semantic deadline matches as same-horizon even when venue expiry metadata differs", () => {
    const result = classifyPredictionCandidate({
      candidate: {
        matchScore: 0.84,
        grossEdgePct: 0.28,
        netEdgePct: -4.22,
        feeDragPct: 4.5,
        displayedSizeA: 4000,
        displayedSizeB: 5000,
        expiryA: "2026-05-31T00:00:00Z",
        expiryB: "2026-04-30T23:59:00.000Z",
        sameHorizon: true,
        settlementCompatible: true,
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
      },
      policy: DEFAULT_PREDICTION_SCAN_POLICY
    });

    expect(result.reasons).not.toContain("expiry-mismatch");
    expect(result.verdict).toBe("watch");
  });

  it("keeps legacy rows conservative when sameHorizon is missing", () => {
    const result = classifyPredictionCandidate({
      candidate: {
        matchScore: 0.96,
        grossEdgePct: 8.2,
        netEdgePct: 5.8,
        feeDragPct: 1.4,
        displayedSizeA: 2000,
        displayedSizeB: 1800,
        expiryA: "2026-04-30T00:00:00Z",
        expiryB: "2026-05-02T00:00:00Z",
        settlementCompatible: true,
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
      },
      policy: DEFAULT_PREDICTION_SCAN_POLICY
    });

    expect(result.reasons).toContain("expiry-mismatch");
    expect(result.verdict).toBe("watch");
  });

  it("treats unknown displayed size as thin rather than paperable", () => {
    const result = classifyPredictionCandidate({
      candidate: {
        matchScore: 0.96,
        grossEdgePct: 8.2,
        netEdgePct: 5.8,
        feeDragPct: 1.4,
        sameHorizon: true,
        settlementCompatible: true,
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
      },
      policy: DEFAULT_PREDICTION_SCAN_POLICY
    });

    expect(result.sizeVerdict).toBe("thin");
    expect(result.reasons).toContain("thin-size");
    expect(result.verdict).toBe("watch");
  });
});
