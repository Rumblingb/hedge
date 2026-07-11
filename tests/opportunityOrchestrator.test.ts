import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { buildOpportunitySnapshot } from "../src/opportunity/orchestrator.js";

function writeJson(baseDir: string, relativePath: string, value: unknown): void {
  const path = resolve(baseDir, relativePath);
  mkdirSync(resolve(path, ".."), { recursive: true });
  writeFileSync(path, JSON.stringify(value));
}

describe("opportunity orchestrator", () => {
  it("builds an action board without touching the live workspace", async () => {
    const baseDir = mkdtempSync(resolve(tmpdir(), "opportunity-orchestrator-"));

    writeJson(baseDir, ".rumbling-hedge/state/prediction-review.latest.json", {
      review: {
        counts: { watch: 1, "paper-trade": 0, reject: 0 },
        topCandidate: { candidateId: "candidate-1" },
        readyForPaper: false,
        blockers: ["no-paper-candidates"],
        recommendation: "Keep collecting"
      }
    });
    writeJson(baseDir, ".rumbling-hedge/state/prediction-copy-demo.latest.json", {
      ts: "2026-04-15T00:00:00.000Z",
      ideas: [{ id: "idea-1", slug: "macro-theme", action: "watch" }],
      blockers: [],
      summary: "Watch-only"
    });
    writeJson(baseDir, ".rumbling-hedge/state/futures-demo.latest.json", {
      posture: {
        deployableNow: false,
        mode: "paper",
        reportStatus: "yellow",
        whyNotTrading: ["unstable"],
        selectedProfileDescription: "demo"
      },
      sampling: {
        laneCount: 2,
        sampleSequence: 5,
        lanes: [{ accountId: "demo1", label: "lane1", primaryStrategy: "session", focusSymbol: "NQ", action: "shadow-observe" }]
      }
    });
    writeJson(baseDir, ".rumbling-hedge/state/prediction-learning.latest.json", {
      recentCycleSummary: {
        totalCycles: 12,
        structuralWatchCycles: 8,
        economicBlockCycles: 7,
        dominantCandidate: {
          candidateId: "candidate-1",
          observations: 7,
          bestGrossEdgePct: 4.1,
          latestGrossEdgePct: 3.7,
          latestShortfallPct: 1.2,
          trend: "improving"
        }
      }
    });
    writeJson(baseDir, ".rumbling-hedge/research/researcher/latest-run.json", {
      runId: "run-1",
      startedAt: "2026-04-15T00:00:00.000Z",
      finishedAt: "2026-04-15T00:01:00.000Z",
      targetsAttempted: 1,
      targetsSucceeded: 1,
      chunksCollected: 5,
      chunksKept: 4,
      firecrawlUsed: false,
      dedupRate: 0.2,
      topKeptTitles: ["Firecrawl Intro"],
      strategyHypothesesCount: 2,
      topStrategyHypotheses: ["London session displacement continuation"]
    });
    writeJson(baseDir, ".rumbling-hedge/research/researcher/strategy-hypotheses.latest.json", {
      generatedAt: "2026-04-15T00:01:00.000Z",
      runId: "run-1",
      count: 2,
      provider: "ollama",
      model: "qwen2.5-coder:14b",
      hypotheses: [
        {
          id: "ict-1",
          title: "London session displacement continuation",
          market: "futures",
          symbols: ["NQ", "ES"],
          timeframes: ["5m"],
          sessions: ["london"],
          setupSummary: "Fair value gap continuation after displacement.",
          biasRules: ["Trade only with London-session displacement."],
          entryRules: ["Enter on FVG retrace."],
          stopRules: ["Stop beyond liquidity raid."],
          targetRules: ["Target external liquidity."],
          riskRules: ["Keep risk fixed."],
          confluence: ["ICT", "FVG", "MSS"],
          invalidationRules: ["Stand down if displacement fails."],
          evidence: ["displacement", "fair value gap"],
          automationReadiness: "high",
          confidence: 0.82,
          sourceTargetIds: ["ict-youtube-transcripts"],
          sourceVideoIds: ["video-1"],
          sourceVideoTitles: ["ICT title"],
          sourceChannels: ["Inner Circle Trader"],
          sourceUrls: ["https://www.youtube.com/watch?v=video-1"]
        }
      ]
    });
    writeJson(baseDir, ".rumbling-hedge/research/source-catalog.json", [
      { id: "polymarket", tracks: ["prediction"], configured: true, automationReady: true, collectionCommand: "collect" },
      { id: "yahoo", tracks: ["futures-core", "crypto-liquid"], configured: true, automationReady: true, collectionCommand: "collect" },
      { id: "polygon", tracks: ["options-us"], configured: false, automationReady: true, mode: "missing-config", reason: "Configure RH_POLYGON_API_KEY" },
      { id: "fred", tracks: ["macro-rates"], configured: false, automationReady: true, mode: "missing-config", reason: "Configure FRED_API_KEY" }
    ]);

    mkdirSync(resolve(baseDir, "data/research/crypto-bars"), { recursive: true });
    writeFileSync(resolve(baseDir, "data/research/crypto-bars/BTCUSD-1d-1mo.csv"), "ts,open\n");

    const snapshot = await buildOpportunitySnapshot({
      baseDir,
      env: {
        BILL_ACTIVE_TRACKS: "prediction,futures-core",
        BILL_RESEARCH_ONLY_TRACKS: "options-us,crypto-liquid,macro-rates"
      }
    });

    expect(snapshot.prediction.posture).toBe("watch-only");
    expect(snapshot.primaryAction.lane).toBe("futures-core");
    expect(snapshot.primaryAction.stage).toBe("shadow");
    expect(snapshot.trackBoard.find((track) => track.id === "crypto-liquid")?.posture).toBe("collecting");
    expect(snapshot.trackBoard.find((track) => track.id === "options-us")?.posture).toBe("setup-debt");
    expect(snapshot.trackBoard.find((track) => track.id === "macro-rates")?.nextAction).toContain("FRED");
    expect(snapshot.trackBoard.find((track) => track.id === "long-only-compounder")?.posture).toBe("idle");
    expect(snapshot.actionQueue.some((action) => action.lane === "futures-core" && action.stage === "shadow")).toBe(true);
    expect(snapshot.actionQueue.some((action) => action.lane === "prediction" && action.stage === "collect")).toBe(true);
    expect(snapshot.fundPlan.mode).toBe("seed-compounder");
    expect(snapshot.fundPlan.buckets.find((bucket) => bucket.id === "compounder")?.deployedPct).toBe(0);
    expect(snapshot.attention.some((line) => line.includes("candidate-1"))).toBe(true);
    expect(snapshot.research.strategyFocusStrategies).toContain("ict-displacement");
    expect(snapshot.research.strategyFocusSymbols).toContain("NQ");
  });

  it("treats the selected refreshed futures dataset as current even when the requested path was stale", async () => {
    const baseDir = mkdtempSync(resolve(tmpdir(), "opportunity-orchestrator-"));

    writeJson(baseDir, ".rumbling-hedge/state/prediction-review.latest.json", {
      review: {
        ts: "2026-04-18T00:30:00.000Z",
        counts: { watch: 1, "paper-trade": 0, reject: 0 },
        readyForPaper: false,
        blockers: ["no-paper-candidates"],
        recommendation: "Keep collecting"
      }
    });
    writeJson(baseDir, ".rumbling-hedge/state/futures-demo.latest.json", {
      ts: "2026-04-18T01:00:00.000Z",
      posture: {
        deployableNow: false,
        mode: "paper",
        reportStatus: "yellow",
        whyNotTrading: ["unstable"],
        selectedProfileDescription: "demo"
      },
      sampling: {
        ts: "2026-04-18T01:00:00.000Z",
        laneCount: 1,
        sampleSequence: 8,
        lanes: [{ accountId: "demo1", label: "lane1", primaryStrategy: "session", focusSymbol: "NQ", action: "shadow-observe" }]
      },
      data: {
        path: `${baseDir}/data/free/ALL-6MARKETS-1m-10d-normalized.csv`,
        requestedPath: `${baseDir}/data/free/ALL-6MARKETS-1m-5d-normalized.csv`,
        inspection: {
          endTs: "2026-04-18T00:58:00.000Z"
        },
        preflight: {
          priorStatus: {
            shouldRefresh: true,
            staleHours: 360,
            reasons: ["dataset has only 5 distinct day(s), below the 7-day minimum"]
          },
          warnings: []
        }
      }
    });
    writeJson(baseDir, ".rumbling-hedge/research/researcher/latest-run.json", {
      runId: "run-1",
      finishedAt: "2026-04-18T00:59:00.000Z",
      targetsAttempted: 1,
      targetsSucceeded: 1,
      chunksCollected: 1,
      chunksKept: 1,
      firecrawlUsed: true,
      topKeptTitles: ["one"],
      status: "healthy"
    });
    writeJson(baseDir, ".rumbling-hedge/research/source-catalog.json", []);

    const snapshot = await buildOpportunitySnapshot({
      baseDir,
      now: () => "2026-04-18T01:02:00.000Z",
      env: {
        BILL_ACTIVE_TRACKS: "prediction,futures-core"
      }
    });

    expect(snapshot.futures.datasetFreshness?.status).toBe("fresh");
    expect(snapshot.futures.warnings ?? []).not.toContain("dataset has only 5 distinct day(s), below the 7-day minimum");
    expect(snapshot.primaryAction.lane).toBe("futures-core");
    expect(snapshot.fundPlan.mode).toBe("stabilize-core");
  });

  it("accepts flat prediction review artifacts with a top-level timestamp", async () => {
    const baseDir = mkdtempSync(resolve(tmpdir(), "opportunity-orchestrator-"));

    writeJson(baseDir, ".rumbling-hedge/state/prediction-review.latest.json", {
      ts: "2026-04-18T00:30:00.000Z",
      counts: { watch: 1, "paper-trade": 0, reject: 0 },
      topCandidate: { candidateId: "candidate-flat", verdict: "watch", reasons: ["negative-net-edge"] },
      readyForPaper: false,
      blockers: ["no-paper-candidates"],
      recommendation: "Keep collecting"
    });
    writeJson(baseDir, ".rumbling-hedge/state/prediction-learning.latest.json", {
      ts: "2026-04-18T00:31:00.000Z",
      recentCycleSummary: {
        totalCycles: 4,
        structuralWatchCycles: 4,
        economicBlockCycles: 4
      }
    });
    writeJson(baseDir, ".rumbling-hedge/research/researcher/latest-run.json", {
      runId: "run-flat",
      finishedAt: "2026-04-18T00:32:00.000Z",
      targetsAttempted: 1,
      targetsSucceeded: 1,
      chunksCollected: 1,
      chunksKept: 1,
      firecrawlUsed: true,
      topKeptTitles: ["one"],
      status: "healthy"
    });
    writeJson(baseDir, ".rumbling-hedge/research/source-catalog.json", []);

    const snapshot = await buildOpportunitySnapshot({
      baseDir,
      now: () => "2026-04-18T00:35:00.000Z",
      env: {
        BILL_ACTIVE_TRACKS: "prediction"
      }
    });

    expect(snapshot.prediction.topCandidate?.candidateId).toBe("candidate-flat");
    expect(snapshot.prediction.counts.watch).toBe(1);
    expect(snapshot.prediction.freshness?.status).toBe("fresh");
  });
});
