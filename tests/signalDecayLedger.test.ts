import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildSignalDecayLedger } from "../src/engine/signalDecayLedger.js";
import type { MacroConditionedPolicyReport } from "../src/engine/macroConditionedPolicy.js";
import type { PredictionCycleReview } from "../src/prediction/types.js";

describe("signal decay ledger", () => {
  it("promotes only durable first-lane paper candidates and leaves expansion locked", async () => {
    const dir = await mkdtemp(join(tmpdir(), "signal-decay-"));
    const futuresPolicyPath = join(dir, "macro-policy.json");
    const predictionReviewPath = join(dir, "prediction-review.json");
    const predictionResolvedPath = join(dir, "prediction-resolved.jsonl");
    const outputPath = join(dir, "ledger.json");
    const historyPath = join(dir, "ledger.jsonl");

    const futuresPolicy: Partial<MacroConditionedPolicyReport> = {
      command: "macro-conditioned-policy",
      blockers: [],
      selected: {
        profileId: "convex-index-asymmetry",
        symbol: "NQ",
        strategyId: "liquidity-reversion",
        macroGate: {
          riskRegime: "normal",
          vixTermStructure: "contango",
          creditRiskProxy: "normal",
          equityTrendProxy: "risk-on",
          maxTailScore: 6.9
        },
        action: "paper-allow",
        score: 0.72,
        trades: 10,
        netTotalR: 7.1,
        averageR: 0.71,
        winRate: 0.7,
        profitFactor: 2.4,
        sharpePerTrade: 0.5,
        cvar95TradeR: -1,
        riskOfRuinProb: 0.05,
        maxConsecutiveLosses: 1,
        rationale: []
      }
    };
    const predictionReview: Partial<PredictionCycleReview> = {
      ts: "2026-05-06T13:00:00.000Z",
      counts: { reject: 0, watch: 1, "paper-trade": 0 },
      blockers: ["lead-candidate-not-paper-trade"],
      readyForPaper: false,
      topCandidate: {
        candidateId: "polymarket:X__kalshi:Y",
        verdict: "watch",
        reasons: ["edge-too-small"],
        grossEdgePct: 3,
        netEdgePct: 0.5,
        feeDragPct: 2.5,
        edgeShortfallPct: 2,
        matchScore: 0.9,
        recommendedStake: 0,
        venuePair: "polymarket->kalshi",
        history: {
          observations: 3,
          watchCycles: 3,
          paperCycles: 0,
          bestGrossEdgePct: 3,
          bestNetEdgePct: 0.5,
          averageGrossEdgePct: 2.8,
          averageNetEdgePct: 0.3,
          averageShortfallPct: 2,
          latestGrossEdgePct: 3,
          latestNetEdgePct: 0.5,
          latestShortfallPct: 2,
          trend: "flat"
        }
      }
    };

    await writeFile(futuresPolicyPath, JSON.stringify(futuresPolicy), "utf8");
    await writeFile(predictionReviewPath, JSON.stringify(predictionReview), "utf8");
    await writeFile(predictionResolvedPath, JSON.stringify({
      ts: "2026-05-05T13:00:00.000Z",
      candidateId: "polymarket:old__kalshi:old",
      venueA: "polymarket",
      venueB: "kalshi",
      marketType: "binary",
      normalizedEventKey: "",
      normalizedQuestionKey: "",
      normalizedOutcomeKey: "yes",
      eventTitleA: "",
      eventTitleB: "",
      outcomeA: "Yes",
      outcomeB: "Yes",
      settlementCompatible: true,
      matchScore: 0.9,
      entityOverlap: 0.8,
      questionOverlap: 0.8,
      grossEdgePct: 5,
      netEdgePct: 3,
      feeDragPct: 2,
      sizeVerdict: "ok",
      verdict: "paper-trade",
      reasons: [],
      resolvedAt: "2026-05-06T13:00:00.000Z",
      settlementMismatch: false,
      realizedGrossEdgePct: 5,
      realizedNetEdgePct: 3,
      calibrationBucket: "2-5"
    }) + "\n", "utf8");

    const report = await buildSignalDecayLedger({
      futuresPolicyPath,
      strategyFactoryPath: join(dir, "missing-strategy-factory.json"),
      predictionReviewPath,
      predictionResolvedPath,
      outputPath,
      historyPath,
      env: {
        RH_LIVE_EXECUTION_ENABLED: "false",
        BILL_PREDICTION_EXECUTION_MODE: "paper",
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false"
      } as NodeJS.ProcessEnv,
      now: () => "2026-05-06T14:00:00.000Z"
    });

    expect(report.status).toBe("cashflow-candidate");
    expect(report.entries.find((entry) => entry.lane === "futures-prop")?.status).toBe("active");
    expect(report.entries.find((entry) => entry.lane === "prediction-markets")?.status).not.toBe("active");
    expect(report.entries.find((entry) => entry.lane === "prediction-markets")?.evidence.resolvedOutcomes).toBe(1);
    expect(report.unlockPlan.find((entry) => entry.lane === "crypto-liquid")?.status).toBe("locked");
    expect(report.operatingDoctrine.join(" ")).toMatch(/LLMs observe/i);
  });
});
