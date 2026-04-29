import { describe, expect, it } from "vitest";
import { DEFAULT_PREDICTION_SCAN_POLICY } from "../src/prediction/scanPolicy.js";
import { summarizePredictionSources, summarizeRecentPredictionCycles, trainPredictionPolicy } from "../src/prediction/training.js";
import type { PredictionCandidate } from "../src/prediction/types.js";

function makeCandidate(args: {
  candidateId: string;
  venueA: string;
  venueB: string;
  matchScore: number;
  netEdgePct: number;
  recommendedStake: number;
}): PredictionCandidate {
  return {
    ts: "2026-04-15T00:00:00.000Z",
    candidateId: args.candidateId,
    venueA: args.venueA,
    venueB: args.venueB,
    marketType: "binary",
    normalizedEventKey: "event",
    normalizedQuestionKey: "question",
    normalizedOutcomeKey: "yes",
    eventTitleA: "Event A",
    eventTitleB: "Event B",
    outcomeA: "Yes",
    outcomeB: "Yes",
    expiryA: "2026-12-01",
    expiryB: "2026-12-01",
    settlementCompatible: true,
    matchScore: args.matchScore,
    entityOverlap: args.matchScore,
    questionOverlap: args.matchScore,
    grossEdgePct: args.netEdgePct + 4.5,
    netEdgePct: args.netEdgePct,
    feeDragPct: 4.5,
    displayedSizeA: 400,
    displayedSizeB: 400,
    sizeVerdict: "ok",
    verdict: "watch",
    reasons: [],
    sizing: {
      action: "buy-cheaper-venue",
      venue: args.venueA,
      entryPrice: 0.4,
      referenceVenue: args.venueB,
      referencePrice: 0.45,
      consensusPrice: 0.425,
      bankroll: 100,
      bankrollCurrency: "GBP",
      impliedEdgePct: args.netEdgePct,
      confidenceAdjustedEdgePct: args.netEdgePct,
      kellyFraction: 0.05,
      cappedStakePct: 0.02,
      recommendedStake: args.recommendedStake,
      maxLoss: args.recommendedStake,
      expectedValue: 1.2,
      rewardRiskRatio: 0.2
    }
  };
}

describe("prediction training", () => {
  it("prefers stricter paper thresholds when extra paper candidates are low conviction", () => {
    const rows: PredictionCandidate[] = [
      makeCandidate({
        candidateId: "strong",
        venueA: "polymarket",
        venueB: "kalshi",
        matchScore: 0.92,
        netEdgePct: 6,
        recommendedStake: 5
      }),
      makeCandidate({
        candidateId: "borderline",
        venueA: "manifold",
        venueB: "polymarket",
        matchScore: 0.74,
        netEdgePct: 3.2,
        recommendedStake: 1.4
      }),
      makeCandidate({
        candidateId: "watch",
        venueA: "kalshi",
        venueB: "manifold",
        matchScore: 0.78,
        netEdgePct: 2.9,
        recommendedStake: 2
      })
    ];

    const state = trainPredictionPolicy({
      rows,
      currentPolicy: DEFAULT_PREDICTION_SCAN_POLICY,
      sourceSummary: summarizePredictionSources([
        { category: "prediction-market", mode: "active" },
        { category: "prediction-market", mode: "active" },
        { category: "prediction-market", mode: "catalog-only" }
      ]),
      recentCycleSummary: summarizeRecentPredictionCycles([
        {
          venuesHealthy: 2,
          scan: { counts: { reject: 1, watch: 1, "paper-trade": 1 } },
          topCandidate: { netEdgePct: 5.5, matchScore: 0.91 },
          review: {
            topCandidate: {
              committee: {
                votes: [
                  { analyst: "contract-analyst", stance: "approve" },
                  { analyst: "portfolio-manager", stance: "approve" }
                ]
              }
            }
          }
        }
      ]),
      paths: {
        journalPath: "/tmp/journal.jsonl",
        policyPath: "/tmp/policy.json",
        statePath: "/tmp/state.json",
        historyPath: "/tmp/history.jsonl",
        trainingSetPath: "/tmp/training.json"
      },
      ts: "2026-04-15T00:00:00.000Z"
    });

    expect(state.selectedEvaluation.objectiveScore).toBeGreaterThan(state.baselineEvaluation.objectiveScore);
    expect(state.selectedEvaluation.lowConvictionPaperCount).toBeLessThan(state.baselineEvaluation.lowConvictionPaperCount);
    expect(
      state.selectedPolicy.paperEdgeThresholdPct > DEFAULT_PREDICTION_SCAN_POLICY.paperEdgeThresholdPct
      || state.selectedPolicy.paperMatchScore > DEFAULT_PREDICTION_SCAN_POLICY.paperMatchScore
      || state.selectedPolicy.minRecommendedStake > DEFAULT_PREDICTION_SCAN_POLICY.minRecommendedStake
    ).toBe(true);
    expect(state.recommendations[0]).toContain("Adopt");
  });

  it("summarizes source coverage and cycle health", () => {
    expect(summarizePredictionSources([
      { category: "prediction-market", mode: "active" },
      { category: "prediction-market", mode: "missing-config" },
      { category: "market-data", mode: "catalog-only" }
    ])).toEqual({
      totalSources: 3,
      activeSources: 1,
      activePredictionSources: 1,
      missingConfigSources: 1,
      catalogOnlySources: 1
    });

    expect(summarizeRecentPredictionCycles([
      {
        venuesHealthy: 2,
        scan: { counts: { reject: 0, watch: 1, "paper-trade": 1 } },
        topCandidate: { netEdgePct: 4.5, matchScore: 0.87 },
        review: {
          topCandidate: {
            candidateId: "cand-1",
            grossEdgePct: 1.5,
            edgeShortfallPct: 3,
            committee: {
              votes: [
                { analyst: "contract-analyst", stance: "approve" },
                { analyst: "portfolio-manager", stance: "watch" },
                { analyst: "edge-analyst", stance: "reject" },
                { analyst: "risk-manager", stance: "reject" }
              ]
            }
          }
        }
      },
      {
        venuesHealthy: 1,
        scan: { counts: { reject: 1, watch: 0, "paper-trade": 0 } },
        topCandidate: { netEdgePct: 0, matchScore: 0 },
        review: {
          topCandidate: {
            candidateId: "cand-1",
            grossEdgePct: 4.5,
            edgeShortfallPct: 0
          }
        }
      }
    ])).toEqual({
      totalCycles: 2,
      healthyCycles: 1,
      paperCandidateCycles: 1,
      structuralWatchCycles: 1,
      economicBlockCycles: 1,
      averageTopEdgePct: 4.5,
      averageTopMatchScore: 0.87,
      dominantCandidate: {
        candidateId: "cand-1",
        observations: 2,
        bestGrossEdgePct: 4.5,
        latestGrossEdgePct: 4.5,
        latestShortfallPct: 0,
        trend: "improving"
      }
    });
  });
});
