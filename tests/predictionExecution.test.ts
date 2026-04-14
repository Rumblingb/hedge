import { describe, expect, it } from "vitest";
import { routePredictionCandidates } from "../src/prediction/execution/router.js";
import { evaluateLiveGate } from "../src/prediction/execution/liveGate.js";
import type { PredictionCandidate } from "../src/prediction/types.js";

function buildCandidate(
  overrides: Partial<PredictionCandidate> = {}
): PredictionCandidate {
  const base: PredictionCandidate = {
    ts: "2026-04-15T00:00:00Z",
    candidateId: "cand-1",
    venueA: "polymarket",
    venueB: "kalshi",
    marketType: "binary",
    normalizedEventKey: "spain-fifa-26",
    normalizedQuestionKey: "spain-win-fifa-26",
    normalizedOutcomeKey: "yes",
    eventTitleA: "Spain win FIFA 2026?",
    eventTitleB: "Will Spain win the 2026 FIFA World Cup?",
    outcomeA: "Yes",
    outcomeB: "Yes",
    settlementCompatible: true,
    matchScore: 0.92,
    entityOverlap: 0.9,
    questionOverlap: 0.85,
    grossEdgePct: 6.2,
    netEdgePct: 4.8,
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
      confidenceAdjustedEdgePct: 4.0,
      kellyFraction: 0.04,
      cappedStakePct: 0.01,
      recommendedStake: 10,
      maxLoss: 5,
      expectedValue: 0.5,
      rewardRiskRatio: 1.8
    }
  };
  return { ...base, ...overrides };
}

describe("prediction execution router", () => {
  it("routes a paper-trade candidate into a fill under caps", () => {
    const outcome = routePredictionCandidates([buildCandidate()], {
      config: {
        mode: "paper",
        maxTotalStake: 50,
        maxTotalMaxLoss: 25,
        stakeCurrency: "GBP",
        journalPath: "journals/test-fills.jsonl",
        onePerCandidate: true
      }
    });
    expect(outcome.placed).toHaveLength(1);
    expect(outcome.placed[0].candidateId).toBe("cand-1");
    expect(outcome.totalStake).toBe(10);
    expect(outcome.skipped).toHaveLength(0);
  });

  it("skips a candidate whose verdict is not paper-trade", () => {
    const outcome = routePredictionCandidates(
      [buildCandidate({ verdict: "watch", sizing: undefined })],
      {
        config: {
          mode: "paper",
          maxTotalStake: 50,
          maxTotalMaxLoss: 25,
          stakeCurrency: "GBP",
          journalPath: "journals/test-fills.jsonl",
          onePerCandidate: true
        }
      }
    );
    expect(outcome.placed).toHaveLength(0);
    expect(outcome.skipped[0].reason).toContain("verdict=watch");
  });

  it("enforces the aggregate stake ceiling", () => {
    const outcome = routePredictionCandidates(
      [
        buildCandidate({ candidateId: "a" }),
        buildCandidate({ candidateId: "b" }),
        buildCandidate({ candidateId: "c" })
      ],
      {
        config: {
          mode: "paper",
          maxTotalStake: 15,
          maxTotalMaxLoss: 100,
          stakeCurrency: "GBP",
          journalPath: "journals/test-fills.jsonl",
          onePerCandidate: true
        }
      }
    );
    expect(outcome.placed).toHaveLength(1);
    expect(outcome.skipped.map((s) => s.reason).some((r) => r.includes("stake ceiling"))).toBe(true);
  });

  it("refuses to double-fill a candidate that already exists in the journal", () => {
    const outcome = routePredictionCandidates([buildCandidate()], {
      config: {
        mode: "paper",
        maxTotalStake: 50,
        maxTotalMaxLoss: 25,
        stakeCurrency: "GBP",
        journalPath: "journals/test-fills.jsonl",
        onePerCandidate: true
      },
      existingFills: [
        {
          fillId: "existing",
          ts: "2026-04-14T00:00:00Z",
          mode: "paper",
          candidateId: "cand-1",
          venue: "polymarket",
          referenceVenue: "kalshi",
          marketQuestion: "Spain",
          outcomeLabel: "Yes",
          side: "yes",
          price: 0.31,
          referencePrice: 0.37,
          consensusPrice: 0.34,
          stake: 10,
          stakeCurrency: "GBP",
          impliedEdgePct: 5.4,
          expectedValue: 0.5,
          maxLoss: 5,
          rewardRiskRatio: 1.8,
          reasons: []
        }
      ]
    });
    expect(outcome.placed).toHaveLength(0);
    expect(outcome.skipped[0].reason).toContain("already-filled");
  });

  it("refuses all candidates in live mode when the live gate fails", () => {
    const outcome = routePredictionCandidates([buildCandidate()], {
      config: {
        mode: "live",
        maxTotalStake: 50,
        maxTotalMaxLoss: 25,
        stakeCurrency: "GBP",
        journalPath: "journals/test-fills.jsonl",
        onePerCandidate: true
      },
      env: {} as NodeJS.ProcessEnv
    });
    expect(outcome.placed).toHaveLength(0);
    expect(outcome.skipped[0].reason).toContain("live gate refused");
  });

  it("admits live-mode execution only when every gate flag is set", () => {
    const env = {
      BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "true",
      BILL_PREDICTION_LIVE_ACKNOWLEDGED: "true",
      BILL_PREDICTION_LIVE_MAX_STAKE: "50",
      BILL_PREDICTION_BANKROLL_CURRENCY: "GBP",
      RH_MODE: "live"
    } as unknown as NodeJS.ProcessEnv;
    const gate = evaluateLiveGate(env);
    expect(gate.ok).toBe(true);
    const outcome = routePredictionCandidates([buildCandidate()], {
      config: {
        mode: "live",
        maxTotalStake: 50,
        maxTotalMaxLoss: 25,
        stakeCurrency: "GBP",
        journalPath: "journals/test-fills.jsonl",
        onePerCandidate: true
      },
      env
    });
    expect(outcome.placed).toHaveLength(1);
    expect(outcome.placed[0].mode).toBe("live");
  });
});
